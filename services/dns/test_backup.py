"""Exercise bundle generation with the existing synthetic restore fixture only."""
import importlib
import json
import sqlite3
import stat
from unittest.mock import patch

import pytest

import backup
import restore_verify
from test_restore_verify import bundle as restore_bundle

bundle = restore_bundle  # Reuse the existing synthetic schema/restore fixture.


def inputs(bundle, tmp_path):
    config = tmp_path / "synthetic-config"
    config.mkdir()
    (config / "settings.txt").write_text("synthetic secret fixture", encoding="utf-8")
    return bundle / "dns.sqlite3", config, tmp_path / "produced"


def test_import_has_no_io_or_umask_side_effects():
    with patch.object(backup.os, "umask", side_effect=AssertionError("umask")), \
         patch.object(backup.sqlite3, "connect", side_effect=AssertionError("database")), \
         patch.object(backup.Path, "mkdir", side_effect=AssertionError("mkdir")), \
         patch.object(backup.tarfile, "open", side_effect=AssertionError("archive")):
        importlib.reload(backup)


def test_generated_bundle_passes_existing_restore_verifier(bundle, tmp_path):
    database, config, output = inputs(bundle, tmp_path)
    original = database.read_bytes()
    published = backup.create_bundle(database, [config], output, name="synthetic-complete")
    assert set(path.name for path in published.iterdir()) == {"dns.sqlite3", "config.tar.gz", "SHA256SUMS"}
    assert restore_verify.verify_bundle(published)["restored_state_equal"]
    assert database.read_bytes() == original
    assert stat.S_IMODE(published.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in published.iterdir())
    assert not list(output.glob(".pending-*"))


@pytest.mark.parametrize("phase", ["snapshot", "archive_config", "write_manifest", "verify_bundle"])
def test_failure_never_publishes_or_leaves_staging(bundle, tmp_path, phase):
    database, config, output = inputs(bundle, tmp_path)
    with patch.object(backup, phase, side_effect=OSError("synthetic failure")):
        with pytest.raises(OSError):
            backup.create_bundle(database, [config], output, name="incomplete")
    assert not list(output.iterdir())
    assert database.is_file()


def test_missing_source_is_not_created(tmp_path):
    database = tmp_path / "missing.sqlite3"
    with pytest.raises(backup.BackupError, match="source_database_invalid"):
        backup.create_bundle(database, [tmp_path], tmp_path / "output")
    assert not database.exists()


def test_existing_destination_is_preserved(bundle, tmp_path):
    database, config, output = inputs(bundle, tmp_path)
    target = output / "existing"
    target.mkdir(parents=True)
    sentinel = target / "keep"
    sentinel.write_text("keep")
    with pytest.raises(backup.BackupError, match="bundle_already_exists"):
        backup.create_bundle(database, [config], output, name="existing")
    assert sentinel.read_text() == "keep"
    assert list(output.iterdir()) == [target]


@pytest.mark.parametrize("name", ["../escape", ".hidden", "a/b", ""])
def test_invalid_explicit_name_is_rejected(bundle, tmp_path, name):
    database, config, output = inputs(bundle, tmp_path)
    with pytest.raises(backup.BackupError, match="bundle_name_invalid"):
        backup.create_bundle(database, [config], output, name=name)


def test_config_symlink_is_rejected(bundle, tmp_path):
    database, config, output = inputs(bundle, tmp_path)
    (config / "unsafe").symlink_to(config / "settings.txt")
    with pytest.raises(backup.BackupError, match="configuration_member_type_invalid"):
        backup.create_bundle(database, [config], output)
    assert not list(output.iterdir())


def test_cli_failure_is_sanitized(bundle, tmp_path, capsys):
    database, config, output = inputs(bundle, tmp_path)
    with patch.object(backup, "write_manifest", side_effect=OSError("synthetic secret fixture")):
        code = backup.main(["--database", str(database), "--config", str(config), "--output", str(output)])
    assert code == 1
    result = capsys.readouterr()
    assert "synthetic secret fixture" not in result.out + result.err
    assert str(tmp_path) not in result.out + result.err
    assert json.loads(result.out)["reason"] == "backup_failed"


def test_live_wal_snapshot_keeps_committed_rows(bundle, tmp_path):
    database, config, output = inputs(bundle, tmp_path)
    with sqlite3.connect(database) as writer:
        writer.execute("PRAGMA journal_mode=WAL")
        writer.execute("INSERT INTO users VALUES('wal-fixture','Synthetic WAL',2)")
        writer.commit()
        published = backup.create_bundle(database, [config], output)
        with sqlite3.connect(published / "dns.sqlite3") as restored:
            assert restored.execute("SELECT name FROM users WHERE sub='wal-fixture'").fetchone() == ("Synthetic WAL",)
