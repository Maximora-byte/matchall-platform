"""Synthetic offline backup fixtures only; never import/run the production backup job."""
import hashlib
import io
import json
import sqlite3
import subprocess
import sys
import tarfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import pytest

import app as m
import restore_verify as verifier


def manifest(bundle):
    (bundle / "SHA256SUMS").write_text("".join(
        hashlib.sha256((bundle / name).read_bytes()).hexdigest() + "  " + name + "\n"
        for name in sorted(verifier.REQUIRED_FILES)))


def config_archive(bundle, entries=None):
    entries = entries or [("synthetic-config/settings.txt", b"synthetic fixture only")]
    with tarfile.open(bundle / "config.tar.gz", "w:gz") as archive:
        for name, value in entries:
            member = tarfile.TarInfo(name)
            if isinstance(value, bytes):
                member.size, member.mode = len(value), 0o600
                archive.addfile(member, io.BytesIO(value))
            else:
                member.type = value["type"]
                member.linkname = "../../outside"
                archive.addfile(member)
    manifest(bundle)


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    runtime = tmp_path / "synthetic-runtime"
    monkeypatch.setattr(m, "DATA", runtime)
    m.init_db()
    m.mg.migrate(m.db)
    m.moddns.migrate(m.db)
    m.qh.initialize(m.db)
    with m.db() as con:
        con.execute("INSERT INTO users VALUES('fixture-user','Synthetic',1)")
        con.execute("UPDATE account_settings SET enabled=0,qps=7,burst=9 WHERE sub='fixture-user'")
        con.execute("INSERT INTO devices(id,sub,label,token_hash,token_enc,created,revoked) VALUES('old','fixture-user','Fixture','old-hash','',1,2)")
        con.execute("INSERT INTO devices(id,sub,label,token_hash,token_enc,created) VALUES('active','fixture-user','Fixture','synthetic-hash','synthetic-not-a-real-token',3)")
        con.execute("INSERT INTO moddns_mapping(sub,state,routing,revision,personalized,updated) VALUES('fixture-user','error',1,7,1,3)")
        con.execute("INSERT INTO query_log_settings VALUES('fixture-user',1,0)")
        con.execute("INSERT INTO query_history(sub,timestamp,domain,qtype,outcome,rcode,latency_ms,route) VALUES('fixture-user',10,'private-fixture.invalid','A','response',0,1,'fixture')")
    result = tmp_path / "bundle"
    result.mkdir()
    with m.db() as source, closing(sqlite3.connect(result / "dns.sqlite3")) as target:
        source.backup(target)
    config_archive(result)
    return result


def test_offline_restore_preserves_state_and_leaves_source_untouched(bundle, tmp_path):
    before = {path.name: path.read_bytes() for path in bundle.iterdir()}
    with patch.object(verifier.tempfile, "tempdir", str(tmp_path)):
        report = verifier.verify_bundle(bundle)
    assert report["verified"] and report["restored_state_equal"] and report["temporary_copy_removed"]
    assert report["schema_migrations"] == [1, 2, 3, 4, 5]
    assert {path.name: path.read_bytes() for path in bundle.iterdir()} == before
    assert not list(tmp_path.glob("matchall-restore-rehearsal-*"))
    for private in ("fixture-user", "private-fixture.invalid", "synthetic-hash", "synthetic-not-a-real-token"):
        assert private not in json.dumps(report)
    assert "encryption_key_pairing" in report["not_verified"]
    assert "multi_replica_safety" in report["not_verified"]


def test_checksum_corruption_is_rejected(bundle):
    with (bundle / "dns.sqlite3").open("ab") as handle:
        handle.write(b"corruption")
    with pytest.raises(verifier.VerificationError, match="checksum_mismatch"):
        verifier.verify_bundle(bundle)


@pytest.mark.parametrize("contents", ["", "f" * 64 + "  ../dns.sqlite3\n",
                                      "f" * 64 + "  dns.sqlite3\n" * 2, "invalid\n"])
def test_missing_duplicate_or_path_manifest_is_rejected(bundle, contents):
    (bundle / "SHA256SUMS").write_text(contents)
    with pytest.raises(verifier.VerificationError, match="manifest_"):
        verifier.verify_bundle(bundle)


@pytest.mark.parametrize("name", ["../outside", "/absolute", "a/../../outside", "a\\outside", "a/./outside", "C:/outside"])
def test_archive_traversal_rejected_without_extraction(bundle, name):
    config_archive(bundle, [(name, b"private")])
    with pytest.raises(verifier.VerificationError, match="archive_path_invalid"):
        verifier.verify_bundle(bundle)
    assert not (bundle.parent / "outside").exists()


