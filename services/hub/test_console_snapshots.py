"""Offline Console regressions: never start lifespan or run the snapshot collector."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

import app


class ConsoleSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.snapshot_patch = patch.object(app, "SNAPSHOT_DIR", self.root)
        self.snapshot_patch.start()
        self.now = 2_000_000_000
        self.user = {"sub": "synthetic-sub", "preferred_username": "example", "email": "example@example.invalid", "name": "Example", "groups": []}
        self.records = {
            "drive": {"username": "example", "email": self.user["email"], "enabled": True, "used": 100, "quota": 1024},
            "network": {"subject": self.user["sub"], "banned": 0, "used": 10, "transfer_enable": 100, "expired_at": self.now + 1000, "online_count": 1, "device_limit": 2, "plan_name": "Synthetic plan"},
            "mirrors": {"subject": self.user["sub"], "active_entitlements": 2, "active_tokens": 1, "order_count": 3, "paid_orders": 2},
        }

    def tearDown(self):
        self.snapshot_patch.stop()
        self.temp.cleanup()

    def write(self, key, *, when=None, rows=None):
        source = app.CONSOLE_SOURCES[key]["snapshot"]
        (self.root / f"{source}.json").write_text(json.dumps({"generated_at": self.now if when is None else when, "users": [self.records[key]] if rows is None else rows}))

    def summary(self, key):
        return next(s for s in app.console_service_summaries(self.user, self.now) if s["key"] == key)

    def test_missing_is_unknown_not_unlinked(self):
        for source in app.console_service_summaries(self.user, self.now):
            self.assertEqual(source["state"], "missing")
            self.assertIsNone(source["generated_at"])
            self.assertIsNone(source["record"])
            self.assertFalse(source["fresh"])

    def test_existing_collector_format_links_each_service(self):
        for key in self.records:
            self.write(key)
            self.assertEqual(self.summary(key)["state"], "linked")
            self.assertTrue(self.summary(key)["fresh"])
            self.assertEqual(self.summary(key)["generated_at"], self.now)

    def test_unlinked_requires_fresh_complete_snapshot(self):
        self.write("drive", rows=[])
        self.assertEqual(self.summary("drive")["state"], "unlinked")
        self.write("drive", rows=[], when=self.now - app.SNAPSHOT_STALE_AFTER_SECONDS - 1)
        self.assertEqual(self.summary("drive")["state"], "stale")

    def test_stale_hides_record_and_keeps_original_timestamp(self):
        old = self.now - app.SNAPSHOT_STALE_AFTER_SECONDS - 1
        self.write("network", when=old)
        for _ in range(2):
            summary = self.summary("network")
            self.assertEqual(summary["state"], "stale")
            self.assertIsNone(summary["record"])
            self.assertEqual(summary["generated_at"], old)
        self.assertEqual(json.loads((self.root / "xboard.json").read_text())["generated_at"], old)

    def test_freshness_boundary(self):
        self.write("mirrors", when=self.now - app.SNAPSHOT_STALE_AFTER_SECONDS)
        self.assertEqual(self.summary("mirrors")["state"], "linked")
        self.write("mirrors", when=self.now - app.SNAPSHOT_STALE_AFTER_SECONDS - 1)
        self.assertEqual(self.summary("mirrors")["state"], "stale")

    def test_invalid_and_unreadable_payloads_are_sanitized_errors(self):
        for raw in ('{broken', '[]', '{}', '{"generated_at":1,"users":{}}', '{"generated_at":1,"users":[null]}', '{"generated_at":1,"users":[{"email":42}]}'):
            with self.subTest(raw=raw):
                (self.root / "nextcloud.json").write_text(raw)
                self.assertEqual(self.summary("drive")["state"], "error")
        with patch.object(Path, "read_text", side_effect=PermissionError("private mount detail")):
            self.assertEqual(self.summary("drive")["state"], "error")
            self.assertNotIn("private mount detail", str(self.summary("drive")))

    def test_invalid_or_future_timestamp_is_not_fresh(self):
        for timestamp in (0, -1, "2000000000", None, True, self.now + 61, 10**100):
            (self.root / "nextcloud.json").write_text(json.dumps({"generated_at": timestamp, "users": [self.records["drive"]]}))
            self.assertEqual(self.summary("drive")["state"], "error")
            self.assertFalse(self.summary("drive")["fresh"])

    def test_partial_or_malformed_rows_never_look_unlinked_or_zeroed(self):
        for key in self.records:
            for row in ({"username": "another-user"}, {**self.records[key], app.CONSOLE_SOURCES[key]["required_numbers"][0]: "invalid"}, {**self.records[key], app.CONSOLE_SOURCES[key]["required_numbers"][0]: None}):
                self.write(key, rows=[row])
                self.assertEqual(self.summary(key)["state"], "error")
                self.assertIsNone(self.summary(key)["record"])

    def test_restricted_is_not_normal(self):
        for key, field, value in (("drive", "enabled", False), ("network", "banned", 1)):
            self.records[key][field] = value
            self.write(key)
            self.assertEqual(self.summary(key)["state"], "restricted")

    def test_legacy_network_null_online_count_is_zero_not_source_error(self):
        self.records["network"]["online_count"] = None
        self.records["network"]["expired_at"] = None
        self.write("network")
        summary = self.summary("network")
        self.assertEqual(summary["state"], "linked")
        self.assertEqual(summary["record"]["online_count"], 0)
        self.assertEqual(summary["record"]["expired_at"], 0)
        with patch.object(app.time, "time", return_value=self.now):
            response = self.client(self.user).get("/console")
        self.assertIn("0/2 设备在线", response.text)
        self.assertNotIn('data-service="network" data-sync-state="error"', response.text)
        # Only the legacy explicit null is compatible; missing/malformed fields
        # must still fail closed rather than fabricate a current zero count.
        for value in ("0", False, -1):
            self.records["network"]["online_count"] = value
            self.write("network")
            self.assertEqual(self.summary("network")["state"], "error")
        del self.records["network"]["online_count"]
        self.write("network")
        self.assertEqual(self.summary("network")["state"], "error")

    def test_one_fresh_source_does_not_mask_missing_or_error_sources(self):
        self.write("drive")
        (self.root / "mirrors.json").write_text('broken')
        summaries = app.console_service_summaries(self.user, self.now)
        self.assertEqual(sum(item["fresh"] for item in summaries), 1)
        self.assertEqual([s["state"] for s in summaries], ["linked", "missing", "error"])

    def test_collector_failure_and_unknown_markers_hide_even_fresh_rows(self):
        for marker in ("error", "unknown", "ok", None, False, {}):
            with self.subTest(marker=marker):
                (self.root / "nextcloud.json").write_text(json.dumps({
                    "generated_at": self.now, "users": [self.records["drive"]],
                    "collection_state": marker, "attempted_at": self.now,
                    "error_code": "synthetic-private-exception-detail",
                }), encoding="utf-8")
                summary = self.summary("drive")
                self.assertEqual(summary["state"], "error")
                self.assertIsNone(summary["generated_at"])
                self.assertIsNone(summary["record"])
                self.assertFalse(summary["fresh"])
                self.assertNotIn("synthetic-private", str(summary))

    def test_collector_failure_is_not_unlinked_and_success_recovers(self):
        from snapshot import error_snapshot

        for key in self.records:
            self.write(key)
        (self.root / "xboard.json").write_text(
            json.dumps(error_snapshot("collection_timeout")), encoding="utf-8")
        summaries = app.console_service_summaries(self.user, self.now)
        self.assertEqual([s["state"] for s in summaries], ["linked", "error", "linked"])
        with patch.object(app.time, "time", return_value=self.now):
            response = self.client(self.user).get("/console")
        self.assertIn('data-service="network" data-sync-state="error"', response.text)
        self.assertNotIn("Synthetic plan", response.text)
        self.assertNotIn("collection_timeout", response.text)
        self.write("network")
        self.assertEqual(self.summary("network")["state"], "linked")

    def test_utf8_snapshot_preserves_non_ascii_account_data(self):
        self.records["network"]["plan_name"] = "合成套餐・テスト"
        (self.root / "xboard.json").write_text(json.dumps({
            "generated_at": self.now, "users": [self.records["network"]],
        }, ensure_ascii=False), encoding="utf-8")
        self.assertEqual(self.summary("network")["record"]["plan_name"], "合成套餐・テスト")

    def client(self, user):
        # TestClient without a context does not run lifespan/probes/delivery tasks.
        self.user_patch = patch.object(app, "get_user", return_value=user)
        self.addCleanup(self.user_patch.stop)
        self.user_patch.start()
        status_patch = patch.object(app, "status_summary", return_value=([], []))
        status_patch.start()
        self.addCleanup(status_patch.stop)
        return TestClient(app.app)

    def test_page_contains_per_source_times_dns_boundary_and_no_store(self):
        self.write("drive")
        with patch.object(app.time, "time", return_value=self.now):
            response = self.client(self.user).get("/console")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertIn("1/3 个来源在时效内", response.text)
        self.assertEqual(response.text.count("快照更新时间"), 4)
        self.assertIn('data-sync-state="not-integrated"', response.text)
        self.assertIn('href="https://dns.maximoraverse.org/login"', response.text)
        self.assertIn('href="https://dns.maximoraverse.org/guide"', response.text)
        self.assertNotIn('href="https://dns.maximoraverse.org/account"', response.text)
        self.assertNotIn("已保护", response.text)

    def test_anonymous_does_not_read_snapshots_or_expose_usage(self):
        with patch.object(app, "load_snapshot") as load:
            response = self.client(None).get("/console")
        load.assert_not_called()
        self.assertNotIn("Synthetic plan", response.text)
        self.assertIn('href="/login"', response.text)

    def test_no_matched_other_user_data_is_rendered_and_html_is_escaped(self):
        self.records["network"]["subject"] = "other-sub"
        self.write("network")
        self.records["drive"]["username"] = "other-user"
        self.records["drive"]["email"] = "other@example.invalid"
        self.write("drive")
        self.user["name"] = '<script>alert("test")</script>'
        with patch.object(app.time, "time", return_value=self.now):
            response = self.client(self.user).get("/console")
        self.assertNotIn("Synthetic plan", response.text)
        self.assertNotIn('<script>alert("test")</script>', response.text)
        self.assertIn("&lt;script&gt;", response.text)


if __name__ == "__main__":
    unittest.main()
