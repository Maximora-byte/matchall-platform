"""Synthetic access, session and Stripe callback contracts; never calls a provider."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

_import_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _import_data.name
os.environ["SESSION_SECRET_FILE"] = str(Path(_import_data.name) / "missing-session-secret")

import app
from fastapi.testclient import TestClient


class AuthPaymentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.secret = "synthetic-stripe-webhook-secret"
        secret_file = root / "webhook-secret"
        secret_file.write_text(self.secret)
        config = patch.multiple(app, DATA_DIR=root, FILES_DIR=root / "files", DB_PATH=root / "mirror.db",
            STRIPE_WEBHOOK_SECRET_FILE=str(secret_file), STRIPE_SECRET_FILE=str(root / "missing-payment-secret"),
            STORAGE_PROVIDER="local", EDGE_DOWNLOAD_BASE="")
        config.start()
        self.addCleanup(config.stop)
        app.init_db()
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        network = patch.object(app.httpx, "AsyncClient", side_effect=AssertionError("Unexpected external call"))
        network.start()
        self.addCleanup(network.stop)
        self.now = int(time.time())
        self.users = {name: {"sub": name, "preferred_username": name, "email": f"{name}@example.invalid", "csrf": f"csrf-{name}"}
                      for name in ("alice", "bob", "viewer")}
        with app.db() as con:
            for user in self.users.values():
                app.upsert_user(con, user)
            self.product = con.execute("""INSERT INTO products(code,name,price_minor,currency,duration_days,created_at,updated_at)
                VALUES('test-plan','Synthetic plan',1500,'USD',30,?,?)""", (self.now, self.now)).lastrowid
            self.team = con.execute("INSERT INTO teams(slug,name,owner_sub,created_at) VALUES('test-team','Test','alice',?)", (self.now,)).lastrowid
            for name, role in (("alice", "owner"), ("viewer", "viewer")):
                con.execute("INSERT INTO team_members(team_id,user_sub,role,created_at) VALUES(?,?,?,?)", (self.team, name, role, self.now))
            self.projects = {}
            self.artifacts = {}
            for slug, visibility, access in (("paid-project", "public", "paid"), ("private-project", "private", "free")):
                project = con.execute("""INSERT INTO projects(slug,name,summary,visibility,access_mode,product_id,team_id,created_at,updated_at)
                    VALUES(?,?,'Synthetic test',?,?,?,?,?,?)""", (slug, slug, visibility, access, self.product, self.team, self.now, self.now)).lastrowid
                self.projects[slug] = project
                release = con.execute("INSERT INTO releases(project_id,version,channel,published_at,status) VALUES(?,'1.0','stable',?,'published')", (project, self.now)).lastrowid
                content = slug.encode()
                (app.FILES_DIR / f"{slug}.bin").write_bytes(content)
                self.artifacts[slug] = con.execute("""INSERT INTO artifacts(release_id,filename,local_path,size,sha256,created_at)
                    VALUES(?,?,?,?,?,?)""", (release, f"{slug}.bin", f"{slug}.bin", len(content), hashlib.sha256(content).hexdigest(), self.now)).lastrowid
            con.execute("""INSERT INTO orders(order_no,user_sub,product_id,amount_minor,currency,status,provider,provider_ref,created_at)
                VALUES('order-alice','alice',?,1500,'USD','pending','stripe','cs_synthetic',?)""", (self.product, self.now))

    def login(self, name, age=0):
        with patch("itsdangerous.timed.time.time", return_value=self.now - age):
            cookie = app.serializer.dumps(self.users[name])
        self.client.cookies.clear()
        self.client.cookies.set("mirror_session", cookie)

    def token(self, user="alice", expires_at=None, revoked=0):
        raw = f"mat_synthetic-{user}-{expires_at}-{revoked}"
        with app.db() as con:
            token_id = con.execute("INSERT INTO api_tokens(token_hash,user_sub,label,expires_at,revoked,created_at) VALUES(?,?,'test',?,?,?)",
                (hashlib.sha256(raw.encode()).hexdigest(), user, expires_at, revoked, self.now)).lastrowid
        return token_id, {"Authorization": f"Bearer {raw}"}

    def grant_alice(self):
        with app.db() as con:
            app.grant_product(con, "alice", self.product, "test", "alice-grant")

    def machine_download(self, slug):
        artifact = self.artifacts[slug]
        token = app.serializer.dumps({"purpose": "machine-download", "artifact_id": artifact})
        return self.client.get(f"/api/v1/download/{artifact}", params={"token": token}, follow_redirects=False)

    def order_state(self):
        with app.db() as con:
            order = dict(con.execute("SELECT * FROM orders WHERE order_no='order-alice'").fetchone())
            grants = [dict(row) for row in con.execute("SELECT * FROM entitlements WHERE source_type='order'")]
            events = con.execute("SELECT count(*) FROM webhook_events").fetchone()[0]
        return order, grants, events

    def stripe_event(self, event_id="evt_paid", payment_status="paid"):
        return {"id": event_id, "type": "checkout.session.completed", "data": {"object": {
            "id": "cs_synthetic", "mode": "payment", "payment_status": payment_status, "payment_intent": "pi_synthetic",
            "amount_total": 1500, "currency": "usd", "metadata": {"order_no": "order-alice", "user_sub": "alice"}}}}

    def post_stripe(self, event, *, timestamp=None, secret=None, signature=None):
        raw = json.dumps(event, separators=(",", ":")).encode()
        timestamp = self.now if timestamp is None else timestamp
        digest = hmac.new((self.secret if secret is None else secret).encode(), f"{timestamp}.".encode() + raw, hashlib.sha256).hexdigest()
        signature = f"t={timestamp},v1={digest}" if signature is None else signature
        return self.client.post("/webhooks/stripe", content=raw, headers={"stripe-signature": signature})

    def test_paid_access_is_bound_to_current_account(self):
        self.grant_alice()
        for name, expected in (("alice", 200), ("bob", 403)):
            with self.subTest(user=name):
                self.login(name)
                self.assertEqual(self.client.get("/api/v1/projects/paid-project/latest").status_code, expected)
                self.assertEqual(self.machine_download("paid-project").status_code, expected)

    def test_bearer_entitlements_do_not_cross_accounts(self):
        self.grant_alice()
        for name, expected in (("alice", 200), ("bob", 403)):
            with self.subTest(user=name):
                _, headers = self.token(user=name)
                self.assertEqual(self.client.get("/api/v1/projects/paid-project/latest", headers=headers).status_code, expected)

    def test_private_project_is_hidden_from_other_accounts_and_catalog(self):
        self.assertNotIn("private-project", {row["slug"] for row in self.client.get("/api/v1/projects").json()["data"]})
        for name, expected in (("alice", 200), ("viewer", 200), ("bob", 404)):
            with self.subTest(user=name):
                self.login(name)
                self.assertEqual(self.client.get("/api/v1/projects/private-project").status_code, expected)
                self.assertEqual(self.client.get("/api/v1/projects/private-project/latest").status_code, expected)
        self.assertEqual(self.machine_download("private-project").status_code, 403)

    def test_viewer_cannot_draft_or_approve_private_releases(self):
        self.login("viewer")
        response = self.client.post("/developer/releases", data={"csrf_token": "csrf-viewer",
            "project_slug": "private-project", "version": "2.0", "external_url": "https://example.invalid/test.zip"})
        self.assertEqual(response.status_code, 403)
        with app.db() as con:
            release = con.execute("INSERT INTO releases(project_id,version,channel,status,published_at) VALUES(?,'2.0','stable','draft',?)",
                (self.projects["private-project"], self.now)).lastrowid
        self.assertEqual(self.client.post(f"/developer/releases/{release}/approve", data={"csrf_token": "csrf-viewer"}).status_code, 403)

    def test_expired_and_revoked_bearer_tokens_are_not_used(self):
        self.grant_alice()
        for expires_at, revoked in ((self.now - 1, 0), (self.now, 0), (self.now + 3600, 1)):
            with self.subTest(expires_at=expires_at, revoked=revoked):
                token_id, headers = self.token(expires_at=expires_at, revoked=revoked)
                self.assertEqual(self.client.get("/api/v1/projects/paid-project/latest", headers=headers).status_code, 403)
                with app.db() as con:
                    self.assertIsNone(con.execute("SELECT last_used_at FROM api_tokens WHERE id=?", (token_id,)).fetchone()[0])

    def test_user_cannot_revoke_another_users_token(self):
        token_id, headers = self.token()
        self.login("bob")
        response = self.client.post(f"/account/tokens/{token_id}/revoke", data={"csrf_token": "csrf-bob"}, follow_redirects=False)
        self.assertEqual(response.status_code, 303)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT revoked FROM api_tokens WHERE id=?", (token_id,)).fetchone()[0], 0)
        self.login("alice")
        self.client.post(f"/account/tokens/{token_id}/revoke", data={"csrf_token": "csrf-alice"}, follow_redirects=False)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT revoked FROM api_tokens WHERE id=?", (token_id,)).fetchone()[0], 1)

    def test_expired_session_and_cross_account_csrf_cannot_mutate(self):
        self.login("alice", age=8 * 86400)
        self.assertEqual(self.client.post("/account/tokens", data={"csrf_token": "csrf-alice"}).status_code, 401)
        self.login("alice")
        self.assertEqual(self.client.post("/account/tokens", data={"csrf_token": "csrf-bob"}).status_code, 403)
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM api_tokens").fetchone()[0], 0)

    def test_tampered_session_does_not_authorize_mutation(self):
        self.client.cookies.set("mirror_session", "invalid.signed.cookie")
        self.assertEqual(self.client.post("/account/tokens", data={"csrf_token": "csrf-alice"}).status_code, 401)

    def test_oidc_expiry_and_state_mismatch_fail_before_token_exchange(self):
        for age, state in ((601, "expected-state"), (0, "other-state")):
            with self.subTest(age=age, state=state):
                with patch("itsdangerous.timed.time.time", return_value=self.now - age):
                    cookie = app.serializer.dumps({"state": "expected-state", "verifier": "synthetic-verifier", "next": "/account"})
                self.client.cookies.clear()
                self.client.cookies.set("mirror_oidc", cookie)
                response = self.client.get("/auth/callback", params={"code": "synthetic-code", "state": state})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("mirror_session", response.cookies)

    def test_valid_payment_grants_only_order_owner_and_duplicate_is_idempotent(self):
        self.login("bob")  # The webhook's browser session must not choose its beneficiary.
        event = self.stripe_event()
        self.assertEqual(self.post_stripe(event).json(), {"received": True})
        order, grants, events = self.order_state()
        self.assertEqual(order["status"], "paid")
        self.assertEqual(order["provider_ref"], "pi_synthetic")
        self.assertEqual([(grant["user_sub"], grant["active"]) for grant in grants], [("alice", 1)])
        self.assertEqual(events, 1)
        self.assertEqual(self.post_stripe(event).json(), {"received": True, "duplicate": True})
        self.assertEqual(self.order_state(), (order, grants, events))

    def test_unpaid_or_unrelated_events_do_not_grant_access(self):
        unpaid = self.stripe_event("evt_unpaid", payment_status="unpaid")
        unrelated = {"id": "evt_other", "type": "customer.updated", "data": {"object": {}}}
        for event in (unpaid, unrelated):
            self.assertEqual(self.post_stripe(event).status_code, 200)
        order, grants, events = self.order_state()
        self.assertEqual(order["status"], "pending")
        self.assertEqual(grants, [])
        self.assertEqual(events, 2)

    def test_missing_empty_or_whitespace_payment_secret_fails_closed(self):
        secret = Path(app.STRIPE_WEBHOOK_SECRET_FILE)
        for contents in (None, "", " \n\t"):
            with self.subTest(contents=contents):
                if contents is None:
                    secret.unlink(missing_ok=True)
                else:
                    secret.write_text(contents)
                response = self.post_stripe(self.stripe_event(), secret="")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(self.order_state()[1:], ([], 0))

    def test_invalid_stale_future_and_malformed_payment_signatures_are_rejected(self):
        # Stay well outside the five-minute tolerance so wall-clock progress
        # while the request is handled cannot turn a boundary case valid.
        cases = ({"secret": "wrong"}, {"timestamp": self.now - 3600}, {"timestamp": self.now + 3600},
                 {"signature": ""}, {"signature": "t=not-a-number,v1=bad"})
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                before = self.order_state()
                self.assertEqual(self.post_stripe(self.stripe_event(), **kwargs).status_code, 400)
                self.assertEqual(self.order_state(), before)

    def test_unknown_order_rolls_back_receipt_for_safe_retry(self):
        event = self.stripe_event()
        event["data"]["object"]["metadata"]["order_no"] = "missing-order"
        self.assertEqual(self.post_stripe(event).status_code, 404)
        self.assertEqual(self.order_state()[1:], ([], 0))
        event["data"]["object"]["metadata"]["order_no"] = "order-alice"
        self.assertEqual(self.post_stripe(event).status_code, 200)
        self.assertEqual(self.order_state()[0]["status"], "paid")

    def test_refund_revokes_only_matching_entitlement_and_is_idempotent(self):
        self.assertEqual(self.post_stripe(self.stripe_event()).status_code, 200)
        with app.db() as con:
            app.grant_product(con, "bob", self.product, "test", "unrelated")
        refund = {"id": "evt_refund", "type": "charge.refunded", "data": {"object": {"payment_intent": "pi_synthetic"}}}
        self.assertEqual(self.post_stripe(refund).status_code, 200)
        order, grants, events = self.order_state()
        self.assertEqual(order["status"], "refunded")
        self.assertEqual(grants[0]["active"], 0)
        self.assertEqual(events, 2)
        self.assertEqual(self.post_stripe(refund).json(), {"received": True, "duplicate": True})
        with app.db() as con:
            self.assertEqual(con.execute("SELECT active FROM entitlements WHERE user_sub='bob'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
