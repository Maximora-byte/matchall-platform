import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import app


class StatusCorsTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app.app)

    def get_status(self, origin=None):
        headers = {"Origin": origin} if origin is not None else {}
        with patch.object(app, "status_summary", return_value=([], [])):
            return self.client.get("/api/status", headers=headers)

    def test_only_exact_landing_origins_can_read_public_summary_without_credentials(self):
        for origin in ("https://www.maximoraverse.org", "https://maximoraverse.org"):
            with self.subTest(origin=origin):
                response = self.get_status(origin)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers.get("access-control-allow-origin"), origin)
                self.assertNotIn("access-control-allow-credentials", response.headers)
                self.assertIn("Origin", response.headers["vary"].split(", "))
                self.assertEqual(response.json()["schema_version"], 2)

    def test_unknown_malformed_and_missing_origins_are_not_allowed_and_cache_varies(self):
        for origin in (None, "null", "https://example.com", "http://www.maximoraverse.org",
                       "https://www.maximoraverse.org.evil.test", "https://www.maximoraverse.org/",
                       "https://www.maximoraverse.org:443", "https://www.maximoraverse.org https://evil.test"):
            with self.subTest(origin=origin):
                response = self.get_status(origin)
                self.assertNotIn("access-control-allow-origin", response.headers)
                self.assertNotIn("access-control-allow-credentials", response.headers)
                self.assertEqual(response.headers["vary"], "Origin")

    def test_cors_does_not_expand_to_other_routes_or_methods(self):
        headers = {"Origin": "https://www.maximoraverse.org"}
        for method, path in (("GET", "/healthz"), ("POST", "/api/status"), ("OPTIONS", "/api/status"),
                             ("GET", "/api/not-a-status-route")):
            with self.subTest(method=method, path=path):
                response = self.client.request(method, path, headers=headers)
                self.assertNotIn("access-control-allow-origin", response.headers)
                self.assertNotIn("access-control-allow-credentials", response.headers)


if __name__ == "__main__":
    unittest.main()
