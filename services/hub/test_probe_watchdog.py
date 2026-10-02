"""Offline runner, freshness, and alert adapter contracts; no external requests."""
import contextlib
import fcntl
import io
import json
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import probe_watchdog as watchdog


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.state = self.root / "private" / "report.json"
        self.config = self.root / "fixture.json"

    def state_report(self, **values):
        return {"schema_version": 1, "finished_at": 1000, "ok": True, "reason": "probes_ok",
                "vantage_point": "operator_managed_unverified", **values}

    def runner_result(self, ok=True, code=0):
        return subprocess.CompletedProcess([], code, json.dumps(
            {"schema_version": 1, "probes": [{"ok": ok}], "private": "synthetic-secret"}).encode(),
            b"synthetic-secret")

    def test_success_failure_and_nonzero_exit_are_recorded_without_raw_data(self):
        for probe_ok, code, expected in [(True, 0, True), (False, 1, False), (True, 1, False)]:
            with self.subTest(probe_ok=probe_ok, code=code), \
                 patch.object(watchdog.subprocess, "run", return_value=self.runner_result(probe_ok, code)):
                self.assertEqual(watchdog.run(self.config, self.state, 220), 0 if expected else 1)
                text = self.state.read_text()
                self.assertNotIn("synthetic-secret", text)
                self.assertEqual(json.loads(text)["ok"], expected)
                self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(self.state.parent.stat().st_mode), 0o700)

    def test_timeout_crash_invalid_and_missing_configuration_fail_closed(self):
        failures = [(subprocess.TimeoutExpired("fixture", 1), "runner_timeout"),
                    (OSError("synthetic-secret"), "runner_error"),
                    (subprocess.CompletedProcess([], 2, b"", b""), "runner_error"),
                    (subprocess.CompletedProcess([], 0, b"{}", b""), "runner_output_invalid"),
                    (subprocess.CompletedProcess([], 0, b"[]", b""), "runner_output_invalid"),
                    (subprocess.CompletedProcess([], 0, b"x" * 65537, b""), "runner_output_invalid")]
        for result, reason in failures:
            with self.subTest(reason=reason):
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch.object(watchdog.subprocess, "run", **kwargs):
                    self.assertEqual(watchdog.run(self.config, self.state, 1), 1)
                self.assertEqual(json.loads(self.state.read_text())["reason"], reason)

    def test_overlapping_run_does_not_replace_report(self):
        watchdog.atomic_state(self.state, self.state_report())
        original = self.state.read_bytes()
        with self.state.with_suffix(".lock").open("w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch.object(watchdog.subprocess, "run") as process:
                self.assertEqual(watchdog.run(self.config, self.state, 1), 0)
                process.assert_not_called()
        self.assertEqual(self.state.read_bytes(), original)

    def test_missing_invalid_stale_future_and_failed_reports_are_not_healthy(self):
        self.assertFalse(watchdog.inspect(self.state, 300, now=1000)["ok"])
        for values, now, reason in [({}, 1301, "report_stale"), ({}, 999, "report_clock_invalid"),
                                   ({"ok": False, "reason": "runner_timeout"}, 1001, "runner_timeout"),
                                   ({"ok": "true"}, 1001, "report_missing_or_invalid"),
                                   ({"ok": False}, 1001, "report_missing_or_invalid")]:
            watchdog.atomic_state(self.state, self.state_report(**values))
            event = watchdog.inspect(self.state, 300, now=now)
            self.assertFalse(event["ok"])
            self.assertEqual(event["reason"], reason)
            self.assertEqual(event["business_availability"], "not_verified")
        watchdog.atomic_state(self.state, self.state_report())
        self.assertTrue(watchdog.inspect(self.state, 300, now=1300)["ok"])

    def test_atomic_failure_preserves_previous_report_and_cleans_temporary_file(self):
        watchdog.atomic_state(self.state, self.state_report())
        original = self.state.read_bytes()
        with patch.object(watchdog.os, "replace", side_effect=OSError("fixture")):
            with self.assertRaises(OSError):
                watchdog.atomic_state(self.state, self.state_report(ok=False))
        self.assertEqual(self.state.read_bytes(), original)
        self.assertFalse(list(self.state.parent.glob(".probe-state-*")))

    def test_check_sends_only_sanitized_event_to_adapter_and_remains_failed(self):
        output = io.StringIO()
        with patch.object(watchdog.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as process, \
             contextlib.redirect_stdout(output):
            self.assertEqual(watchdog.main(["check", "--state", str(self.state),
                                           "--alert-command", "/approved/synthetic-alert"]), 1)
        args, kwargs = process.call_args
        self.assertEqual(args[0], ["/approved/synthetic-alert"])
        self.assertNotIn("shell", kwargs)
        self.assertEqual(kwargs["timeout"], 15)
        self.assertEqual(json.loads(kwargs["input"])["reason"], "report_missing_or_invalid")
        self.assertEqual(json.loads(output.getvalue())["alert_delivery"], "accepted")
        self.assertNotIn(str(self.state), output.getvalue())

    def test_real_offline_adapter_receives_stdin_and_acknowledges(self):
        adapter = self.root / "adapter"
        received = self.root / "received"
        adapter.write_text("#!/bin/sh\ncat > " + str(received) + "\n", encoding="utf-8")
        adapter.chmod(0o700)
        event = watchdog.inspect(self.state, 300)
        self.assertEqual(watchdog.deliver(adapter, event), "accepted")
        self.assertEqual(json.loads(received.read_text()), event)

    def test_unconfigured_failure_timeout_and_healthy_report_do_not_fake_delivery(self):
        self.assertEqual(watchdog.deliver(None, {}), "not_configured")
        self.assertEqual(watchdog.deliver(Path("relative"), {}), "failed")
        for result in [OSError("private"), subprocess.TimeoutExpired("private", 15),
                       subprocess.CompletedProcess([], 1)]:
            kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
            with patch.object(watchdog.subprocess, "run", **kwargs):
                self.assertEqual(watchdog.deliver(Path("/approved/adapter"), {}), "failed")
        watchdog.atomic_state(self.state, self.state_report(finished_at=int(watchdog.time.time())))
        with patch.object(watchdog.subprocess, "run") as process, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(watchdog.main(["check", "--state", str(self.state)]), 0)
            process.assert_not_called()


if __name__ == "__main__":
    unittest.main()
