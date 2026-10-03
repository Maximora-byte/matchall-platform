"""Offline collector regressions: synthetic databases only, never execute Docker."""
import contextlib
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote, urlsplit
from urllib.request import url2pathname

with patch("sqlite3.connect", side_effect=AssertionError("Unexpected import database access")), \
     patch("subprocess.run", side_effect=AssertionError("Unexpected import command")):
    import snapshot


SOURCES = ("xboard", "mirrors", "nextcloud")


class SnapshotCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root / "snapshots"
        self.now = 2_000_000_000
        self.clock = 100.0
        self.real_connect = sqlite3.connect
        self.real_mkstemp = tempfile.mkstemp
        self.mock_patch(snapshot, "OUT", self.output)
        self.mock_patch(snapshot, "XBOARD_DB", self.root / "xboard.sqlite")
        self.mock_patch(snapshot, "MIRROR_DB", self.root / "mirrors.sqlite")
        self.mock_patch(snapshot.time, "time", return_value=self.now)
        self.mock_patch(snapshot.time, "monotonic", side_effect=lambda: self.clock)
        self.connect = self.mock_patch(snapshot.sqlite3, "connect", side_effect=self.guarded_connect)
        self.mock_patch(snapshot.tempfile, "mkstemp", side_effect=self.synthetic_tempfile)
        self.chown = self.mock_patch(snapshot.os, "chown", create=True)
        self.run = self.mock_patch(snapshot.subprocess, "run", side_effect=AssertionError("Unmocked command"))

    def mock_patch(self, target, name, *args, **kwargs):
        patcher = patch.object(target, name, *args, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def guarded_connect(self, database, *args, **kwargs):
        raw = str(database)
        path = Path(url2pathname(unquote(urlsplit(raw).path))) if raw.startswith("file:") else Path(raw)
        self.assertTrue(path.resolve().is_relative_to(self.root.resolve()), "Unexpected database path")
        return self.real_connect(database, *args, **kwargs)

    def synthetic_tempfile(self, *args, **kwargs):
        kwargs.setdefault("dir", self.root)
        self.assertTrue(Path(kwargs["dir"]).resolve().is_relative_to(self.root.resolve()))
        return self.real_mkstemp(*args, **kwargs)

    def seed(self, path, script):
        with self.guarded_connect(path) as con:
            con.executescript(script)

    def payload(self, source):
        return json.loads((self.output / f"{source}.json").read_text(encoding="utf-8"))

    def mock_sources(self):
        return {name: self.mock_patch(snapshot, name, return_value=[{"username": f"synthetic-{name}"}]) for name in SOURCES}

    def assert_error(self, source, error_code):
        self.assertEqual(self.payload(source), {
            "generated_at": None, "users": [], "collection_state": "error",
            "attempted_at": self.now, "error_code": error_code,
        })

    def test_deadline_uses_monotonic_time_and_rejects_exhausted_budget(self):
        deadline = snapshot.Deadline(10)
        self.assertEqual(deadline.remaining(), 10)
        self.clock += 9.5
        self.assertFalse(deadline.expired())
        self.assertEqual(deadline.remaining(), 0.5)
        self.clock += 0.5
        self.assertTrue(deadline.expired())
        with self.assertRaises(snapshot.CollectionTimeout):
            deadline.remaining()

    def test_each_source_failure_is_isolated_and_next_run_recovers(self):
        callbacks = self.mock_sources()
        for failed in SOURCES:
            for callback in callbacks.values():
                callback.reset_mock()
                callback.side_effect = None
            callbacks[failed].side_effect = RuntimeError("synthetic private database detail")
            report = snapshot.collect_all()
            self.assertFalse(report["ok"])
            self.assertEqual(report["sources"][failed], {"state": "error", "error_code": "collection_failed"})
            self.assertNotIn("private", json.dumps(report))
            self.assert_error(failed, "collection_failed")
            for name in SOURCES:
                callbacks[name].assert_called_once()
                if name != failed:
                    self.assertEqual(self.payload(name), {"generated_at": self.now, "users": callbacks[name].return_value})
                    self.assertEqual(report["sources"][name], {"state": "ok", "error_code": None})
            callbacks[failed].side_effect = None
            self.assertTrue(snapshot.collect_all()["ok"])
            self.assertEqual(self.payload(failed), {"generated_at": self.now, "users": callbacks[failed].return_value})

    def test_source_failure_replaces_previous_success_without_old_rows(self):
        callbacks = self.mock_sources()
        self.assertTrue(snapshot.collect_all()["ok"])
        callbacks["xboard"].side_effect = snapshot.CollectionTimeout("synthetic sensitive timeout")
        report = snapshot.collect_all()
        self.assertEqual(report["sources"]["xboard"]["error_code"], "collection_timeout")
        self.assert_error("xboard", "collection_timeout")
        self.assertNotIn("synthetic-xboard", (self.output / "xboard.json").read_text(encoding="utf-8"))

    def test_late_source_result_is_not_published_as_success(self):
        callbacks = self.mock_sources()

        def late(*args, **kwargs):
            self.clock += 2
            return [{"username": "synthetic-late-user"}]

        callbacks["xboard"].side_effect = late
        report = snapshot.collect_all(source_timeout=1)
        self.assertFalse(report["ok"])
        self.assert_error("xboard", "collection_timeout")
        self.assertEqual(report["sources"]["mirrors"]["state"], "ok")
        self.assertEqual(report["sources"]["nextcloud"]["state"], "ok")

    def test_publication_failure_attempts_error_marker_and_continues(self):
        self.mock_sources()
        publish = snapshot.atomic_json
        calls = []

        def fail_first(name, payload):
            calls.append((name, payload))
            if len(calls) == 1:
                raise OSError("synthetic private mount path")
            publish(name, payload)

        self.mock_patch(snapshot, "atomic_json", side_effect=fail_first)
        report = snapshot.collect_all()
        self.assertFalse(report["ok"])
        self.assertEqual(report["sources"]["xboard"], {"state": "error", "error_code": "publication_failed"})
        self.assertEqual(len([call for call in calls if call[0] == "xboard"]), 2)
        self.assertEqual(self.payload("xboard")["collection_state"], "error")
        self.assertEqual(self.payload("xboard")["users"], [])
        self.assertIsNone(self.payload("xboard")["generated_at"])
        self.assertNotIn("private", json.dumps(report) + json.dumps(self.payload("xboard")))
        for name in ("mirrors", "nextcloud"):
            self.assertEqual(report["sources"][name]["state"], "ok")

    def test_repeated_publication_failure_is_bounded_and_does_not_stop_sources(self):
        callbacks = self.mock_sources()
        publish = self.mock_patch(snapshot, "atomic_json", side_effect=OSError("synthetic private error"))
        report = snapshot.collect_all()
        self.assertFalse(report["ok"])
        self.assertEqual(publish.call_count, 6)
        for name in SOURCES:
            callbacks[name].assert_called_once()
            self.assertEqual(report["sources"][name]["error_code"], "publication_failed")
        self.assertNotIn("private", json.dumps(report))

    def test_programmatic_limits_reject_invalid_types_and_values_before_collection(self):
        callbacks = self.mock_sources()
        for option, invalid in (("source_timeout", (0, -1, 901, True, 1.5, "120")),
                                ("command_timeout", (0, -1, 121, False, 1.5, "15"))):
            for value in invalid:
                with self.subTest(option=option, value=value), self.assertRaises(ValueError):
                    snapshot.collect_all(**{option: value})
        for callback in callbacks.values():
            callback.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_atomic_json_is_utf8_fsynced_and_owned_by_hub(self):
        events = []
        replace = snapshot.os.replace
        self.mock_patch(snapshot.os, "fsync", side_effect=lambda fd: events.append("fsync"))

        def recorded_replace(source, target):
            events.append("replace")
            return replace(source, target)

        self.mock_patch(snapshot.os, "replace", side_effect=recorded_replace)
        payload = {"users": [{"username": "合成用户", "display_name": "测试 ☁"}]}
        snapshot.atomic_json("nextcloud", payload)
        self.assertEqual(self.payload("nextcloud"), payload)
        self.assertIn("合成用户".encode(), (self.output / "nextcloud.json").read_bytes())
        self.assertLess(events.index("fsync"), events.index("replace"))
        self.chown.assert_called_once()
        self.assertEqual(self.chown.call_args.args[1:], (10001, 10001))
        self.assertEqual([p.name for p in self.output.iterdir()], ["nextcloud.json"])
        if os.name != "nt":
            self.assertEqual((self.output / "nextcloud.json").stat().st_mode & 0o777, 0o600)

    def test_atomic_json_failure_preserves_complete_previous_file_and_cleans_temp(self):
        original = {"generated_at": self.now - 100, "users": [{"username": "old"}]}
        snapshot.atomic_json("xboard", original)
        self.mock_patch(snapshot.os, "replace", side_effect=OSError("synthetic replace failure"))
        with self.assertRaises(OSError):
            snapshot.atomic_json("xboard", {"users": [{"username": "new"}]})
        self.assertEqual(self.payload("xboard"), original)
        self.assertEqual([p.name for p in self.output.iterdir()], ["xboard.json"])

    def test_atomic_json_ownership_failure_cleans_temp_and_does_not_publish(self):
        self.chown.side_effect = PermissionError("synthetic ownership failure")
        with self.assertRaises(PermissionError):
            snapshot.atomic_json("xboard", {"users": []})
        self.assertEqual(list(self.output.iterdir()), [])

    def test_missing_database_is_not_created(self):
        path = self.root / "missing.sqlite"
        with self.assertRaises((FileNotFoundError, sqlite3.OperationalError)):
            with snapshot.sqlite_snapshot(path, snapshot.Deadline(10)):
                self.fail("Missing source opened")
        self.assertFalse(path.exists())
        self.assertEqual(list(self.root.iterdir()), [])

    def test_sqlite_snapshot_copies_source_and_cleans_up_after_query_error(self):
        path = self.root / "source with spaces.sqlite"
        self.seed(path, "CREATE TABLE users(name TEXT); INSERT INTO users VALUES ('合成用户');")
        source_before = path.read_bytes()
        with self.assertRaises(sqlite3.OperationalError):
            with snapshot.sqlite_snapshot(path, snapshot.Deadline(10)) as con:
                self.assertEqual(con.execute("SELECT name FROM users").fetchone()["name"], "合成用户")
                con.execute("SELECT missing_column FROM users").fetchall()
        self.assertEqual(path.read_bytes(), source_before)
        self.assertEqual(list(self.root.iterdir()), [path])
        with self.assertRaises(sqlite3.ProgrammingError):
            con.execute("SELECT 1")

    def test_sqlite_backup_progress_enforces_deadline_and_cleans_temp(self):
        path = self.root / "large.sqlite"
        self.seed(path, "CREATE TABLE fixture(data BLOB); INSERT INTO fixture VALUES (zeroblob(2000000));")
        guarded_connect = self.guarded_connect
        testcase = self

        class SlowBackup:
            def __init__(self, con):
                self.con = con

            def __getattr__(self, name):
                return getattr(self.con, name)

            def backup(self, destination, *args, **kwargs):
                progress = kwargs["progress"]

                def expire_before_progress(*status):
                    testcase.clock += 20
                    return progress(*status)

                kwargs["progress"] = expire_before_progress
                return self.con.backup(destination, *args, **kwargs)

        def slow_connect(database, *args, **kwargs):
            con = guarded_connect(database, *args, **kwargs)
            return SlowBackup(con) if str(database).startswith("file:") else con

        self.connect.side_effect = slow_connect
        with self.assertRaises(snapshot.CollectionTimeout):
            with snapshot.sqlite_snapshot(path, snapshot.Deadline(10)):
                self.fail("Expired backup was yielded")
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_sqlite_query_progress_enforces_deadline_and_cleans_temp(self):
        path = self.root / "source.sqlite"
        self.seed(path, "CREATE TABLE fixture(value INTEGER);")
        with self.assertRaises(snapshot.CollectionTimeout):
            with snapshot.sqlite_snapshot(path, snapshot.Deadline(10)) as con:
                self.clock += 11
                con.execute("WITH RECURSIVE n(x) AS (VALUES(1) UNION ALL SELECT x+1 FROM n WHERE x<100000) SELECT sum(x) FROM n").fetchone()
        self.assertEqual(list(self.root.iterdir()), [path])

    def test_sqlite_collectors_preserve_existing_fields_without_publishing(self):
        self.seed(snapshot.XBOARD_DB, """
            CREATE TABLE v2_authentik_oidc_identities(subject TEXT, email TEXT, user_id INTEGER);
            CREATE TABLE v2_user(id INTEGER, email TEXT, banned INTEGER, t INTEGER, u INTEGER, d INTEGER,
                transfer_enable INTEGER, expired_at INTEGER, device_limit INTEGER, online_count INTEGER,
                last_online_at INTEGER, speed_limit INTEGER, plan_id INTEGER);
            CREATE TABLE v2_plan(id INTEGER, name TEXT, device_limit INTEGER);
            CREATE TABLE v2_order(user_id INTEGER, status INTEGER);
            INSERT INTO v2_authentik_oidc_identities VALUES ('synthetic-sub', 'fixture@example.invalid', 1);
            INSERT INTO v2_user VALUES (1, 'fixture@example.invalid', 0, 0, 12, 30, 1000, 2100000000, 0, NULL, 0, 0, 1);
            INSERT INTO v2_plan VALUES (1, '合成套餐', 2);
            INSERT INTO v2_order VALUES (1, 3), (1, 0);
        """)
        self.seed(snapshot.MIRROR_DB, """
            CREATE TABLE users(sub TEXT, username TEXT, email TEXT);
            CREATE TABLE orders(user_sub TEXT, status TEXT);
            CREATE TABLE entitlements(user_sub TEXT, active INTEGER, ends_at INTEGER);
            CREATE TABLE api_tokens(user_sub TEXT, revoked INTEGER, expires_at INTEGER);
            INSERT INTO users VALUES ('synthetic-sub', '合成用户', 'fixture@example.invalid');
            INSERT INTO orders VALUES ('synthetic-sub', 'paid'), ('synthetic-sub', 'pending');
            INSERT INTO entitlements VALUES ('synthetic-sub', 1, NULL), ('synthetic-sub', 0, NULL), ('synthetic-sub', 1, 1);
            INSERT INTO api_tokens VALUES ('synthetic-sub', 0, NULL), ('synthetic-sub', 1, NULL), ('synthetic-sub', 0, 1);
        """)
        network = snapshot.xboard(snapshot.Deadline(10), 5)
        self.assertEqual(len(network), 1)
        self.assertEqual(network[0]["used"], 42)
        self.assertEqual(network[0]["plan_name"], "合成套餐")
        self.assertEqual(network[0]["device_limit"], 2)
        self.assertEqual((network[0]["order_count"], network[0]["paid_orders"]), (2, 1))
        mirrors = snapshot.mirrors(snapshot.Deadline(10), 5)
        self.assertEqual(mirrors, [{"subject": "synthetic-sub", "username": "合成用户",
            "email": "fixture@example.invalid", "order_count": 2, "paid_orders": 1,
            "active_entitlements": 1, "active_tokens": 1}])
        self.assertFalse(self.output.exists())
        self.assertEqual(set(self.root.iterdir()), {snapshot.XBOARD_DB, snapshot.MIRROR_DB})

    def test_nextcloud_command_timeout_shrinks_to_remaining_source_budget(self):
        limits = []

        def respond(command, **kwargs):
            self.assertTrue(kwargs["check"])
            self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
            self.assertEqual(kwargs["stdout"], subprocess.PIPE)
            self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)
            self.assertEqual(kwargs["encoding"], "utf-8")
            limits.append(kwargs["timeout"])
            self.clock += 6
            data = {"合成用户": "Synthetic", "other": "Other"} if "user:list" in command else {
                "email": "fixture@example.invalid", "display_name": "合成 ☁", "enabled": True,
                "storage": {"used": 5, "quota": 100, "free": 95}, "last_seen": 0,
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")

        self.run.side_effect = respond
        users = snapshot.nextcloud(snapshot.Deadline(20), 15)
        self.assertEqual(limits, [15, 14, 8])
        self.assertEqual(len(users), 2)
        self.assertEqual(users[0]["username"], "合成用户")
        self.assertEqual(users[0]["display_name"], "合成 ☁")
        self.assertFalse(self.output.exists())

    def test_nextcloud_empty_user_list_is_a_complete_success(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])
        for raw in ("{}", "[]"):
            with self.subTest(raw=raw):
                self.run.reset_mock()
                self.run.side_effect = None
                self.run.return_value = subprocess.CompletedProcess([], 0, raw, "")
                report = snapshot.collect_all()
                self.assertTrue(report["ok"])
                self.assertEqual(self.payload("nextcloud"), {"generated_at": self.now, "users": []})
                self.run.assert_called_once()

    def test_nextcloud_malformed_listing_is_error_not_empty_success(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])
        for raw in ("null", "42", '"name"', '["name"]', '{"":"name"}', "{broken"):
            with self.subTest(raw=raw):
                self.run.reset_mock()
                self.run.side_effect = None
                self.run.return_value = subprocess.CompletedProcess([], 0, raw, "")
                report = snapshot.collect_all()
                self.assertFalse(report["ok"])
                self.assert_error("nextcloud", "collection_failed")
                self.run.assert_called_once()

    def test_nextcloud_malformed_info_rejects_whole_source(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])
        invalid = [None, [], "name", {}, {"storage": []}, {"storage": None},
                   {"storage": {"used": 0, "quota": 100}},
                   {"enabled": True}, {"enabled": True, "storage": {}},
                   {"enabled": True, "storage": {"used": 0}},
                   {"enabled": True, "storage": {"quota": 100}},
                   {"enabled": "true", "storage": {"used": 0, "quota": 100}},
                   {"enabled": 2, "storage": {"used": 0, "quota": 100}},
                   {"enabled": True, "storage": {"used": True, "quota": 100}},
                   {"enabled": True, "storage": {"used": -1, "quota": 100}},
                   {"enabled": True, "storage": {"used": "0", "quota": 100}},
                   {"enabled": True, "storage": {"used": 0, "quota": False}},
                   {"enabled": True, "storage": {"used": 0, "quota": "100"}}]
        for raw in [json.dumps(value) for value in invalid] + ["{broken"]:
            with self.subTest(raw=raw):
                self.run.side_effect = [
                    subprocess.CompletedProcess([], 0, '{"synthetic-user":"Synthetic"}', ""),
                    subprocess.CompletedProcess([], 0, raw, ""),
                ]
                report = snapshot.collect_all()
                self.assertFalse(report["ok"])
                self.assert_error("nextcloud", "collection_failed")

    def test_nextcloud_preserves_disabled_user_and_negative_quota(self):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, '{"synthetic-user":"Synthetic"}', ""),
            subprocess.CompletedProcess([], 0, '{"enabled":0,"storage":{"used":0,"quota":-3}}', ""),
        ]
        users = snapshot.nextcloud(snapshot.Deadline(10), 5)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["enabled"], 0)
        self.assertEqual(users[0]["used"], 0)
        self.assertEqual(users[0]["quota"], -3)
        self.assertFalse(self.output.exists())

    def test_nextcloud_exhausted_source_budget_does_not_start_another_command(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])

        def slow_listing(command, **kwargs):
            self.assertEqual(kwargs["timeout"], 1)
            self.clock += 2
            return subprocess.CompletedProcess(command, 0, '{"synthetic-user":"Synthetic"}', "")

        self.run.side_effect = slow_listing
        report = snapshot.collect_all(source_timeout=1)
        self.assertEqual(report["sources"]["nextcloud"]["error_code"], "collection_timeout")
        self.assert_error("nextcloud", "collection_timeout")
        self.run.assert_called_once()

    def test_nextcloud_does_not_publish_partial_users_after_later_command_failure(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])
        self.run.side_effect = [
            subprocess.CompletedProcess([], 0, '{"first":"First","second":"Second"}', ""),
            subprocess.CompletedProcess([], 0, '{"email":"first@example.invalid","enabled":true,"storage":{"used":5,"quota":100}}', ""),
            subprocess.CalledProcessError(1, ["synthetic-command"], stderr="synthetic private stderr"),
        ]
        report = snapshot.collect_all()
        self.assertEqual(self.run.call_count, 3)
        self.assertEqual(report["sources"]["nextcloud"]["error_code"], "collection_failed")
        self.assert_error("nextcloud", "collection_failed")
        self.assertNotIn("first@example.invalid", json.dumps(report) + json.dumps(self.payload("nextcloud")))
        self.assertNotIn("private", json.dumps(report) + json.dumps(self.payload("nextcloud")))

    def test_subprocess_timeout_is_reported_without_command_or_output_details(self):
        self.mock_patch(snapshot, "xboard", return_value=[])
        self.mock_patch(snapshot, "mirrors", return_value=[])
        self.run.side_effect = subprocess.TimeoutExpired(["synthetic-private-command"], 15, output="synthetic private output")
        report = snapshot.collect_all()
        self.assert_error("nextcloud", "collection_timeout")
        self.assertEqual(report["sources"]["nextcloud"]["error_code"], "collection_timeout")
        self.assertNotIn("private", json.dumps(report) + json.dumps(self.payload("nextcloud")))

    def test_cli_emits_only_sanitized_report_and_sets_exit_status(self):
        callbacks = self.mock_sources()
        for fail, expected in ((False, 0), (True, 1)):
            callbacks["xboard"].side_effect = RuntimeError("synthetic private traceback") if fail else None
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                status = snapshot.main(["--source-timeout", "12", "--command-timeout", "4"])
            self.assertEqual(status, expected)
            self.assertEqual(json.loads(stdout.getvalue())["ok"], not fail)
            self.assertEqual(stderr.getvalue(), "")
            self.assertNotIn("private", stdout.getvalue())

    def test_cli_invalid_limits_never_collect(self):
        callbacks = self.mock_sources()
        for args in (["--source-timeout", "0"], ["--source-timeout", "901"],
                     ["--command-timeout", "0"], ["--command-timeout", "121"],
                     ["--source-timeout", "1.5"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    snapshot.main(args)
                self.assertEqual(error.exception.code, 2)
        for callback in callbacks.values():
            callback.assert_not_called()
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
