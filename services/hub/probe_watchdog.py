"""Opt-in Linux runner supervision and independent freshness checks; no deployment."""
import argparse
import fcntl
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

MAX_STATE_BYTES = 65536
REASONS = {"probes_ok", "probe_failed", "runner_timeout", "runner_error", "runner_output_invalid"}


def atomic_state(path: Path, state: dict):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".probe-state-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(config: Path, state: Path, timeout: int) -> int:
    """Bound total runtime and serialize scheduled runs without importing Hub."""
    state.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(state.with_suffix(".lock"), os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Existing run owns the report; freshness checks still detect a stall.
            return 0
        ok, reason = False, "runner_error"
        try:
            result = subprocess.run(
                [sys.executable, str(Path(__file__).with_name("probe_runner.py")), "--config", str(config)],
                capture_output=True, timeout=timeout, check=False,
            )
            if result.returncode in (0, 1):
                try:
                    if len(result.stdout) > MAX_STATE_BYTES:
                        raise ValueError("oversized")
                    report = json.loads(result.stdout)
                    probes = report["probes"]
                    if (report.get("schema_version") != 1 or not isinstance(probes, list)
                            or not 1 <= len(probes) <= 20
                            or any(not isinstance(item, dict) or type(item.get("ok")) is not bool for item in probes)):
                        raise ValueError("invalid")
                    ok = result.returncode == 0 and all(item["ok"] for item in probes)
                    reason = "probes_ok" if ok else "probe_failed"
                except (ValueError, KeyError, TypeError):
                    reason = "runner_output_invalid"
        except subprocess.TimeoutExpired:
            reason = "runner_timeout"
        except OSError:
            pass
        # No raw subprocess stdout/stderr, URL, domain, or exception text persists.
        atomic_state(state, {"schema_version": 1, "finished_at": int(time.time()),
                             "ok": ok, "reason": reason, "vantage_point": "operator_managed_unverified"})
        return 0 if ok else 1


def inspect(state: Path, max_age: int, *, now: int | None = None) -> dict:
    now = int(time.time()) if now is None else now
    reason, ok = "report_missing_or_invalid", False
    try:
        fd = os.open(state, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                raise ValueError("invalid")
            raw = handle.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            raise ValueError("oversized")
        report = json.loads(raw)
        if (not isinstance(report, dict) or type(report.get("schema_version")) is not int
                or report["schema_version"] != 1 or type(report.get("finished_at")) is not int
                or type(report.get("ok")) is not bool or report.get("reason") not in REASONS
                or report.get("vantage_point") != "operator_managed_unverified"
                or report["ok"] != (report["reason"] == "probes_ok")):
            raise ValueError("invalid")
        age = now - report["finished_at"]
        if age < 0:
            reason = "report_clock_invalid"
        elif age > max_age:
            reason = "report_stale"
        else:
            ok, reason = report["ok"], report["reason"]
    except (OSError, ValueError, TypeError):
        pass
    return {"schema_version": 1, "observed_at": now, "ok": ok, "reason": reason,
            "vantage_point": "operator_managed_unverified", "business_availability": "not_verified"}


def deliver(alert_command: Path | None, event: dict) -> str:
    if alert_command is None:
        return "not_configured"
    if not alert_command.is_absolute():
        return "failed"
    try:
        # A trusted operator-owned executable receives fixed sanitized JSON on stdin.
        # No shell, command interpolation, or notification credentials in this repo.
        result = subprocess.run([str(alert_command)], input=json.dumps(event).encode(),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                timeout=15, check=False)
        return "accepted" if result.returncode == 0 else "failed"
    except (OSError, subprocess.TimeoutExpired):
        return "failed"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--config", required=True, type=Path)
    runner.add_argument("--state", required=True, type=Path)
    runner.add_argument("--timeout", type=int, default=220, choices=range(1, 301), metavar="1..300")
    checker = commands.add_parser("check")
    checker.add_argument("--state", required=True, type=Path)
    checker.add_argument("--max-age", type=int, default=300, choices=range(1, 3601), metavar="1..3600")
    checker.add_argument("--alert-command", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return run(args.config, args.state, args.timeout)
        event = inspect(args.state, args.max_age)
        if not event["ok"]:
            event["alert_delivery"] = deliver(args.alert_command, event)
        print(json.dumps(event))
        return 0 if event["ok"] else 1
    except (OSError, ValueError):
        print(json.dumps({"schema_version": 1, "ok": False, "reason": "watchdog_error"}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
