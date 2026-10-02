"""Publish sanitized CN routing health; operator-owned probes remain outside Git."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


CHECK_IDS = ("global_backend", "cn_backend", "tunnel_fresh", "dns_global", "dns_cn", "dnssec")
MAX_BYTES = 65536
MAX_AGE = 300
RUN_REASONS = {"checks_pending", "checks_passed", "checks_failed", "configuration_invalid"}


def make_report(checks: dict, checked_at: int | None, reason: str) -> dict:
    return {
        "schema_version": 1,
        "checked_at": checked_at,
        "healthy": all(checks.values()),
        "global_up": int(checks["global_backend"]),
        "cn_up": int(checks["cn_backend"]),
        "global_fallback_available": checks["global_backend"] and checks["dns_global"] and checks["dnssec"],
        "checks": checks,
        "failed_checks": [name for name in CHECK_IDS if not checks[name]],
        "reason": reason,
    }


def atomic_report(path: Path, report: dict):
    """Replace on the same filesystem; readers see one complete JSON document."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".routing-health-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(report, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def report_lock(path: Path):
    """Serialize writers, including manual runs, without stale lockfile ownership."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path.with_suffix(path.suffix + ".lock"),
                 os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(fd, "r+b") as handle:
        if os.name == "nt":
            import msvcrt
            if os.fstat(handle.fileno()).st_size == 0:
                handle.write(b"\0")
                handle.flush()
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_config(path: Path) -> tuple[dict, int]:
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("configuration_invalid")
    config = json.loads(raw)
    if not isinstance(config, dict) or set(config) - {"checks", "timeout_seconds"}:
        raise ValueError("configuration_invalid")
    checks = config.get("checks")
    timeout = config.get("timeout_seconds", 5)
    if (not isinstance(checks, dict) or set(checks) != set(CHECK_IDS)
            or type(timeout) is not int or not 1 <= timeout <= 10):
        raise ValueError("configuration_invalid")
    for command in checks.values():
        if (not isinstance(command, list) or not 1 <= len(command) <= 32
                or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in command)
                or not Path(command[0]).is_absolute()):
            raise ValueError("configuration_invalid")
    return checks, timeout


def run(config: Path, report: Path) -> int:
    with report_lock(report):
        # Invalidate a previous success BEFORE any configuration or probe can fail.
        # Timestamp the start, so an old/slow cycle cannot appear freshly measured.
        checked_at = int(time.time())
        checks = dict.fromkeys(CHECK_IDS, False)
        atomic_report(report, make_report(checks, checked_at, "checks_pending"))
        try:
            commands, timeout = load_config(config)
        except (OSError, ValueError, TypeError, RecursionError):
            atomic_report(report, make_report(checks, checked_at, "configuration_invalid"))
            return 1
        for name in CHECK_IDS:
            try:
                result = subprocess.run(
                    commands[name], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, timeout=timeout, check=False, shell=False,
                )
                checks[name] = result.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                checks[name] = False
        healthy = all(checks.values())
        atomic_report(report, make_report(checks, checked_at, "checks_passed" if healthy else "checks_failed"))
        return 0 if healthy else 1


def inspect(report: Path, max_age: int = MAX_AGE, *, now: int | None = None) -> dict:
    """Consumers must call this before trusting either full health or fallback."""
    checked_at = None
    reason = "report_missing_or_invalid"
    try:
        if type(max_age) is not int or not 1 <= max_age <= MAX_AGE:
            raise ValueError("invalid freshness budget")
        with report.open("rb") as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError("oversized report")
        data = json.loads(raw)
        if (not isinstance(data, dict) or type(data.get("schema_version")) is not int
                or data["schema_version"] != 1 or type(data.get("checked_at")) is not int
                or data["checked_at"] < 0 or not isinstance(data.get("checks"), dict)
                or set(data["checks"]) != set(CHECK_IDS)
                or any(type(value) is not bool for value in data["checks"].values())
                or not isinstance(data.get("reason"), str) or data["reason"] not in RUN_REASONS):
            raise ValueError("invalid report")
        expected = make_report(data["checks"], data["checked_at"], data["reason"])
        for name, value in expected.items():
            if type(data.get(name)) is not type(value) or data[name] != value:
                raise ValueError("inconsistent report")
        if (data["reason"] == "checks_passed") != data["healthy"]:
            raise ValueError("inconsistent result")
        if (data["reason"] in {"checks_pending", "configuration_invalid"}
                and any(data["checks"].values())):
            raise ValueError("inconsistent result")
        checked_at = data["checked_at"]
        age = (int(time.time()) if now is None else now) - checked_at
        if age < 0:
            reason = "report_clock_invalid"
        elif age > max_age:
            reason = "report_stale"
        else:
            return expected  # Rebuild the allowlist; never relay arbitrary fields.
    except (OSError, ValueError, TypeError, RecursionError):
        pass
    return make_report(dict.fromkeys(CHECK_IDS, False), checked_at, reason)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    runner = commands.add_parser("run")
    runner.add_argument("--config", type=Path, required=True)
    runner.add_argument("--report", type=Path, required=True)
    checker = commands.add_parser("check")
    checker.add_argument("--report", type=Path, required=True)
    checker.add_argument("--max-age", type=int, default=MAX_AGE, choices=range(1, MAX_AGE + 1), metavar="1..300")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            return run(args.config, args.report)
        result = inspect(args.report, args.max_age)
        print(json.dumps(result, separators=(",", ":")))
        return 0 if result["healthy"] else 1
    except OSError:
        # An unwritable report or a competing writer is never a successful check.
        print(json.dumps({"healthy": False, "reason": "report_publish_or_lock_failed"}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
