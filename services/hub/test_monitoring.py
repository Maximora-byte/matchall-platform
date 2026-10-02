import asyncio
import base64
import gzip
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import dns.flags
import dns.message
import dns.rcode
import dns.rrset
import httpx

import app
from monitoring import dns_config, run_probe
from probe_runner import collect, load_config


class TrackedStream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.yielded = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk

    async def aclose(self):
        self.closed = True


def stream_response(status_code, **kwargs):
    if "stream" in kwargs:
        return httpx.Response(status_code, **kwargs)
    # content=/json= constructors are already consumed in HTTPX; use a real
    # unread AsyncByteStream so tests exercise the production raw streaming path.
    buffered = httpx.Response(status_code, **kwargs)
    return httpx.Response(status_code, headers=buffered.headers,
                          stream=TrackedStream([buffered.content]))


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.spec = dns_config("https://resolver.example/dns-query", "example.com", "192.0.2.1")
        self.seen = []

    async def probe(self, handler, spec=None):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await run_probe(client, spec or self.spec)

    def answer(self, request, *, address="192.0.2.1", rcode=0):
        self.seen.append(request)
        query = dns.message.from_wire(base64.urlsafe_b64decode(request.url.params["dns"] + "=="))
        answer = dns.message.make_response(query)
        answer.set_rcode(rcode)
        if address:
            answer.answer.append(dns.rrset.from_text("example.com.", 60, "IN", "A", address))
        return stream_response(200, content=answer.to_wire(), headers={"content-type": "application/dns-message"})

    async def test_dns_queries_configured_resolver_and_validates_answer(self):
        result = await self.probe(self.answer)
        self.assertTrue(result.ok)
        request = self.seen[0]
        self.assertEqual(request.url.host, "resolver.example")
        self.assertEqual(request.method, "GET")
        self.assertEqual(request.url.path, "/dns-query")
        self.assertNotIn("authorization", request.headers)

    async def test_wrong_answer_empty_nxdomain_and_servfail_fail(self):
        for address, rcode, reason in [("192.0.2.2", 0, "dns_answer_mismatch"),
                                      (None, 0, "dns_answer_missing"),
                                      (None, dns.rcode.NXDOMAIN, "dns_rcode_failure"),
                                      (None, dns.rcode.SERVFAIL, "dns_rcode_failure")]:
            result = await self.probe(lambda request: self.answer(request, address=address, rcode=rcode))
            self.assertFalse(result.ok)
            self.assertEqual(result.detail, reason)

    async def test_wrong_question_is_not_success(self):
        wrong = dns.message.make_response(dns.message.make_query("other.example", "A"))
        result = await self.probe(lambda _: stream_response(200, content=wrong.to_wire(),
            headers={"content-type": "application/dns-message"}))
        self.assertEqual(result.detail, "dns_response_mismatch")

    async def test_cname_chain_is_validated(self):
        def answer(request):
            query = dns.message.from_wire(base64.urlsafe_b64decode(request.url.params["dns"] + "=="))
            result = dns.message.make_response(query)
            result.answer.append(dns.rrset.from_text("example.com.", 60, "IN", "CNAME", "alias.example."))
            result.answer.append(dns.rrset.from_text("alias.example.", 60, "IN", "A", "192.0.2.1"))
            return stream_response(200, content=result.to_wire(), headers={"content-type": "application/dns-message"})
        self.assertTrue((await self.probe(answer)).ok)

    async def test_truncated_flag_and_malformed_wire_fail(self):
        async def truncated(request):
            response = self.answer(request)
            answer = dns.message.from_wire(await response.aread())
            answer.flags |= dns.flags.TC
            return stream_response(200, content=answer.to_wire(), headers={"content-type": "application/dns-message"})
        result = await self.probe(truncated)
        self.assertEqual(result.detail, "dns_response_truncated")
        result = await self.probe(lambda _: stream_response(200, content=b"invalid", headers={"content-type": "application/dns-message"}))
        self.assertEqual(result.detail, "invalid_response")

    async def test_http_200_html_is_not_dns_success(self):
        result = await self.probe(lambda _: stream_response(200, text="healthy"))
        self.assertEqual(result.detail, "unexpected_content_type")

    async def test_timeout_is_sanitized(self):
        def fail(request):
            raise httpx.ReadTimeout("secret.example/token/private", request=request)
        result = await self.probe(fail)
        self.assertEqual(result.detail, "timeout")
        self.assertNotIn("secret", repr(result))

    async def test_whole_probe_deadline_and_cookie_isolation(self):
        async def slow(request):
            await asyncio.sleep(1)
            return stream_response(200)
        with patch("monitoring.PROBE_TIMEOUT_SECONDS", 0.01):
            result = await self.probe(slow)
        self.assertEqual(result.detail, "timeout")
        def handler(request):
            self.assertNotIn("cookie", request.headers)
            return stream_response(200, headers={"set-cookie": "private=1; Path=/"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            spec = {"kind": "http", "probe": "https://same.example/"}
            self.assertTrue((await run_probe(client, spec)).ok)
            self.assertTrue((await run_probe(client, spec)).ok)

    async def test_unconfigured_does_not_make_request(self):
        handler = Mock(side_effect=AssertionError("unexpected network request"))
        result = await self.probe(handler, dns_config("", ""))
        self.assertFalse(result.ok)
        handler.assert_not_called()

    async def test_redirect_is_failure_and_not_followed(self):
        result = await self.probe(lambda _: stream_response(302, headers={"location": "https://other.example/"}))
        self.assertFalse(result.ok)
        self.assertEqual(result.code, 302)

    async def test_read_only_contract_requires_all_fields_and_types(self):
        spec = {"probe": "https://drive.example/status.php", "kind": "nextcloud"}
        for body in ({"installed": True, "maintenance": False, "needsDbUpgrade": False},
                     {"installed": True, "maintenance": True, "needsDbUpgrade": False},
                     {"installed": 1, "maintenance": False, "needsDbUpgrade": False}, {}, []):
            result = await self.probe(lambda _: stream_response(200, json=body), spec)
            self.assertEqual(result.ok, body == {"installed": True, "maintenance": False, "needsDbUpgrade": False}
                             and body.get("installed") is True)

    async def test_gzip_response_is_rejected_without_reading_or_decoding(self):
        # Small fixture with expansion beyond the semantic limit, not a large bomb.
        payload = gzip.compress(b" " * 131072)
        self.assertLess(len(payload), 1024)
        stream = TrackedStream([payload])
        requests = []

        def handler(request):
            requests.append(request)
            return stream_response(200, stream=stream, headers={"content-encoding": "gzip"})

        from httpx._decoders import GZipDecoder
        original_decode = GZipDecoder.decode
        with patch.object(GZipDecoder, "decode", autospec=True, side_effect=original_decode) as decode:
            result = await self.probe(handler, {"kind": "readiness", "probe": "https://status.example/readyz"})
        self.assertEqual(stream.yielded, 0)
        decode.assert_not_called()
        self.assertTrue(stream.closed)
        self.assertEqual(result.detail, "unexpected_content_encoding")
        self.assertFalse(result.ok)
        self.assertEqual(result.code, 200)
        self.assertEqual(requests[0].headers["accept-encoding"], "identity")

    async def test_nonidentity_encodings_are_rejected_for_every_probe_kind(self):
        for kind in ("doh", "nextcloud", "readiness", "http"):
            for encoding in ("gzip", "deflate", "br", "unknown", "identity, gzip", ""):
                with self.subTest(kind=kind, encoding=encoding):
                    stream = TrackedStream([b"must not be read"])
                    result = await self.probe(lambda _: stream_response(200, stream=stream,
                        headers={"content-encoding": encoding}), {**self.spec, "kind": kind})
                    self.assertEqual(result.detail, "unexpected_content_encoding")
                    self.assertEqual(stream.yielded, 0)
                    self.assertTrue(stream.closed)

    async def test_identity_semantic_body_limit_and_early_close(self):
        for kind, body in (("nextcloud", {"installed": True, "maintenance": False, "needsDbUpgrade": False}),
                           ("readiness", {"ready": True})):
            for encoding in (None, "identity", " Identity "):
                for size in (65535, 65536):
                    with self.subTest(kind=kind, encoding=encoding, size=size):
                        raw = json.dumps(body).encode()
                        raw += b" " * (size - len(raw))
                        # The sentinel must not be fetched after an oversized body.
                        chunks = [raw[i:i + 8192] for i in range(0, len(raw), 8192)]
                        if size > 65535:
                            chunks.append(b"unread tail")
                        stream = TrackedStream(chunks)
                        headers = {} if encoding is None else {"content-encoding": encoding}
                        result = await self.probe(lambda _: stream_response(200, stream=stream, headers=headers),
                            {"kind": kind, "probe": "https://service.example/status"})
                        self.assertEqual(result.ok, size == 65535)
                        self.assertEqual(result.detail, "" if size == 65535 else "response_too_large")
                        self.assertEqual(stream.yielded, 8)
                        self.assertTrue(stream.closed)

    async def test_remote_runner_readiness_stream_succeeds(self):
        def handler(request):
            self.assertEqual(request.headers["accept-encoding"], "identity")
            return stream_response(200, json={"ready": True})
        report = await collect([{"name": "hub", "kind": "readiness",
                                 "probe": "https://status.example/readyz"}], httpx.MockTransport(handler))
        self.assertTrue(report["probes"][0]["ok"])

    async def test_oversize_response_fails(self):
        for kind in ("doh", "nextcloud", "readiness"):
            with self.subTest(kind=kind):
                result = await self.probe(lambda _: stream_response(200, content=b" " * 65536),
                                          {**self.spec, "kind": kind})
                self.assertEqual(result.detail, "response_too_large")

    async def test_remote_runner_report_is_bounded_and_has_no_endpoint_details(self):
        report = await collect([{**self.spec, "name": "dns"}], httpx.MockTransport(self.answer))
        self.assertTrue(report["probes"][0]["ok"])
        self.assertEqual(report["vantage_point"], "operator_managed_unverified")
        self.assertNotIn("resolver.example", json.dumps(report))
        self.assertNotIn("192.0.2.1", json.dumps(report))


class ConfigTests(unittest.TestCase):
    def test_dns_requires_explicit_public_resolver_domain_pair(self):
        self.assertEqual(dns_config("", "")["configuration_state"], "unconfigured")
        for url, domain in [("https://r.example/dns-query", ""), ("", "example.com"),
                            ("http://r.example/dns-query", "example.com"),
                            ("https://user:password@r.example/dns-query", "example.com"),
                            ("https://r.example/dns-query/token", "example.com"),
                            ("https://r.example/dns-query?token=secret", "example.com"),
                            ("https://r.example/dns-query", ".")]:
            self.assertEqual(dns_config(url, domain)["configuration_state"], "invalid")

    def test_remote_runner_rejects_unknown_fields_credentials_and_duplicates(self):
        probe = {"name": "hub", "kind": "readiness", "url": "https://status.example/readyz"}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(json.dumps({"probes": [probe]}))
            self.assertEqual(load_config(path)[0]["kind"], "readiness")
            for body in ({"probes": []}, {"probes": [probe, probe]},
                         {"probes": [{**probe, "headers": {"Authorization": "secret"}}]},
                         {"probes": [{**probe, "url": "https://u:p@status.example/readyz"}]},
                         {"probes": [{**probe, "kind": "post"}]}, {"probes": [None]}):
                path.write_text(json.dumps(body))
                with self.assertRaises(ValueError):
                    load_config(path)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, "STATUS_DB", Path(self.temp.name) / "status.db"),
                        patch.object(app, "NOTIFY_DB", Path(self.temp.name) / "notify.db"),
                        patch.object(app, "BACKGROUND_TASKS", {name: Mock(done=lambda: False) for name in ("probes", "delivery")}),
                        patch.object(app, "BACKGROUND_PROGRESS", {"probes": 1000, "delivery": 1000}),
                        patch.object(app, "BACKGROUND_ERRORS", set()),
                        patch.object(app.time, "monotonic", lambda: 1001)]
        for item in self.patches:
            item.start()
        app.init_status_db()
        app.init_notify_db()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def test_liveness_does_not_claim_readiness_or_business_health(self):
        self.assertEqual(app.healthz(), {"status": "ok"})
        self.assertEqual(app.readyz().status_code, 200)
        app.BACKGROUND_TASKS["probes"] = Mock(done=lambda: True)
        self.assertEqual(app.healthz(), {"status": "ok"})
        response = app.readyz()
        self.assertEqual(response.status_code, 503)
        self.assertIn("probes_task_stopped", json.loads(response.body)["reasons"])

    def test_stale_missing_heartbeat_cycle_failure_and_db_failure(self):
        app.BACKGROUND_PROGRESS["probes"] = 1
        self.assertEqual(app.readyz().status_code, 503)
        app.BACKGROUND_PROGRESS["probes"] = 1000
        app.BACKGROUND_PROGRESS.pop("delivery")
        self.assertEqual(app.readyz().status_code, 503)
        app.BACKGROUND_PROGRESS["delivery"] = 1000
        app.BACKGROUND_ERRORS.add("probes")
        self.assertEqual(app.readyz().status_code, 503)
        app.BACKGROUND_ERRORS.clear()
        app.STATUS_DB.unlink()
        self.assertEqual(app.readyz().status_code, 503)
        self.assertFalse(app.STATUS_DB.exists())

    def test_public_contract_labels_unconfigured_dns_unknown(self):
        response = json.loads(app.status_api().body)
        dns_service = next(item for item in response["services"] if item["key"] == "dns")
        self.assertFalse(dns_service["configured"])
        self.assertEqual(dns_service["status"], "unknown")
        self.assertEqual(dns_service["business_availability"], "not_verified")
        self.assertNotIn("probe", dns_service)
        self.assertNotIn("domain", dns_service)
        self.assertNotIn("expected_addresses", dns_service)

    def test_invalid_config_is_not_ready(self):
        with patch.object(app, "SERVICES", [{"configuration_state": "invalid"}]):
            self.assertEqual(app.readyz().status_code, 503)


class LifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_lifespan_cancels_and_awaits_background_tasks(self):
        stopped = []
        async def wait(name):
            app.mark_progress(name)
            try:
                await asyncio.Future()
            finally:
                stopped.append(name)
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(app, "DATA_DIR", Path(temp)), \
             patch.object(app, "SNAPSHOT_DIR", Path(temp) / "snapshots"), \
             patch.object(app, "init_status_db"), patch.object(app, "init_notify_db"), \
             patch.object(app, "probe_loop", lambda: wait("probes")), \
             patch.object(app, "delivery_loop", lambda: wait("delivery")), \
             patch.object(app, "BACKGROUND_TASKS", {}), \
             patch.object(app, "BACKGROUND_PROGRESS", {}), \
             patch.object(app, "BACKGROUND_ERRORS", set()):
            async with app.lifespan(app.app):
                await asyncio.sleep(0)
                self.assertEqual(set(app.BACKGROUND_PROGRESS), {"probes", "delivery"})
            self.assertCountEqual(stopped, ["probes", "delivery"])
            self.assertFalse(app.BACKGROUND_TASKS)
            self.assertFalse(app.BACKGROUND_PROGRESS)

    async def test_loop_retries_failure_and_only_marks_completed_cycle(self):
        calls, progress = [], []
        async def cycle():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("synthetic failure")
        async def sleep(_):
            if len(calls) == 1:
                self.assertIn("probes", app.BACKGROUND_ERRORS)
                self.assertFalse(progress)
            else:
                raise asyncio.CancelledError()
        with patch.object(app, "probe_once", cycle), patch.object(app.asyncio, "sleep", sleep), \
             patch.object(app, "mark_progress", lambda name: progress.append(name)), \
             patch.object(app, "BACKGROUND_ERRORS", set()):
            with self.assertRaises(asyncio.CancelledError):
                await app.probe_loop()
            self.assertEqual(len(calls), 2)
            self.assertEqual(progress, ["probes"])
            self.assertFalse(app.BACKGROUND_ERRORS)

    async def test_unconfigured_probe_is_not_recorded_as_failure(self):
        with patch.object(app, "SERVICES", [{"configured": False}]), \
             patch.object(app, "run_probe", AsyncMock()) as run, \
             patch.object(app, "status_db", Mock(side_effect=AssertionError("no DB writes"))):
            await app.probe_once()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
