"""History edge cases use synthetic SQLite data only; no service lifespan."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app


class PublicHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        database = patch.object(app, "STATUS_DB", Path(self.temp.name) / "status.db")
        database.start()
        self.addCleanup(database.stop)
        app.init_status_db()
        self.now = 2_000_000_000
        self.key = app.SERVICES[0]["key"]

    def history(self, days=3):
        with patch.object(app.time, "time", return_value=self.now):
            response = app.status_history(days)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.body)

    def check(self, key, when, ok=True):
        with app.status_db() as con:
            con.execute("INSERT INTO checks(service_key,checked_at,ok,latency_ms,status_code,detail) VALUES(?,?,?,?,?,?)",
                        (key, when, int(ok), 30, 200 if ok else 503, "synthetic"))

    def maintenance(self):
        with app.status_db() as con:
            con.execute("INSERT INTO maintenance(service_key,starts_at,ends_at,title,detail) VALUES(?,?,?,?,?)",
                        (self.key, self.now - 120, self.now + 120, "Synthetic maintenance", "Test only"))

    def assert_unknown_days(self, body):
        self.assertEqual(body["available_days"], 0)
        self.assertEqual(body["requested_days"], 3)
        self.assertEqual(len(body["services"]), len(app.SERVICES))
        for service in body["services"]:
            self.assertEqual(len(service["days"]), 3)
            for day in service["days"]:
                self.assertEqual(day["checks"], 0)
                self.assertIsNone(day["uptime"])
                self.assertIsNone(day["avg_latency"])

    def test_empty_database_returns_unknown_days_instead_of_500(self):
        body = self.history()
        self.assert_unknown_days(body)
        self.assertTrue(all(day["maintenance_minutes"] == 0 for service in body["services"] for day in service["days"]))

    def test_maintenance_without_samples_keeps_maintenance_coverage(self):
        self.maintenance()
        body = self.history()
        self.assert_unknown_days(body)
        service = next(item for item in body["services"] if item["key"] == self.key)
        self.assertEqual(service["days"][-1]["maintenance_minutes"], 2)

    def test_only_maintenance_samples_remain_excluded(self):
        self.maintenance()
        self.check(self.key, self.now - 60)
        body = self.history()
        self.assert_unknown_days(body)
        service = next(item for item in body["services"] if item["key"] == self.key)
        self.assertEqual(service["days"][-1]["maintenance_minutes"], 2)

    def test_removed_service_and_out_of_window_samples_are_not_eligible(self):
        self.check("removed-service", self.now - 10)
        self.check(self.key, self.now - 10 * 86400)
        self.assert_unknown_days(self.history())

    def test_existing_samples_keep_availability_and_missing_day_semantics(self):
        self.check(self.key, self.now - 10, True)
        self.check(self.key, self.now - 5, False)
        body = self.history()
        self.assertEqual(body["available_days"], 1)
        service = next(item for item in body["services"] if item["key"] == self.key)
        self.assertEqual(service["days"][-1]["checks"], 2)
        self.assertEqual(service["days"][-1]["uptime"], 50.0)
        self.assertEqual(service["days"][-1]["maintenance_minutes"], 0)
        self.assertIsNone(service["days"][0]["uptime"])
        self.assertEqual(service["days"][0]["checks"], 0)


if __name__ == "__main__":
    unittest.main()
