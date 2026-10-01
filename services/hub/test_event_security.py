"""Synthetic ingress and delivery regressions; no background/network delivery."""
import hashlib
import hmac
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

# Import must not look for a real session secret on the test machine.
with tempfile.TemporaryDirectory() as import_dir:
    with patch.dict(os.environ, {"SESSION_SECRET_FILE": str(Path(import_dir) / "missing-session-secret")}):
        import app


class EventSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.secret_file = self.root / "event-secret"
        self.secret = "synthetic-event-secret"
        self.secret_file.write_text(self.secret)
        token_file = self.root / "telegram-token"
        token_file.write_text("synthetic-telegram-token")
        chat_file = self.root / "telegram-chat"
        chat_file.write_text("synthetic-chat")
        settings = patch.multiple(
            app,
            NOTIFY_DB=self.root / "notifications.db",
            EVENT_SECRET_FILE=str(self.secret_file),
            TELEGRAM_BOT_TOKEN_FILE=str(token_file),
            TELEGRAM_CHAT_ID_FILE=str(chat_file),
            SMTP_HOST="smtp.example.invalid",
        )
        settings.start()
        self.addCleanup(settings.stop)
        app.init_notify_db()
        with app.notify_db() as con:
            for user in ("alice", "bob"):
                con.execute("""INSERT INTO notification_preferences
                    (user_sub,email,email_enabled,webpush_enabled,updated_at)
                    VALUES(?,?,1,1,1)""", (user, f"{user}@example.invalid"))
                con.execute("""INSERT INTO push_subscriptions
                    (user_sub,endpoint,p256dh,auth,active,created_at,updated_at)
                    VALUES(?,?,?, ?,1,1,1)""",
                    (user, f"https://push.example.invalid/{user}", "synthetic-p256dh", "synthetic-auth"))
        # ASGITransport does not start the lifespan probes/delivery worker.
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app.app), base_url="http://testserver")

    async def asyncTearDown(self):
        await self.client.aclose()

    def event(self, event_id="event-1", **extra):
        return {"id": event_id, "type": "release.published", "title": "Synthetic release", "body": "Test only", **extra}

    def encode(self, event):
        return json.dumps(event).encode()

    def signature(self, raw, secret=None):
        return hmac.new((self.secret if secret is None else secret).encode(), raw, hashlib.sha256).hexdigest()

    async def post_event(self, event, prefix="sha256="):
        raw = self.encode(event)
        return await self.client.post("/internal/events", content=raw,
            headers={"x-matchall-signature": prefix + self.signature(raw)})

    def assert_counts(self, notifications, jobs):
        with app.notify_db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], notifications)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM delivery_jobs").fetchone()[0], jobs)

    async def test_unconfigured_secret_rejects_empty_key_forgery_before_hmac(self):
        raw = self.encode(self.event())
        forged = self.signature(raw, secret="")
        for secret_contents in (None, "", " \n\t "):
            with self.subTest(secret_contents=secret_contents):
                if secret_contents is None:
                    self.secret_file.unlink(missing_ok=True)
                else:
                    self.secret_file.write_text(secret_contents)
                with patch.object(app.hmac, "new", side_effect=AssertionError("Unconfigured HMAC must not run")):
                    response = await self.client.post("/internal/events", content=raw,
                        headers={"x-matchall-signature": "sha256=" + forged})
                self.assertEqual(response.status_code, 503)
                self.assert_counts(0, 0)

    async def test_valid_signature_supports_existing_formats_and_stripped_secret(self):
        self.secret_file.write_text(f" \n{self.secret}\t\n")
        for index, prefix in enumerate(("sha256=", "")):
            with self.subTest(prefix=prefix):
                response = await self.post_event(self.event(f"format-{index}"), prefix=prefix)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), {"accepted": True})
        self.assert_counts(2, 10)

    async def test_invalid_and_missing_signatures_do_not_publish(self):
        raw = self.encode(self.event())
        for signature in (None, "", "sha256=" + "0" * 64, self.signature(raw, secret="wrong-secret")):
            with self.subTest(signature=signature):
                headers = {} if signature is None else {"x-matchall-signature": signature}
                response = await self.client.post("/internal/events", content=raw, headers=headers)
                self.assertEqual(response.status_code, 403)
                self.assert_counts(0, 0)

    async def test_signature_cannot_be_reused_for_modified_body(self):
        signature = self.signature(self.encode(self.event()))
        response = await self.client.post("/internal/events", content=self.encode(self.event(title="Changed")),
            headers={"x-matchall-signature": "sha256=" + signature})
        self.assertEqual(response.status_code, 403)
        self.assert_counts(0, 0)

    async def test_duplicate_valid_event_is_idempotent(self):
        for _ in range(2):
            response = await self.post_event(self.event())
            self.assertEqual(response.status_code, 200)
        self.assert_counts(1, 5)

    async def test_unsupported_audiences_are_rejected_without_delivery(self):
        for audience in ("private", "admins", "", None, [], {}):
            with self.subTest(audience=audience):
                response = await self.post_event(self.event(audience=audience))
                self.assertEqual(response.status_code, 400)
                self.assert_counts(0, 0)

    async def test_private_release_cannot_claim_broad_audience(self):
        for extra in ({}, {"audience": "users"}, {"audience": "public"}):
            with self.subTest(extra=extra):
                response = await self.post_event(self.event(visibility="private", **extra))
                self.assertEqual(response.status_code, 400)
                self.assert_counts(0, 0)

    async def test_supported_audiences_preserve_center_feed_and_delivery(self):
        for event_id, extra in (("legacy-default", {}), ("users", {"audience": "users", "visibility": "public"}),
                                ("public", {"audience": "public", "visibility": "public"})):
            response = await self.post_event(self.event(event_id, title=event_id, **extra))
            self.assertEqual(response.status_code, 200)
        self.assert_counts(3, 15)
        for user in ("alice", "bob"):
            self.assertEqual({row["event_key"] for row in app.notification_rows({"sub": user})},
                             {"legacy-default", "users", "public"})
        feed = app.notification_feed().body.decode()
        self.assertIn("<title>public</title>", feed)
        self.assertNotIn("<title>users</title>", feed)
        self.assertNotIn("<title>legacy-default</title>", feed)
        with app.notify_db() as con:
            self.assertEqual(dict(con.execute("SELECT channel,COUNT(*) FROM delivery_jobs GROUP BY channel")),
                             {"email": 6, "telegram": 3, "webpush": 6})

    def test_unsupported_stored_audiences_cannot_enqueue_or_display(self):
        for audience in ("private", "admins", ""):
            app.publish_notification(event_key=f"stored-{audience}", kind="event", severity="info",
                title="Hidden synthetic event", body="Not for broad delivery", audience=audience)
        self.assert_counts(3, 0)
        with app.notify_db() as con:
            for row in con.execute("SELECT id FROM notifications").fetchall():
                app.enqueue_delivery_jobs(con, row["id"])
            app.enqueue_delivery_jobs(con, 9999)
        self.assert_counts(3, 0)
        self.assertEqual(app.notification_rows({"sub": "alice"}), [])
        self.assertNotIn("Hidden synthetic event", app.notification_feed().body.decode())

    async def test_delivery_worker_skips_legacy_unsupported_jobs(self):
        for audience in ("private", "admins", "users", "public"):
            app.publish_notification(event_key=f"queued-{audience}", kind="event", severity="info",
                title=f"Queued {audience}", body="Test only", audience=audience, deliver_external=False)
        with app.notify_db() as con:
            for row in con.execute("SELECT id FROM notifications").fetchall():
                con.execute("""INSERT INTO delivery_jobs
                    (notification_id,channel,recipient,status,next_attempt_at,created_at)
                    VALUES(?,'telegram','synthetic-chat','pending',0,0)""", (row["id"],))
        deliver = AsyncMock()
        class EndIteration(Exception):
            pass
        with patch.object(app, "deliver_job", deliver), patch.object(app.asyncio, "sleep", side_effect=EndIteration):
            with self.assertRaises(EndIteration):
                await app.delivery_loop()
        self.assertEqual({call.args[0]["title"] for call in deliver.await_args_list}, {"Queued users", "Queued public"})
        with app.notify_db() as con:
            statuses = dict(con.execute("""SELECT n.audience,j.status FROM delivery_jobs j
                JOIN notifications n ON n.id=j.notification_id"""))
        self.assertEqual(statuses, {"private": "pending", "admins": "pending", "users": "sent", "public": "sent"})


if __name__ == "__main__":
    unittest.main()
