"""Explicit, private SQLite/config bundle producer; importing performs no backup."""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tarfile
import tempfile
import time
import uuid
from contextlib import closing
from pathlib import Path

from restore_verify import VerificationError, verify_bundle


class BackupError(ValueError):
    """Only fixed reason codes; paths, SQL rows and configuration stay private."""


def snapshot(database: Path, target: Path):
    if database.is_symlink() or not stat.S_ISREG(database.stat().st_mode):
        raise BackupError("source_database_invalid")
    # mode=ro must not create a missing source; do not use immutable=1 on a live WAL.
    with target.open("xb"):
        os.chmod(target, 0o600)
    deadline = time.monotonic() + 30

    def progress(_status, _remaining, _total):
        if time.monotonic() > deadline:
            raise BackupError("snapshot_timeout")

    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        source.execute("PRAGMA trusted_schema=OFF")
        with closing(sqlite3.connect(target)) as destination:
            source.backup(destination, pages=256, progress=progress, sleep=0.1)
            if destination.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
                raise BackupError("snapshot_integrity_failed")


def archive_config(sources: list[Path], target: Path):
    def review(member):
        if any(part in {"__pycache__", ".pytest_cache"} for part in Path(member.name).parts):
            return None
        if not (member.isdir() or member.isreg()) or member.issparse():
            raise BackupError("configuration_member_type_invalid")
        member.mode &= 0o777
        return member

    with target.open("xb") as handle:
        os.chmod(target, 0o600)
        with tarfile.open(fileobj=handle, mode="w:gz") as archive:
            for source in sources:
                if source.is_symlink() or not source.exists():
                    raise BackupError("configuration_source_invalid")
                archive.add(source, arcname=source.resolve().as_posix().lstrip("/"), filter=review)
        handle.flush()
        os.fsync(handle.fileno())


def write_manifest(stage: Path):
    lines = []
    for name in ("dns.sqlite3", "config.tar.gz"):
        digest = hashlib.sha256()
        with (stage / name).open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        lines.append(digest.hexdigest() + "  " + name + "\n")
    with (stage / "SHA256SUMS").open("x", encoding="ascii") as handle:
        os.chmod(handle.name, 0o600)
        handle.writelines(lines)
        handle.flush()
        os.fsync(handle.fileno())


def create_bundle(database: Path, configs: list[Path], output: Path, *, name: str | None = None) -> Path:
    """Publish only a complete, offline-verified bundle; never execute a restore."""
    database, output = Path(database), Path(output)
    configs = [Path(path) for path in configs]
    if not configs:
        raise BackupError("configuration_sources_required")
    if name is None:
        name = (datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                + "-" + uuid.uuid4().hex[:12])
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", name):
        raise BackupError("bundle_name_invalid")
    if database.is_symlink() or not database.is_file():
        raise BackupError("source_database_invalid")
    if output.is_symlink():
        raise BackupError("output_directory_invalid")
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    destination = output / name
    if destination.exists() or destination.is_symlink():
        raise BackupError("bundle_already_exists")
    # Consumers must ignore .pending-* and require the exact manifest.
    stage = Path(tempfile.mkdtemp(prefix=".pending-", dir=output))
    try:
        snapshot(database, stage / "dns.sqlite3")
        archive_config(configs, stage / "config.tar.gz")
        write_manifest(stage)
        verify_bundle(stage)
        for entry in stage.iterdir():
            with entry.open("rb") as handle:
                os.fsync(handle.fileno())
        fd = os.open(stage, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        if destination.exists() or destination.is_symlink():
            raise BackupError("bundle_already_exists")
        stage.rename(destination)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return destination


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--config", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--name", help="Optional new bundle name; never overwrite")
    args = parser.parse_args(argv)
    try:
        bundle = create_bundle(args.database, args.config, args.output, name=args.name)
    except (OSError, sqlite3.Error, tarfile.TarError, BackupError, VerificationError):
        print(json.dumps({"schema_version": 1, "created": False, "reason": "backup_failed"}))
        return 1
    print(json.dumps({"schema_version": 1, "created": True, "bundle": bundle.name}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
