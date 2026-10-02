"""Offline DNS bundle rehearsal; copies into a new temporary directory, never a service."""
import argparse
import gzip
import hashlib
import json
import os
import re
import sqlite3
import stat
import tarfile
import tempfile
import time
from contextlib import closing
from pathlib import Path, PurePosixPath

MAX_DATABASE_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
MAX_EXPANDED_BYTES = 512 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10000
REQUIRED_FILES = {"dns.sqlite3", "config.tar.gz"}
SUPPORTED_MIGRATIONS = {1, 2, 3, 4, 5}
REQUIRED_COLUMNS = {
    "users": {"sub", "name", "created"},
    "sessions": {"hash", "sub", "csrf", "expires"},
    "devices": {"id", "sub", "token_hash", "token_enc", "revoked"},
    "account_settings": {"sub", "enabled", "qps", "burst", "is_admin"},
    "moddns_mapping": {"sub", "account_id", "profile_id", "state", "routing", "revision", "personalized"},
    "query_log_settings": {"sub", "enabled", "retention"},
    "query_history": {"id", "sub", "timestamp", "domain"},
    "schema_migrations": {"version", "applied"},
}


class VerificationError(ValueError):
    """Fixed reason codes only: never include a path, token, query, or database row."""


def read_regular(path: Path, limit: int):
    # Reject symlink inputs; inspect an already-open descriptor to avoid link races.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    handle = os.fdopen(fd, "rb")
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        handle.close()
        raise VerificationError("input_type_or_size_invalid")
    return handle


def read_manifest(bundle: Path) -> dict:
    with read_regular(bundle / "SHA256SUMS", 4096) as handle:
        data = handle.read(4097)
    if len(data) > 4096:
        raise VerificationError("manifest_invalid")
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError:
        raise VerificationError("manifest_invalid") from None
    hashes = {}
    for line in lines:
        match = re.fullmatch(r"([a-fA-F0-9]{64})  (dns\.sqlite3|config\.tar\.gz)", line)
        if not match or match[2] in hashes:
            raise VerificationError("manifest_invalid")
        hashes[match[2]] = match[1].lower()
    if set(hashes) != REQUIRED_FILES:
        raise VerificationError("manifest_incomplete")
    return hashes


def copy_checked(source: Path, destination: Path, expected: str, limit: int):
    digest, total = hashlib.sha256(), 0
    with read_regular(source, limit) as src, destination.open("xb") as dst:
        os.chmod(destination, 0o600)
        while chunk := src.read(1024 * 1024):
            total += len(chunk)
            if total > limit:
                raise VerificationError("input_size_exceeded")
            digest.update(chunk)
            dst.write(chunk)
    if digest.hexdigest() != expected:
        raise VerificationError("checksum_mismatch")


class ExpandedReader:
    """Bound decompression including PAX headers/padding, not only member sizes."""
    def __init__(self, handle):
        self.handle, self.total = handle, 0

    def read(self, size):
        chunk = self.handle.read(min(size, 1024 * 1024, MAX_EXPANDED_BYTES - self.total + 1))
        self.total += len(chunk)
        if self.total > MAX_EXPANDED_BYTES:
            raise VerificationError("archive_size_limit")
        return chunk


def inspect_archive(path: Path) -> dict:
    """Validate full archive contents without extracting any config/secret member."""
    names, total, regular = set(), 0, 0
    with gzip.open(path, "rb") as compressed:
        expanded = ExpandedReader(compressed)
        with tarfile.open(fileobj=expanded, mode="r|") as archive:
            for member in archive:
                name = member.name
                parts = PurePosixPath(name).parts
                if (not name or name.startswith("/") or "\\" in name or ":" in name
                        or any(part in {"", ".", ".."} for part in name.rstrip("/").split("/"))
                        or not parts or name.rstrip("/") in names):
                    raise VerificationError("archive_path_invalid")
                names.add(name.rstrip("/"))
                if len(names) > MAX_ARCHIVE_MEMBERS:
                    raise VerificationError("archive_member_limit")
                if not (member.isdir() or member.isreg()) or member.issparse() or (member.isdir() and member.size):
                    raise VerificationError("archive_member_type_invalid")
                if member.mode & 0o7000:
                    raise VerificationError("archive_special_permissions")
                total += member.size
                if member.size < 0 or total > MAX_EXPANDED_BYTES:
                    raise VerificationError("archive_size_limit")
                if member.isreg():
                    regular += 1
                    # Consume each member to catch truncation, never execute or extract.
                    with archive.extractfile(member) as handle:
                        remaining = member.size
                        while chunk := handle.read(min(1024 * 1024, remaining + 1)):
                            remaining -= len(chunk)
                            if remaining < 0:
                                raise VerificationError("archive_size_invalid")
                        if remaining:
                            raise VerificationError("archive_truncated")
        # Include metadata/trailing padding and force gzip CRC/truncation validation.
        while expanded.read(1024 * 1024):
            pass
    if not regular:
        raise VerificationError("archive_empty")
    return {"members": len(names), "expanded_bytes": expanded.total}