@pytest.mark.parametrize("member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE, tarfile.FIFOTYPE, tarfile.CHRTYPE])
def test_archive_links_and_devices_rejected(bundle, member_type):
    config_archive(bundle, [("link", {"type": member_type})])
    with pytest.raises(verifier.VerificationError, match="archive_member_type_invalid"):
        verifier.verify_bundle(bundle)


def test_archive_duplicate_paths_rejected(bundle):
    config_archive(bundle, [("duplicate", b"1"), ("duplicate", b"2")])
    with pytest.raises(verifier.VerificationError, match="archive_path_invalid"):
        verifier.verify_bundle(bundle)


def test_archive_and_database_resource_limits(bundle):
    with patch.object(verifier, "MAX_EXPANDED_BYTES", 1):
        with pytest.raises(verifier.VerificationError, match="archive_size_limit"):
            verifier.verify_bundle(bundle)
    with patch.object(verifier, "MAX_DATABASE_BYTES", 1):
        with pytest.raises(verifier.VerificationError, match="input_type_or_size_invalid"):
            verifier.verify_bundle(bundle)


def test_standalone_consistent_snapshot_required(bundle):
    (bundle / "dns.sqlite3-wal").write_bytes(b"uncheckpointed")
    with pytest.raises(verifier.VerificationError, match="standalone_snapshot_required"):
        verifier.verify_bundle(bundle)


def test_symlink_inputs_rejected(bundle):
    original = bundle / "dns.sqlite3"
    saved = bundle / "saved"
    original.rename(saved)
    original.symlink_to(saved)
    with pytest.raises(OSError):
        verifier.verify_bundle(bundle)


@pytest.mark.parametrize("sql,reason", [
    ("DELETE FROM schema_migrations WHERE version=5", "schema_version_unsupported"),
    ("DROP TABLE query_history", "required_schema_missing"),
    ("DROP INDEX one_active_account_token", "active_token_constraint_missing"),
    ("INSERT INTO moddns_mapping(sub,state,updated) VALUES('orphan','deleted',1)", "orphan_account_state"),
])
def test_incompatible_or_inconsistent_state_rejected(bundle, sql, reason):
    with closing(sqlite3.connect(bundle / "dns.sqlite3")) as con:
        con.execute(sql)
        con.commit()
    manifest(bundle)
    with pytest.raises(verifier.VerificationError, match=reason):
        verifier.verify_bundle(bundle)


def test_invalid_sqlite_rejected(bundle):
    (bundle / "dns.sqlite3").write_bytes(b"not a database")
    manifest(bundle)
    with pytest.raises(sqlite3.DatabaseError):
        verifier.verify_bundle(bundle)


def test_cli_reports_sanitized_failure_and_requires_explicit_bundle(bundle):
    script = str(Path(verifier.__file__))
    missing = subprocess.run([sys.executable, script], capture_output=True, text=True)
    assert missing.returncode == 2
    result = subprocess.run([sys.executable, script, "--bundle", str(bundle)], capture_output=True, text=True)
    assert result.returncode == 0 and json.loads(result.stdout)["verified"]
    (bundle / "dns.sqlite3").write_bytes(b"sensitive broken contents")
    result = subprocess.run([sys.executable, script, "--bundle", str(bundle)], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout) == {"verified": False, "reason": "checksum_mismatch"}
    assert str(bundle) not in result.stdout and "sensitive" not in result.stdout


def test_existing_single_worker_boundary_is_preserved():
    dockerfile = (Path(__file__).parent / "Dockerfile").read_text()
    assert '"--workers", "1"' in dockerfile


def test_restore_state_mismatch_fails_closed(bundle):
    original = verifier.verify_database
    calls = []
    def altered(con):
        fingerprint, tables = original(con)
        calls.append(1)
        return (fingerprint if len(calls) == 1 else "changed", tables)
    with patch.object(verifier, "verify_database", altered):
        with pytest.raises(verifier.VerificationError, match="restored_state_mismatch"):
            verifier.verify_bundle(bundle)



def test_truncated_compressed_archive_is_rejected_even_with_matching_checksum(bundle):
    archive = bundle / "config.tar.gz"
    archive.write_bytes(archive.read_bytes()[:-8])
    manifest(bundle)
    with pytest.raises((EOFError, tarfile.TarError)):
        verifier.verify_bundle(bundle)


def test_archive_metadata_counts_toward_expansion_limit(bundle):
    import gzip
    # Tar padding and extra compressed bytes cannot evade the member-size budget.
    archive = bundle / "config.tar.gz"
    data = gzip.decompress(archive.read_bytes())
    archive.write_bytes(gzip.compress(data + b"0" * 20000))
    manifest(bundle)
    with patch.object(verifier, "MAX_EXPANDED_BYTES", len(data) + 10000):
        with pytest.raises(verifier.VerificationError, match="archive_size_limit"):
            verifier.verify_bundle(bundle)
