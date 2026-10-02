import asyncio
import hashlib
import hmac
import json
import os
import socket
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import httpx

_import_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _import_data.name
os.environ["SESSION_SECRET_FILE"] = str(Path(_import_data.name) / "missing-session-secret")

import app
import release_events
from fastapi.testclient import TestClient


class ReleaseEventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        config = patch.multiple(app, DATA_DIR=root, FILES_DIR=root / "files", DB_PATH=root / "mirror.db")
        config.start()
        self.addCleanup(config.stop)
        app.init_db()
        with app.db() as con:
            self.team = con.execute("INSERT INTO teams(slug,name,owner_sub,created_at) VALUES('synthetic-team','Test','owner',0)").lastrowid
            con.execute("INSERT INTO team_members(team_id,user_sub,role,created_at) VALUES(?,'owner','owner',0)", (self.team,))
            self.project_id = con.execute("""INSERT INTO projects(slug,name,summary,team_id,visibility,created_at,updated_at)
                VALUES('synthetic-project','合成项目','Synthetic fixture',?,'public',0,0)""", (self.team,)).lastrowid
            self.release_id = con.execute("""INSERT INTO releases(project_id,version,channel,published_at,status)
                VALUES(?,'1.0','stable',100,'published')""", (self.project_id,)).lastrowid
        self.client = AsyncMock()
        self.client.post.return_value = Mock(status_code=200)
        self.validate = Mock(side_effect=lambda value: value)

    def project(self):
        with app.db() as con:
            return dict(con.execute("SELECT * FROM projects WHERE id=?", (self.project_id,)).fetchone())

    def hook(self, *, active=1, events="release.published"):
        with app.db() as con:
            return con.execute("""INSERT INTO project_webhooks(project_id,url,secret,active,events,created_at)
                VALUES(?,'https://hook.example.invalid/events','synthetic-hook-key',?,?,0)""",
                (self.project_id, active, events)).lastrowid

    def queue(self, *, now=100, project=None, version="1.0", release_id=None):
        value = self.project() if project is None else project
        with app.db() as con:
            if release_id is None and version != "1.0":
                release_id = con.execute("""INSERT INTO releases(project_id,version,channel,published_at,status)
                    VALUES(?,?,'stable',?,'published')""", (self.project_id, version, now)).lastrowid
            return release_events.enqueue_release_event(con, value, release_id or self.release_id,
                version, "stable", "https://mirror.example.invalid", now)

    def rows(self):
        with app.db() as con:
            return [dict(row) for row in con.execute("SELECT * FROM release_event_outbox ORDER BY id")]

    def drain(self, now=100, *, client=None, secret="synthetic-hub-key", validate=None, limit=20):
        return asyncio.run(release_events.deliver_pending_events(app.db, client=self.client if client is None else client,
            hub_url="http://synthetic-hub.invalid/internal/events", hub_secret=lambda: secret,
            validate_url=self.validate if validate is None else validate, now=lambda: now, limit=limit))

    def private(self):
        with app.db() as con:
            con.execute("UPDATE projects SET visibility='private' WHERE id=?", (self.project_id,))

    def test_schema_migration_is_idempotent_and_preserves_delivery_history(self):
        hook = self.hook()
        with app.db() as con:
            con.execute("""INSERT INTO webhook_deliveries(webhook_id,event_id,event_type,status,status_code,error,created_at,sent_at)
                VALUES(?,'legacy-event','release.published','delivered',204,'',10,11)""", (hook,))
            before = [tuple(row) for row in con.execute("SELECT * FROM webhook_deliveries")]
            release = tuple(con.execute("SELECT * FROM releases WHERE id=?", (self.release_id,)).fetchone())
            release_events.ensure_schema(con)
            release_events.ensure_schema(con)
            self.assertEqual([tuple(row) for row in con.execute("SELECT * FROM webhook_deliveries")], before)
            self.assertEqual(tuple(con.execute("SELECT * FROM releases WHERE id=?", (self.release_id,)).fetchone()), release)
        self.assertEqual(self.queue(), 2)

    def test_public_event_is_unique_per_destination_and_preserves_exact_payload(self):
        self.hook()
        self.assertEqual(self.queue(), 2)
        rows = self.rows()
        self.assertEqual([row["destination_key"] for row in rows], ["hub", "webhook:1"])
        raw = rows[0]["payload"]
        self.assertIsInstance(raw, bytes)
        self.assertEqual(rows[1]["payload"], raw)
        event = json.loads(raw)
        self.assertEqual(event["id"], "release:synthetic-project:stable:1.0")
        self.assertEqual(event["audience"], "users")
        self.assertEqual(event["visibility"], "public")
        self.assertIn("合成项目", raw.decode("utf-8"))
        self.assertEqual(self.queue(now=999), 0)
        self.assertEqual([row["payload"] for row in self.rows()], [raw, raw])

    def test_private_event_reaches_only_project_hook(self):
        self.private()
        self.hook()
        self.assertEqual(self.queue(), 1)
        self.assertEqual(self.rows()[0]["destination_key"], "webhook:1")
        self.assertEqual(json.loads(self.rows()[0]["payload"])["audience"], "private")
        self.drain()
        self.client.post.assert_awaited_once()
        self.assertEqual(self.client.post.call_args.args[0], "https://hook.example.invalid/events")

    def test_unknown_visibility_fails_closed_for_hub(self):
        for visibility in (None, "unlisted", "", "PUBLIC"):
            with self.subTest(visibility=visibility):
                value = self.project()
                if visibility is None:
                    value.pop("visibility")
                else:
                    value["visibility"] = visibility
                self.assertEqual(self.queue(project=value), 0)
        self.assertEqual(self.rows(), [])

    def test_enqueue_uses_callers_transaction_and_rolls_back(self):
        with self.assertRaisesRegex(RuntimeError, "synthetic rollback"):
            with app.db() as con:
                con.execute("UPDATE releases SET status='draft' WHERE id=?", (self.release_id,))
                release_events.enqueue_release_event(con, self.project(), self.release_id, "1.0", "stable",
                    "https://mirror.example.invalid", 100)
                raise RuntimeError("synthetic rollback")
        self.assertEqual(self.rows(), [])
        with app.db() as con:
            self.assertEqual(con.execute("SELECT status FROM releases WHERE id=?", (self.release_id,)).fetchone()[0], "published")

    def test_approval_and_outbox_are_atomic_when_enqueue_fails(self):
        with app.db() as con:
            con.execute("UPDATE releases SET status='draft' WHERE id=?", (self.release_id,))
        client = TestClient(app.app)
        self.addCleanup(client.close)
        client.cookies.set("mirror_session", app.serializer.dumps({"sub": "owner", "csrf": "synthetic-csrf"}))
        def enqueue_then_fail(*args, **kwargs):
            release_events.enqueue_release_event(*args, **kwargs)
            raise sqlite3.OperationalError("synthetic queue failure")
        with patch.object(app, "enqueue_release_event", side_effect=enqueue_then_fail):
            with self.assertRaises(sqlite3.OperationalError):
                client.post(f"/developer/releases/{self.release_id}/approve", data={"csrf_token": "synthetic-csrf"})
        with app.db() as con:
            row = con.execute("SELECT status,approved_at FROM releases WHERE id=?", (self.release_id,)).fetchone()
            self.assertEqual(tuple(row), ("draft", None))
            self.assertEqual(con.execute("SELECT count(*) FROM audit_log WHERE action='release.approved'").fetchone()[0], 0)
        self.assertEqual(self.rows(), [])

    def test_failure_survives_fresh_connection_then_recovers_with_same_bytes_and_hmac(self):
        self.queue()
        raw = self.rows()[0]["payload"]
        self.client.post.return_value = Mock(status_code=503)
        result = self.drain()
        self.assertEqual(result["retried"], 1)
        first = self.rows()[0]
        self.assertEqual((first["status"], first["attempts"], first["next_attempt_at"]), ("pending", 1, 130))
        self.assertEqual(first["payload"], raw)
        self.assertEqual(self.drain(129)["claimed"], 0)
        recovered_client = AsyncMock()
        recovered_client.post.return_value = Mock(status_code=204)
        self.assertEqual(self.drain(130, client=recovered_client)["delivered"], 1)
        call = recovered_client.post.call_args
        self.assertEqual(call.kwargs["content"], raw)
        signature = hmac.new(b"synthetic-hub-key", raw, hashlib.sha256).hexdigest()
        self.assertEqual(call.kwargs["headers"]["x-matchall-signature"], f"sha256={signature}")
        final = self.rows()[0]
        self.assertEqual((final["status"], final["attempts"], final["payload"]), ("delivered", 2, b""))
        self.assertEqual(self.drain(10000)["claimed"], 0)

    def test_destination_failure_does_not_block_other_notifications(self):
        self.hook()
        self.queue()
        self.client.post.side_effect = [Mock(status_code=503), Mock(status_code=202)]
        result = self.drain()
        self.assertEqual((result["retried"], result["delivered"]), (1, 1))
        self.assertEqual([row["status"] for row in self.rows()], ["pending", "delivered"])
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM webhook_deliveries WHERE status='delivered'").fetchone()[0], 1)

    def test_http_exception_is_sanitized_and_keeps_retryable_payload(self):
        self.queue()
        raw = self.rows()[0]["payload"]
        self.client.post.side_effect = httpx.ConnectError("synthetic-secret https://private.invalid/account")
        result = self.drain()
        self.assertEqual(result["retried"], 1)
        row = self.rows()[0]
        self.assertEqual(row["payload"], raw)
        self.assertNotIn("synthetic-secret", row["last_error"])
        self.assertNotIn("private.invalid", row["last_error"])
        self.assertEqual(row["status_code"], 0)

    def test_lease_expiry_recovers_claim_and_stale_claimant_cannot_complete(self):
        self.queue()
        first = release_events.claim_event(app.db, 100)
        self.assertEqual(first["attempts"], 1)
        self.assertIsNone(release_events.claim_event(app.db, 159))
        second = release_events.claim_event(app.db, 160)
        self.assertEqual(second["id"], first["id"])
        self.assertEqual(second["attempts"], 2)
        self.assertNotEqual(second["claim_token"], first["claim_token"])
        self.assertIsNone(release_events._finish_event(app.db, first, now=161, outcome="delivered", status_code=200))
        self.assertEqual(self.rows()[0]["claim_token"], second["claim_token"])
        release_events._finish_event(app.db, second, now=162, outcome="delivered", status_code=200)
        self.assertEqual(self.rows()[0]["status"], "delivered")

    def test_concurrent_connections_claim_distinct_rows(self):
        self.hook()
        self.queue()
        barrier = threading.Barrier(2)
        def claim(_):
            barrier.wait()
            return release_events.claim_event(app.db, 100)
        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(claim, range(2)))
        self.assertEqual(len({row["id"] for row in claims}), 2)
        self.assertEqual([row["attempts"] for row in claims], [1, 1])
        self.assertIsNone(release_events.claim_event(app.db, 100))

    def test_retries_back_off_and_stop_after_eight_attempts(self):
        self.queue()
        self.client.post.return_value = Mock(status_code=503)
        now = 100
        for attempt in range(1, 9):
            with self.subTest(attempt=attempt):
                result = self.drain(now)
                self.assertEqual(result["claimed"], 1)
                row = self.rows()[0]
                self.assertEqual(row["attempts"], attempt)
                if attempt < 8:
                    self.assertEqual(row["status"], "pending")
                    self.assertEqual(row["next_attempt_at"] - now, min(3600, 30 * 2 ** (attempt - 1)))
                    now = row["next_attempt_at"]
                else:
                    self.assertEqual(row["status"], "failed")
                    self.assertEqual(result["failed"], 1)
        self.assertTrue(self.rows()[0]["payload"])
        self.assertEqual(self.drain(now + 100000)["claimed"], 0)
        self.assertEqual(self.client.post.await_count, 8)

    def test_missing_hub_secret_retries_without_unsigned_network_call(self):
        self.queue()
        self.assertEqual(self.drain(secret="")["retried"], 1)
        self.client.post.assert_not_awaited()
        self.assertEqual(self.rows()[0]["status"], "pending")

    def test_project_visibility_change_cancels_queued_public_event(self):
        self.hook()
        self.queue()
        self.private()
        result = self.drain()
        self.assertEqual(result["cancelled"], 2)
        self.client.post.assert_not_awaited()
        self.assertTrue(all(row["payload"] == b"" for row in self.rows()))

    def test_rolled_back_release_cancels_pending_event(self):
        self.queue()
        with app.db() as con:
            con.execute("UPDATE releases SET status='rolled_back',rolled_back_at=101 WHERE id=?", (self.release_id,))
        self.assertEqual(self.drain(101)["cancelled"], 1)
        self.client.post.assert_not_awaited()

    def test_disabled_deleted_and_unsubscribed_hooks_are_not_sent(self):
        for mutation in ("UPDATE project_webhooks SET active=0", "DELETE FROM project_webhooks",
                "UPDATE project_webhooks SET events='unrelated.event'"):
            with self.subTest(mutation=mutation):
                self.private()
                hook = self.hook()
                self.queue(version=f"case-{hook}")
                with app.db() as con:
                    con.execute(mutation + " WHERE id=?", (hook,))
                result = self.drain()
                self.assertEqual(result["cancelled"], 0 if mutation.startswith("DELETE") else 1)
        self.client.post.assert_not_awaited()

    def test_changed_webhook_uses_current_url_and_secret(self):
        self.private()
        hook = self.hook()
        self.queue()
        raw = self.rows()[0]["payload"]
        with app.db() as con:
            con.execute("UPDATE project_webhooks SET url='https://new-hook.example.invalid/events',secret='synthetic-rotated-key' WHERE id=?", (hook,))
        self.assertEqual(self.drain()["delivered"], 1)
        call = self.client.post.call_args
        self.assertEqual(call.args[0], "https://new-hook.example.invalid/events")
        self.validate.assert_called_once_with(call.args[0])
        signature = hmac.new(b"synthetic-rotated-key", raw, hashlib.sha256).hexdigest()
        self.assertEqual(call.kwargs["headers"]["x-matchall-signature"], f"sha256={signature}")

    def test_private_ip_dns_failure_and_invalid_scheme_are_guarded_at_delivery(self):
        cases = [("https://hook.example.invalid/events", [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]),
                 ("https://hook.example.invalid/events", socket.gaierror("synthetic DNS failure")),
                 ("http://hook.example.invalid/events", [])]
        for url, resolution in cases:
            with self.subTest(url=url, resolution=type(resolution).__name__):
                self.private()
                with app.db() as con:
                    con.execute("UPDATE project_webhooks SET active=0")
                hook = self.hook()
                self.queue(version=f"guard-{hook}")
                with app.db() as con:
                    con.execute("UPDATE project_webhooks SET url=? WHERE id=?", (url, hook))
                with patch.object(app.socket, "getaddrinfo", side_effect=resolution if isinstance(resolution, Exception) else None,
                        return_value=resolution if isinstance(resolution, list) else None):
                    result = self.drain(validate=app.validate_webhook_url)
                self.assertEqual(result["claimed"], 1)
                row = self.rows()[-1]
                self.assertEqual(row["last_error"], "webhook_resolution_failed" if isinstance(resolution, Exception) else "unsafe_webhook_url")
        self.client.post.assert_not_awaited()
        self.assertTrue(all(row["last_error"] and "synthetic DNS failure" not in row["last_error"] for row in self.rows()))

    def test_lost_claim_during_http_does_not_record_false_success(self):
        self.private()
        self.hook()
        self.queue()
        async def steal_claim(*args, **kwargs):
            with app.db() as con:
                con.execute("UPDATE release_event_outbox SET claim_token='synthetic-new-claim',leased_until=999 WHERE status='processing'")
            return Mock(status_code=200)
        self.client.post.side_effect = steal_claim
        self.assertEqual(self.drain()["lost_claim"], 1)
        row = self.rows()[0]
        self.assertEqual((row["status"], row["claim_token"]), ("processing", "synthetic-new-claim"))
        self.assertTrue(row["payload"])
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM webhook_deliveries").fetchone()[0], 0)

    def test_batch_limit_leaves_remaining_work_durable(self):
        self.private()
        self.hook()
        for index in range(5):
            self.queue(version=f"batch-{index}")
        result = self.drain(limit=2)
        self.assertEqual((result["claimed"], result["delivered"]), (2, 2))
        self.assertEqual([row["status"] for row in self.rows()].count("pending"), 3)
        self.assertEqual(self.drain()["delivered"], 3)

    def test_final_abandoned_attempt_becomes_failed_without_ninth_send(self):
        self.queue()
        with app.db() as con:
            con.execute("UPDATE release_event_outbox SET attempts=7")
        final = release_events.claim_event(app.db, 100)
        self.assertEqual(final["attempts"], 8)
        self.assertIsNone(release_events.claim_event(app.db, 160))
        row = self.rows()[0]
        self.assertEqual((row["status"], row["last_error"], row["attempts"]), ("failed", "lease_expired", 8))
        self.assertTrue(row["payload"])
        self.client.post.assert_not_awaited()

    def test_redirect_is_retryable_and_never_followed(self):
        self.queue()
        self.client.post.return_value = Mock(status_code=302)
        self.assertEqual(self.drain()["retried"], 1)
        self.assertIs(self.client.post.call_args.kwargs["follow_redirects"], False)
        self.assertEqual(self.rows()[0]["last_error"], "http_error")

    def test_lifespan_starts_worker_again_after_shutdown_and_cancels_it(self):
        async def run():
            started = []
            stopped = []
            async def worker():
                started.append(asyncio.current_task())
                try:
                    await asyncio.Event().wait()
                finally:
                    stopped.append(asyncio.current_task())
            with patch.object(app, "release_event_loop", side_effect=worker):
                for _ in range(2):
                    async with app.release_event_lifespan(app.app):
                        await asyncio.sleep(0)
                        self.assertEqual(len(started), len(stopped) + 1)
                    self.assertEqual(len(started), len(stopped))
            self.assertEqual(len(started), 2)
            self.assertIsNot(started[0], started[1])
            self.assertTrue(all(task.cancelled() for task in stopped))
        asyncio.run(run())

    def test_worker_retries_iteration_failures_and_closes_mocked_client_on_cancellation(self):
        async def run():
            entered = asyncio.Event()
            wait_forever = asyncio.Event()
            attempts = []
            async def deliver(*args, **kwargs):
                attempts.append(kwargs)
                if len(attempts) == 1:
                    raise RuntimeError("synthetic exception with private payload")
                entered.set()
                await wait_forever.wait()
            async def skip_pause(_):
                return None
            client = AsyncMock()
            client.__aenter__.return_value = client
            with patch.object(app.httpx, "AsyncClient", return_value=client), \
                    patch.object(app, "deliver_pending_events", side_effect=deliver), \
                    patch.object(app.asyncio, "sleep", side_effect=skip_pause), \
                    self.assertLogs(app.__name__, level="ERROR") as logs:
                worker = asyncio.create_task(app.release_event_loop())
                await asyncio.wait_for(entered.wait(), timeout=1)
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker
            self.assertEqual(len(attempts), 2)
            client.post.assert_not_awaited()
            client.__aexit__.assert_awaited_once()
            self.assertEqual(logs.output, [f"ERROR:{app.__name__}:Release event worker iteration failed"])
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