def open_database(path: Path):
    con = sqlite3.connect(path.resolve().as_uri() + "?mode=ro&immutable=1", uri=True)
    con.execute("PRAGMA trusted_schema=OFF")
    con.execute("PRAGMA query_only=ON")
    deadline = time.monotonic() + 30
    con.set_progress_handler(lambda: int(time.monotonic() > deadline), 10000)
    return con


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def verify_database(con) -> tuple[str, int]:
    if con.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
        raise VerificationError("sqlite_integrity_failed")
    if con.execute("PRAGMA foreign_key_check").fetchone():
        raise VerificationError("sqlite_foreign_key_failed")
    schema = con.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name").fetchall()
    if any(row[3] and "CREATE VIRTUAL TABLE" in row[3].upper() for row in schema):
        raise VerificationError("virtual_tables_unsupported")
    tables = {row[1] for row in schema if row[0] == "table"}
    if not REQUIRED_COLUMNS.keys() <= tables:
        raise VerificationError("required_schema_missing")
    for name, required in REQUIRED_COLUMNS.items():
        columns = {row[1] for row in con.execute(f"PRAGMA table_info({quote_identifier(name)})")}
        if not required <= columns:
            raise VerificationError("required_schema_missing")
    migrations = {row[0] for row in con.execute("SELECT version FROM schema_migrations")}
    if migrations != SUPPORTED_MIGRATIONS:
        raise VerificationError("schema_version_unsupported")
    for table in ("sessions", "devices", "account_settings", "moddns_mapping", "query_log_settings", "query_history"):
        if con.execute(f"SELECT 1 FROM {quote_identifier(table)} t LEFT JOIN users u ON u.sub=t.sub WHERE u.sub IS NULL LIMIT 1").fetchone():
            raise VerificationError("orphan_account_state")
    if con.execute("SELECT 1 FROM devices WHERE revoked IS NULL GROUP BY sub HAVING COUNT(*)>1 LIMIT 1").fetchone():
        raise VerificationError("duplicate_active_tokens")
    index = con.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name='one_active_account_token'").fetchone()
    indexes = {row[1]: row for row in con.execute('PRAGMA index_list("devices")')}
    active = indexes.get("one_active_account_token")
    index_columns = [row[2] for row in con.execute('PRAGMA index_info("one_active_account_token")')]
    if (not index or not index[0] or not active or active[2] != 1 or active[4] != 1
            or index_columns != ["sub"]
            or not re.search(r"WHERE\s+revoked\s+IS\s+NULL\s*$", index[0], re.I)):
        raise VerificationError("active_token_constraint_missing")
    # The digest stays in memory. Neither it nor row values are exposed in reports.
    digest = hashlib.sha256(repr(schema).encode())
    for name in sorted(tables):
        columns = con.execute(f"PRAGMA table_info({quote_identifier(name)})").fetchall()
        ordering = ",".join(str(index + 1) for index in range(len(columns)))
        digest.update(name.encode())
        for row in con.execute(f"SELECT * FROM {quote_identifier(name)} ORDER BY {ordering}"):
            digest.update(repr(row).encode())
            digest.update(b"\n")
    return digest.hexdigest(), len(tables)


def verify_bundle(bundle: Path) -> dict:
    """Read only the supplied offline bundle. Never touch DATA_DIR or live databases."""
    bundle = Path(bundle)
    if bundle.is_symlink() or not bundle.is_dir():
        raise VerificationError("bundle_directory_invalid")
    if any((bundle / suffix).exists() or (bundle / suffix).is_symlink()
           for suffix in ("dns.sqlite3-wal", "dns.sqlite3-shm", "dns.sqlite3-journal")):
        raise VerificationError("standalone_snapshot_required")
    manifest = read_manifest(bundle)
    # No destination argument: impossible to overwrite a selected runtime path.
    with tempfile.TemporaryDirectory(prefix="matchall-restore-rehearsal-") as temp:
        root = Path(temp)
        for name, limit in (("dns.sqlite3", MAX_DATABASE_BYTES), ("config.tar.gz", MAX_ARCHIVE_BYTES)):
            copy_checked(bundle / name, root / name, manifest[name], limit)
        archive = inspect_archive(root / "config.tar.gz")
        with closing(open_database(root / "dns.sqlite3")) as source:
            before, tables = verify_database(source)
            restored = root / "restored.sqlite3"
            with closing(sqlite3.connect(restored)) as target:
                os.chmod(restored, 0o600)
                source.backup(target)
        with closing(open_database(restored)) as target:
            after, _ = verify_database(target)
        if before != after:
            raise VerificationError("restored_state_mismatch")
    return {"schema_version": 1, "verified": True, "scope": "offline_sqlite_restore_and_archive_structure",
            "sqlite_integrity": "ok", "restored_state_equal": True, "schema_migrations": sorted(SUPPORTED_MIGRATIONS),
            "table_count": tables, "archive": archive, "temporary_copy_removed": True,
            "not_verified": ["source_authenticity", "backup_recency", "encryption_key_pairing",
                             "moddns_backend_restore", "off_host_recovery", "live_service_acceptance",
                             "multi_replica_safety"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", required=True, type=Path, help="Explicit offline bundle directory")
    args = parser.parse_args()
    try:
        report = verify_bundle(args.bundle)
    except VerificationError as exc:
        print(json.dumps({"verified": False, "reason": str(exc)}))
        return 1
    except (OSError, sqlite3.Error, tarfile.TarError, EOFError):
        print(json.dumps({"verified": False, "reason": "unreadable_or_invalid_bundle"}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
