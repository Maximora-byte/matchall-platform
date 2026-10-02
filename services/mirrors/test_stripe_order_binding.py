"""Checkout binding tests use only synthetic signed events and mocked Stripe I/O."""
import hashlib
import hmac
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

_import_data = tempfile.TemporaryDirectory()
os.environ["DATA_DIR"] = _import_data.name
os.environ["SESSION_SECRET_FILE"] = str(Path(_import_data.name) / "missing-session-secret")

import app
from fastapi.testclient import TestClient


class StripeOrderBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.secret = "synthetic-signing-secret"
        (root / "webhook-secret").write_text(self.secret)
        (root / "stripe-secret").write_text("synthetic-api-secret")
        settings = patch.multiple(app, DATA_DIR=root, FILES_DIR=root / "files", DB_PATH=root / "mirror.db",
            STRIPE_WEBHOOK_SECRET_FILE=str(root / "webhook-secret"), STRIPE_SECRET_FILE=str(root / "stripe-secret"))
        settings.start()
        self.addCleanup(settings.stop)
        app.init_db()
        self.client = TestClient(app.app)
        self.addCleanup(self.client.close)
        network = patch.object(app.httpx, "AsyncClient", side_effect=AssertionError("Unexpected real network call"))
        network.start()
        self.addCleanup(network.stop)
        self.now = int(time.time())
        with app.db() as con:
            self.product = con.execute("""INSERT INTO products(code,name,price_minor,currency,duration_days,stripe_price_id,created_at,updated_at)
                VALUES('test-plan','Synthetic plan',1500,'USD',30,'price_synthetic',?,?)""", (self.now, self.now)).lastrowid
            con.execute("""INSERT INTO orders(order_no,user_sub,product_id,amount_minor,currency,status,provider,provider_ref,stripe_session_id,created_at)
                VALUES('order-alice','alice',?,1500,'USD','pending','stripe','cs_synthetic','cs_synthetic',?)""", (self.product, self.now))

    def event(self, event_id="evt_paid", **overrides):
        obj = {"id": "cs_synthetic", "object": "checkout.session", "mode": "payment", "payment_status": "paid",
            "payment_intent": "pi_synthetic", "amount_total": 1500, "currency": "usd", "client_reference_id": "order-alice",
            "metadata": {"order_no": "order-alice", "user_sub": "alice"}, **overrides}
        return {"id": event_id, "type": "checkout.session.completed", "data": {"object": obj}}

    def refund(self):
        return {"id": "evt_refund", "type": "charge.refunded", "data": {"object": {"payment_intent": "pi_synthetic"}}}

    def post(self, event):
        raw = json.dumps(event).encode()
        signature = hmac.new(self.secret.encode(), f"{self.now}.".encode() + raw, hashlib.sha256).hexdigest()
        return self.client.post("/webhooks/stripe", content=raw, headers={"stripe-signature": f"t={self.now},v1={signature}"})

    def state(self):
        with app.db() as con:
            order = dict(con.execute("SELECT * FROM orders WHERE order_no='order-alice'").fetchone())
            grants = [dict(row) for row in con.execute("SELECT * FROM entitlements WHERE source_ref='order-alice'")]
            events = con.execute("SELECT count(*) FROM webhook_events").fetchone()[0]
        return order, grants, events

    def update_order(self, **fields):
        with app.db() as con:
            con.execute("UPDATE orders SET " + ",".join(f"{field}=?" for field in fields) + " WHERE order_no='order-alice'", tuple(fields.values()))

    def assert_rejected_unchanged(self, event, status=400):
        before = self.state()
        response = self.post(event)
        self.assertEqual(response.status_code, status)
        self.assertEqual(self.state(), before)

    def test_valid_session_keeps_binding_and_different_event_duplicate_never_renews(self):
        self.assertEqual(self.post(self.event()).status_code, 200)
        order, grants, _ = self.state()
        self.assertEqual((order["status"], order["provider_ref"], order["stripe_session_id"]), ("paid", "pi_synthetic", "cs_synthetic"))
        self.assertEqual([(g["user_sub"], g["active"]) for g in grants], [("alice", 1)])
        self.assertEqual(self.post(self.event()).json(), {"received": True, "duplicate": True})
        self.assertEqual(self.post(self.event("evt_other_delivery")).status_code, 200)
        self.assertEqual(self.state()[:2], (order, grants))
        self.assertEqual(self.state()[2], 2)

    def test_amount_requires_exact_integer_order_total(self):
        for amount in (None, 1, 1501, -1500, "1500", 1500.0, True):
            with self.subTest(amount=amount):
                self.assert_rejected_unchanged(self.event(amount_total=amount))

    def test_currency_and_mode_must_match_fixed_price_payment(self):
        for fields in ({"currency": "eur"}, {"currency": None}, {"currency": ""}, {"mode": "subscription"}, {"mode": None}):
            with self.subTest(fields=fields):
                self.assert_rejected_unchanged(self.event(**fields))

    def test_checkout_session_cannot_be_rebound(self):
        for session in ("cs_other", "", None, {"id": "cs_synthetic"}):
            with self.subTest(session=session):
                self.assert_rejected_unchanged(self.event(id=session))

    def test_owner_and_order_references_must_agree(self):
        for fields in ({"metadata": {"order_no": "order-alice", "user_sub": "bob"}},
                       {"metadata": {"order_no": "order-alice"}}, {"metadata": []},
                       {"client_reference_id": "other-order"}):
            with self.subTest(fields=fields):
                self.assert_rejected_unchanged(self.event(**fields))
        self.update_order(provider="manual")
        self.assert_rejected_unchanged(self.event())

    def test_client_reference_fallback_remains_bound_to_owner_and_session(self):
        event = self.event(metadata={"user_sub": "alice"})
        self.assertEqual(self.post(event).status_code, 200)
        self.assertEqual(self.state()[0]["status"], "paid")

    def test_missing_payment_intent_rejected_and_expanded_intent_supported(self):
        for intent in (None, "", {}, {"id": None}):
            with self.subTest(intent=intent):
                self.assert_rejected_unchanged(self.event(payment_intent=intent))
        self.assertEqual(self.post(self.event(payment_intent={"id": "pi_synthetic", "object": "payment_intent"})).status_code, 200)

    def test_payment_intent_cannot_grant_two_orders(self):
        with app.db() as con:
            con.execute("""INSERT INTO orders(order_no,user_sub,product_id,amount_minor,currency,status,provider,provider_ref,created_at)
                VALUES('other-order','bob',?,1500,'USD','paid','stripe','pi_synthetic',?)""", (self.product, self.now))
        self.assert_rejected_unchanged(self.event())

    def test_binding_race_rolls_back_receipt_and_allows_retry(self):
        self.update_order(provider_ref="", stripe_session_id="")
        self.assert_rejected_unchanged(self.event(), status=409)
        self.update_order(provider_ref="cs_synthetic", stripe_session_id="cs_synthetic")
        self.assertEqual(self.post(self.event()).status_code, 200)
        self.assertEqual(self.state()[0]["status"], "paid")

    def test_failed_order_cannot_be_fulfilled(self):
        self.update_order(status="failed")
        self.assert_rejected_unchanged(self.event(), status=409)

    def test_legacy_pending_session_is_backfilled_without_changing_payment_state(self):
        with app.db() as con:
            con.execute("ALTER TABLE orders DROP COLUMN stripe_session_id")
        app.init_db()
        app.init_db()
        order, grants, events = self.state()
        self.assertEqual(order["stripe_session_id"], "cs_synthetic")
        self.assertEqual((order["status"], grants, events), ("pending", [], 0))
        self.assertEqual(self.post(self.event()).status_code, 200)

    def test_legacy_paid_retry_is_acknowledged_without_regranting(self):
        self.assertEqual(self.post(self.event()).status_code, 200)
        self.update_order(stripe_session_id="")
        before = self.state()[:2]
        self.assertEqual(self.post(self.event("evt_legacy_retry")).status_code, 200)
        self.assertEqual(self.state()[:2], before)
        self.assert_rejected_unchanged(self.event("evt_wrong_intent", payment_intent="pi_other"))

    def test_unpaid_then_async_success_uses_same_binding_checks(self):
        self.assertEqual(self.post(self.event("evt_unpaid", payment_status="unpaid")).status_code, 200)
        self.assertEqual(self.state()[0]["status"], "pending")
        event = self.event("evt_async")
        event["type"] = "checkout.session.async_payment_succeeded"
        self.assertEqual(self.post(event).status_code, 200)
        self.assertEqual(self.state()[0]["status"], "paid")

    def test_refund_before_completion_is_retryable_and_late_completion_cannot_regrant(self):
        self.assert_rejected_unchanged(self.refund(), status=409)
        self.assertEqual(self.post(self.event()).status_code, 200)
        self.assertEqual(self.post(self.refund()).status_code, 200)
        order, grants, _ = self.state()
        self.assertEqual(order["status"], "refunded")
        self.assertEqual(grants[0]["active"], 0)
        self.assertEqual(self.post(self.event("evt_late_completion")).status_code, 200)
        self.assertEqual(self.state()[:2], (order, grants))

    def test_unbound_refund_cannot_touch_manual_order(self):
        self.update_order(provider="manual", provider_ref="pi_synthetic")
        self.assert_rejected_unchanged(self.refund(), status=409)
        event = self.refund()
        event["data"]["object"]["payment_intent"] = ""
        self.assert_rejected_unchanged(event)

    def test_malformed_signed_event_does_not_save_receipt(self):
        for event in ([], {}, {"id": "", "type": "event", "data": {"object": {}}},
                      {"id": "evt_bad", "type": "event", "data": []},
                      {"id": "evt_bad", "type": "event", "data": {"object": None}}):
            with self.subTest(event=event):
                self.assert_rejected_unchanged(event)

    def test_grant_failure_rolls_back_order_and_receipt_for_retry(self):
        before = self.state()
        with patch.object(app, "grant_product", side_effect=RuntimeError("synthetic database failure")):
            with self.assertRaises(RuntimeError):
                self.post(self.event())
        self.assertEqual(self.state(), before)
        self.assertEqual(self.post(self.event()).status_code, 200)

    def checkout(self, *, provider_response=None, **fields):
        self.client.cookies.set("mirror_session", app.serializer.dumps({"sub": "bob", "preferred_username": "bob", "csrf": "csrf-bob"}))
        payload = {"id": "cs_created", "amount_total": 1500, "currency": "usd", "url": "https://checkout.example.invalid/session", **fields}
        provider = AsyncMock()
        provider.__aenter__.return_value = provider
        provider.post.return_value = provider_response if provider_response is not None else Mock(status_code=200, json=lambda: payload)
        with patch.object(app.httpx, "AsyncClient", return_value=provider):
            response = self.client.post(f"/checkout/{self.product}", data={"csrf_token": "csrf-bob"}, follow_redirects=False)
        with app.db() as con:
            order = dict(con.execute("SELECT * FROM orders WHERE user_sub='bob' ORDER BY id DESC").fetchone())
        return response, order, provider

    def test_checkout_persists_session_without_changing_owner_metadata(self):
        response, order, provider = self.checkout()
        self.assertEqual(response.status_code, 303)
        self.assertEqual((order["provider_ref"], order["stripe_session_id"]), ("cs_created", "cs_created"))
        sent = provider.post.call_args.kwargs["data"]
        self.assertEqual(sent["metadata[order_no]"], order["order_no"])
        self.assertEqual(sent["client_reference_id"], order["order_no"])
        self.assertEqual(sent["metadata[user_sub]"], "bob")

    def test_checkout_price_mismatch_stops_before_redirecting_customer(self):
        for fields in ({"amount_total": 1}, {"currency": "eur"}, {"id": None}):
            with self.subTest(fields=fields):
                response, order, _ = self.checkout(**fields)
                self.assertEqual(response.status_code, 502)
                self.assertNotIn("location", response.headers)
                self.assertEqual(order["status"], "failed")

    def assert_checkout_failed_without_binding(self, response, order):
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("location", response.headers)
        self.assertEqual((order["status"], order["provider_ref"], order["stripe_session_id"]), ("failed", "", ""))
        with app.db() as con:
            self.assertEqual(con.execute("SELECT count(*) FROM entitlements WHERE user_sub='bob'").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT count(*) FROM webhook_events").fetchone()[0], 0)

    def test_checkout_non_json_response_fails_without_saving_session(self):
        for body in ("<html>Bad gateway</html>", "", "{invalid"):
            with self.subTest(body=body):
                response, order, _ = self.checkout(provider_response=app.httpx.Response(200, text=body))
                self.assert_checkout_failed_without_binding(response, order)
        response, order, _ = self.checkout(provider_response=app.httpx.Response(200, content=b"\xff"))
        self.assert_checkout_failed_without_binding(response, order)

    def test_checkout_non_object_json_response_fails_without_saving_session(self):
        for payload in (None, [], "unexpected", 123):
            with self.subTest(payload=payload):
                response, order, _ = self.checkout(provider_response=app.httpx.Response(200, content=json.dumps(payload)))
                self.assert_checkout_failed_without_binding(response, order)

    def test_checkout_missing_or_invalid_url_fails_without_saving_session(self):
        payload = {"id": "cs_created", "amount_total": 1500, "currency": "usd"}
        response, order, _ = self.checkout(provider_response=app.httpx.Response(200, json=payload))
        self.assert_checkout_failed_without_binding(response, order)
        for url in (None, "", {}, 123, "/session", "//checkout.example.invalid/session", "http://checkout.example.invalid/session",
                    "javascript:alert(1)", "https://", "https://[invalid", "https://checkout.example.invalid:bad/session",
                    "https://checkout.example.invalid:65536/session", "https://user:password@checkout.example.invalid/session",
                    "https://checkout.example.invalid\\session", "https://checkout.example.invalid/\nlocation", " https://checkout.example.invalid/session",
                    "https://checkout.example.invalid/\ud800"):
            with self.subTest(url=url):
                response, order, _ = self.checkout(url=url)
                self.assert_checkout_failed_without_binding(response, order)

    def test_checkout_accepts_https_checkout_and_custom_domain_urls(self):
        for url in ("https://checkout.stripe.com/c/pay/cs_test_synthetic#synthetic-fragment",
                    "https://pay.example.invalid/checkout?session=synthetic"):
            with self.subTest(url=url):
                response, order, _ = self.checkout(url=url)
                self.assertEqual(response.status_code, 303)
                self.assertEqual(response.headers["location"], url)
                self.assertEqual((order["status"], order["provider_ref"], order["stripe_session_id"]), ("pending", "cs_created", "cs_created"))


if __name__ == "__main__":
    unittest.main()
