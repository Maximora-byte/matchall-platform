import tempfile
import unittest
import json
from pathlib import Path

import app


class PublicStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_db = app.STATUS_DB
        app.STATUS_DB = Path(self.temp.name) / "status.db"
        app.init_status_db()
        self.service = next(item for item in app.SERVICES if item["key"] == "home")
        self.now = 2_000_000_000

    def tearDown(self):
        app.STATUS_DB = self.original_db
        self.temp.cleanup()

    def check(self, checked_at, ok, latency=30):
        with app.status_db() as con:
            con.execute("INSERT INTO checks(service_key,checked_at,ok,latency_ms,status_code,detail) VALUES(?,?,?,?,?,?)",
                        (self.service["key"], checked_at, int(ok), latency, 200 if ok else 503, ""))

    def state(self):
        with app.status_db() as con:
            return app.public_status(con, self.service, self.now)[0]

    def test_normal_and_degraded(self):
        self.check(self.now - 10, True)
        self.assertEqual(self.state(), "operational")
        self.check(self.now - 5, True, self.service["threshold"] + 1)
        self.assertEqual(self.state(), "degraded")

    def test_single_failure_is_partial_then_outage(self):
        self.check(self.now - 30, True)
        self.check(self.now - 10, False)
        self.assertEqual(self.state(), "partial_outage")
        self.check(self.now - 5, False)
        self.assertEqual(self.state(), "outage")

    def test_stale_and_missing_are_unknown_not_outage(self):
        self.assertEqual(self.state(), "unknown")
        self.check(self.now - app.STALE_AFTER_SECONDS - 1, True)
        self.assertEqual(self.state(), "unknown")

    def test_active_maintenance_takes_precedence(self):
        self.check(self.now - 5, True)
        with app.status_db() as con:
            con.execute("INSERT INTO maintenance(service_key,starts_at,ends_at,title,detail) VALUES(?,?,?,?,?)",
                        (self.service["key"], self.now - 60, self.now + 60, "计划维护", "只读演练"))
        self.assertEqual(self.state(), "maintenance")

    def test_no_history_uses_null_metrics(self):
        original_services = app.SERVICES
        try:
            app.SERVICES = [self.service]
            services, _ = app.status_summary(self.now)
            self.assertIsNone(services[0]["uptime"])
            self.assertIsNone(services[0]["uptime_30d"])
            self.assertIsNone(services[0]["avg_latency"])
            self.assertEqual(services[0]["sample_count_30d"], 0)
        finally:
            app.SERVICES = original_services

    def test_api_v2_keeps_legacy_fields(self):
        self.check(self.now - 5, True)
        original_services = app.SERVICES
        original_time = app.time.time
        try:
            app.SERVICES = [self.service]
            app.time.time = lambda: self.now
            response = app.status_api()
            body = __import__("json").loads(response.body)
            self.assertEqual(body["schema_version"], 2)
            self.assertIn("state", body["services"][0])
            self.assertIn("uptime", body["services"][0])
            self.assertIn("avg_latency", body["services"][0])
            self.assertEqual(body["services"][0]["status"], "operational")
        finally:
            app.time.time = original_time
            app.SERVICES = original_services

    def test_overall_priority_and_single_stale_service(self):
        self.assertEqual(app.overall_status([{"status": "operational"}, {"status": "unknown"}]), "unknown")
        self.assertEqual(app.overall_status([{"status": "maintenance"}, {"status": "outage"}]), "outage")
        self.assertEqual(app.overall_status([{"status": "unknown"}, {"status": "partial_outage"}]), "partial_outage")

    def test_page_refresh_does_not_refresh_probe(self):
        self.check(self.now - app.STALE_AFTER_SECONDS - 1, True)
        with app.status_db() as con:
            self.assertEqual(app.public_status(con, self.service, self.now)[0], "unknown")
            self.assertEqual(app.public_status(con, self.service, self.now + 500)[0], "unknown")

    def test_maintenance_samples_are_excluded_from_metrics(self):
        self.check(self.now - 120, False)
        self.check(self.now - 60, True, 40)
        with app.status_db() as con:
            con.execute("INSERT INTO maintenance(service_key,starts_at,ends_at,title,detail) VALUES(?,?,?,?,?)",
                        (self.service["key"], self.now - 180, self.now - 90, "维护", "窗口"))
        original_services = app.SERVICES
        try:
            app.SERVICES = [self.service]
            services, _ = app.status_summary(self.now)
            self.assertEqual(services[0]["sample_count_30d"], 1)
            self.assertEqual(services[0]["successful_samples_30d"], 1)
            self.assertEqual(services[0]["uptime_30d"], 100.0)
        finally:
            app.SERVICES = original_services

    def test_latency_requires_successful_sample(self):
        self.check(self.now - 10, False, 900)
        original_services = app.SERVICES
        try:
            app.SERVICES = [self.service]
            services, _ = app.status_summary(self.now)
            self.assertIsNone(services[0]["avg_latency"])
        finally:
            app.SERVICES = original_services

    def test_public_api_does_not_expose_probe_or_internal_details(self):
        self.check(self.now - 5, True)
        original_services, original_time = app.SERVICES, app.time.time
        try:
            app.SERVICES = [self.service]
            app.time.time = lambda: self.now
            body = json.loads(app.status_api().body)
            item = body["services"][0]
            self.assertNotIn("probe", item)
            self.assertNotIn("latest", item)
            self.assertNotIn("detail", item)
            self.assertNotIn("status_code", item)
            self.assertEqual(item["sample_count_30d"], item["successful_samples_30d"])
        finally:
            app.time.time, app.SERVICES = original_time, original_services


if __name__ == "__main__":
    unittest.main()
