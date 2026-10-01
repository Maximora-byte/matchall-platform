"""Synthetic Hub session/account boundaries without probes or real delivery."""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

with tempfile.TemporaryDirectory() as import_dir:
    with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(Path(import_dir) / "missing-session-secret")}):
        import app

from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient


class AuthBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        settings = patch.multiple(app, NOTIFY_DB=root / "notifications.db", STATUS_DB=root / "status.db",
            SNAPSHOT_DIR=root / "snapshots", SMTP_HOST="smtp.example.invalid",
            VAPID_PUBLIC_KEY_FILE=str(root / "missing-vapid-public-key"))
        settings.start()
        self.addCleanup(settings.stop)
        app.init_notify_db()
        app.init_status_db()
        self.client = TestClient(app.app)  # No context manager: do not start background workers.
        self.addCleanup(self.client.close)
        network = patch.object(app.httpx, "AsyncClient", side_effect=AssertionError("Unexpected external call"))
        network.start()
        self.addCleanup(network.stop)
        self.now = int(time.time())
        self.users = {name: {"sub": name, "preferred_username": name, "email": f"{name}@example.invalid",
                            "groups": [], "csrf": f"csrf-{name}"} for name in ("alice", "bob")}

    def login(self, name, age=0):
        with patch("itsdangerous.timed.time.time", return_value=self.now - age):
            cookie = app.serializer.dumps(self.users[name])
        self.client.cookies.clear()
        self.client.cookies.set("console_session", cookie)

    def test_preferences_can_only_update_signed_in_account(self):
        with app.notify_db() as con:
            con.execute("""INSERT INTO notification_preferences
                (user_sub,email,email_enabled,webpush_enabled,updated_at)
                VALUES('alice','alice@example.invalid',0,0,0)""")
        self.login("bob")
        response = self.client.post("/notifications/preferences", data={"csrf_token": "csrf-bob",
            "email_enabled": "true", "user_sub": "alice", "email": "alice@example.invalid"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with app.notify_db() as con:
            rows = {row["user_sub"]: dict(row) for row in con.execute("SELECT * FROM notification_preferences")}
        self.assertEqual(rows["alice"]["email_enabled"], 0)
        self.assertEqual(rows["bob"]["email_enabled"], 1)
        self.assertEqual(rows["bob"]["email"], "bob@example.invalid")

    def test_read_receipts_are_scoped_to_current_account(self):
        app.publish_notification(event_key="synthetic", kind="announcement", severity="info",
            title="Test only", body="Synthetic notification", deliver_external=False)
        with app.notify_db() as con:
            notification = con.execute("SELECT id FROM notifications").fetchone()[0]
        self.login("alice")
        self.assertEqual(self.client.post(f"/notifications/{notification}/read",
            data={"csrf_token": "csrf-alice", "user_sub": "bob"}, follow_redirects=False).status_code, 303)
        self.assertEqual(app.notification_rows(self.users["alice"])[0]["is_read"], 1)
        self.assertEqual(app.notification_rows(self.users["bob"])[0]["is_read"], 0)

    def test_sessions_expire_and_tampered_cookies_cannot_mutate(self):
        self.login("alice", age=8 * 86400)
        self.assertEqual(self.client.post("/notifications/preferences", data={"csrf_token": "csrf-alice"}).status_code, 401)
        self.client.cookies.clear()
        self.client.cookies.set("console_session", "tampered.cookie")
        self.assertEqual(self.client.post("/notifications/preferences", data={"csrf_token": "csrf-alice"}).status_code, 401)
        with app.notify_db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM notification_preferences").fetchone()[0], 0)

    def test_wrong_or_missing_csrf_cannot_change_preferences(self):
        self.login("alice")
        for token in ("csrf-bob", ""):
            with self.subTest(token=token):
                self.assertEqual(self.client.post("/notifications/preferences", data={"csrf_token": token}).status_code, 403)
        with app.notify_db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM notification_preferences").fetchone()[0], 0)

    def test_non_admin_cannot_publish_announcements(self):
        self.login("alice")
        response = self.client.post("/notifications/admin", data={"csrf_token": "csrf-alice",
            "title": "Synthetic", "body": "Must not publish", "deliver_external": "true"})
        self.assertEqual(response.status_code, 403)
        with app.notify_db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM notifications").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM delivery_jobs").fetchone()[0], 0)

    def test_oidc_missing_expired_mismatched_and_tampered_state_never_exchanges_tokens(self):
        cases = ((None, "expected-state"), ("tampered.cookie", "expected-state"))
        for age, state in ((601, "expected-state"), (0, "other-state")):
            with patch("itsdangerous.timed.time.time", return_value=self.now - age):
                cookie = app.serializer.dumps({"state": "expected-state", "verifier": "synthetic-verifier"})
            cases += ((cookie, state),)
        for cookie, state in cases:
            with self.subTest(cookie=cookie, state=state):
                self.client.cookies.clear()
                if cookie:
                    self.client.cookies.set("console_oidc", cookie)
                response = self.client.get("/auth/callback", params={"code": "synthetic-code", "state": state})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("console_session", response.cookies)

    def test_console_selects_current_account_from_synthetic_snapshots(self):
        app.SNAPSHOT_DIR.mkdir()
        for service in ("xboard", "nextcloud", "mirrors"):
            records = [{"subject": user["sub"], "username": user["preferred_username"], "email": user["email"],
                        "marker": f"{service}-{name}", "used": 0, "quota": 100, "enabled": True,
                        "transfer_enable": 100, "expired_at": self.now + 3600, "online_count": 0,
                        "device_limit": 2, "banned": 0, "plan_name": "Synthetic plan",
                        "active_entitlements": 1, "active_tokens": 0, "order_count": 1, "paid_orders": 1}
                       for name, user in self.users.items()]
            (app.SNAPSHOT_DIR / f"{service}.json").write_text(json.dumps({"generated_at": self.now, "users": records}))
        def capture(name, request, **context):
            if "console_services" in context:
                records = {key: None for key in ("network", "drive", "mirrors")}
                records.update({item["key"]: item["record"] for item in context["console_services"]})
                return JSONResponse(records)
            return JSONResponse({key: context[key] for key in ("network", "drive", "mirrors")})
        with patch.object(app, "render", side_effect=capture):
            for name in ("alice", "bob"):
                with self.subTest(user=name):
                    self.login(name)
                    data = self.client.get("/console").json()
                    for key, service in (("network", "xboard"), ("drive", "nextcloud"), ("mirrors", "mirrors")):
                        self.assertEqual(data[key]["marker"], f"{service}-{name}")
            self.client.cookies.clear()
            self.assertEqual(self.client.get("/console").json(), {"network": None, "drive": None, "mirrors": None})


if __name__ == "__main__":
    unittest.main()
