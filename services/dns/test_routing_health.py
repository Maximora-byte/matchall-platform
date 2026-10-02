"""Deterministic local routing-health checks; no resolver or production access."""
import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

import routing_health as health


NOW = 1_800_000_000
CHECK_IDS = (
    "global_backend", "cn_backend", "tunnel_fresh",
    "dns_global", "dns_cn", "dnssec",
)
PRIVATE_MARKER = "synthetic-private-endpoint.invalid/example-secret"


def command(code=0):
    return [str(Path(sys.executable).resolve()), "-c", f"raise SystemExit({code})"]


def config_file(tmp_path, failures=(), **extra):
    config = {"checks": {name: command(int(name in failures)) for name in CHECK_IDS}}
    config.update(extra)
    path = tmp_path / "checks.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def successful_report():
    return {
        "schema_version": 1,
        "checked_at": NOW,
        "healthy": True,
        "global_up": 1,
        "cn_up": 1,
        "global_fallback_available": True,
        "checks": dict.fromkeys(CHECK_IDS, True),
        "failed_checks": [],
        "reason": "checks_passed",
    }


def read_report(path):
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    monkeypatch.setattr(health.time, "time", lambda: NOW)


def test_success_is_published_after_every_required_check(tmp_path):
    report = tmp_path / "health.json"
    assert tuple(health.CHECK_IDS) == CHECK_IDS
    assert health.run(config_file(tmp_path), report) == 0
    assert read_report(report) == successful_report()
    inspected = health.inspect(report, now=NOW)
    assert inspected["healthy"] is True
    assert inspected["global_fallback_available"] is True
    assert inspected["reason"] == "checks_passed"


def test_cn_down_is_unhealthy_while_global_fallback_remains_available(tmp_path):
    report = tmp_path / "health.json"
    assert health.run(config_file(tmp_path, failures=("cn_backend",)), report) == 1
    result = read_report(report)
    assert result["healthy"] is False
    assert result["cn_up"] == 0
    assert result["global_up"] == 1
    assert result["global_fallback_available"] is True
    assert result["failed_checks"] == ["cn_backend"]
    assert result["reason"] == "checks_failed"
    assert health.inspect(report, now=NOW)["healthy"] is False


@pytest.mark.parametrize("failed", ["dns_global", "dnssec"])
def test_global_backend_alone_does_not_prove_validated_fallback(tmp_path, failed):
    report = tmp_path / "health.json"
    assert health.run(config_file(tmp_path, failures=(failed,)), report) == 1
    result = read_report(report)
    assert result["global_up"] == 1
    assert result["cn_up"] == 1
    assert result["global_fallback_available"] is False
    assert result["healthy"] is False
    assert result["failed_checks"] == [failed]


def test_early_probe_failure_replaces_previous_success_and_continues(tmp_path):
    report = tmp_path / "health.json"
    health.atomic_report(report, successful_report())
    assert health.run(config_file(tmp_path, failures=("global_backend",)), report) == 1
    result = read_report(report)
    assert result["healthy"] is False
    assert result["global_up"] == 0
    assert result["cn_up"] == 1
    assert result["global_fallback_available"] is False
    assert result["failed_checks"] == ["global_backend"]
    assert all(result["checks"][name] for name in CHECK_IDS[1:])
    assert result["checked_at"] == NOW


def test_pending_report_is_visible_before_any_probe_and_options_are_bounded(tmp_path, monkeypatch):
    report = tmp_path / "health.json"
    health.atomic_report(report, successful_report())
    calls = []

    def probe(argv, **kwargs):
        pending = read_report(report)
        assert pending["healthy"] is False
        assert pending["global_fallback_available"] is False
        assert pending["reason"] == "checks_pending"
        assert not any(pending["checks"].values())
        assert kwargs.get("shell", False) is False
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["timeout"] == 3
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(health.subprocess, "run", probe)
    assert health.run(config_file(tmp_path, timeout_seconds=3), report) == 0
    assert len(calls) == len(CHECK_IDS)
    assert read_report(report)["healthy"] is True


def test_cycle_timestamp_records_start_instead_of_completion(tmp_path, monkeypatch):
    report = tmp_path / "health.json"
    current = [NOW]
    monkeypatch.setattr(health.time, "time", lambda: current[0])

    def probe(argv, **kwargs):
        current[0] += 5
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(health.subprocess, "run", probe)
    assert health.run(config_file(tmp_path), report) == 0
    assert current[0] == NOW + 30
    assert read_report(report)["checked_at"] == NOW


@pytest.mark.parametrize("failure", ["missing", "timeout"])
def test_execution_errors_publish_sanitized_failure_and_continue(tmp_path, monkeypatch, failure):
    report = tmp_path / "health.json"
    calls = []

    def probe(argv, **kwargs):
        calls.append(argv)
        if len(calls) == 1:
            if failure == "missing":
                raise OSError(PRIVATE_MARKER)
            raise subprocess.TimeoutExpired(argv, kwargs["timeout"], output=PRIVATE_MARKER)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(health.subprocess, "run", probe)
    assert health.run(config_file(tmp_path), report) == 1
    assert len(calls) == len(CHECK_IDS)
    result = read_report(report)
    assert result["failed_checks"] == ["global_backend"]
    assert result["reason"] == "checks_failed"
    assert result["healthy"] is False
    assert PRIVATE_MARKER not in report.read_text(encoding="utf-8")


@pytest.mark.parametrize("invalid", [
    "missing_file", "malformed_json", "deep_nesting", "missing_check", "extra_check",
    "relative_executable", "empty_argv", "argv_not_strings", "extra_config",
    "timeout_zero", "timeout_too_large", "timeout_boolean",
])
def test_invalid_config_overwrites_success_with_new_failure(tmp_path, monkeypatch, invalid):
    path = config_file(tmp_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    if invalid == "missing_file":
        path.unlink()
    elif invalid == "malformed_json":
        path.write_text("{", encoding="utf-8")
    elif invalid == "deep_nesting":
        path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    else:
        if invalid == "missing_check":
            del config["checks"]["dns_cn"]
        elif invalid == "extra_check":
            config["checks"]["unreviewed"] = command()
        elif invalid == "relative_executable":
            config["checks"]["dns_cn"] = ["python", "-c", "pass"]
        elif invalid == "empty_argv":
            config["checks"]["dns_cn"] = []
        elif invalid == "argv_not_strings":
            config["checks"]["dns_cn"] = [command()[0], 1]
        elif invalid == "extra_config":
            config["private"] = PRIVATE_MARKER
        else:
            config["timeout_seconds"] = {
                "timeout_zero": 0, "timeout_too_large": 11, "timeout_boolean": True,
            }[invalid]
        path.write_text(json.dumps(config), encoding="utf-8")
    report = tmp_path / "health.json"
    health.atomic_report(report, successful_report())

    def unexpected_probe(*args, **kwargs):
        pytest.fail("Invalid configuration must not execute probes")

    monkeypatch.setattr(health.subprocess, "run", unexpected_probe)
    assert health.run(path, report) == 1
    result = read_report(report)
    assert result["healthy"] is False
    assert result["checked_at"] == NOW
    assert result["reason"] == "configuration_invalid"
    assert result["failed_checks"] == list(CHECK_IDS)
    assert not any(result["checks"].values())
    assert result["global_fallback_available"] is False
    assert PRIVATE_MARKER not in json.dumps(result)


def test_consumer_freshness_boundary_and_clock_future(tmp_path):
    path = tmp_path / "health.json"
    health.atomic_report(path, successful_report())
    assert health.inspect(path, now=NOW + 300)["healthy"] is True
    stale = health.inspect(path, now=NOW + 301)
    assert stale["healthy"] is False
    assert stale["global_fallback_available"] is False
    assert stale["global_up"] == stale["cn_up"] == 0
    assert stale["reason"] == "report_stale"
    future = health.inspect(path, now=NOW - 1)
    assert future["healthy"] is False
    assert future["global_fallback_available"] is False
    assert future["global_up"] == future["cn_up"] == 0


@pytest.mark.parametrize("invalid", [
    "missing", "malformed", "deep_nesting", "oversize", "healthy_inconsistent", "fallback_inconsistent",
    "count_inconsistent", "failed_checks_inconsistent", "reason_inconsistent",
    "boolean_timestamp", "boolean_schema", "boolean_count", "non_bool_check",
    "extra_check", "missing_check",
])
def test_consumer_rejects_untrusted_or_inconsistent_reports(tmp_path, invalid):
    path = tmp_path / "health.json"
    result = successful_report()
    if invalid == "missing":
        pass
    elif invalid == "malformed":
        path.write_text("[]", encoding="utf-8")
    elif invalid == "deep_nesting":
        path.write_text("[" * 2000 + "0" + "]" * 2000, encoding="utf-8")
    elif invalid == "oversize":
        result["ignored"] = "x" * 65536
        path.write_text(json.dumps(result), encoding="utf-8")
    else:
        if invalid == "healthy_inconsistent":
            result["healthy"] = False
        elif invalid == "fallback_inconsistent":
            result["global_fallback_available"] = False
        elif invalid == "count_inconsistent":
            result["cn_up"] = 0
        elif invalid == "failed_checks_inconsistent":
            result["failed_checks"] = ["dnssec"]
        elif invalid == "reason_inconsistent":
            result["reason"] = "checks_failed"
        elif invalid == "boolean_timestamp":
            result["checked_at"] = True
        elif invalid == "boolean_schema":
            result["schema_version"] = True
        elif invalid == "boolean_count":
            result["global_up"] = True
        elif invalid == "non_bool_check":
            result["checks"]["dnssec"] = 1
        elif invalid == "extra_check":
            result["checks"]["private"] = True
        elif invalid == "missing_check":
            del result["checks"]["dnssec"]
        path.write_text(json.dumps(result), encoding="utf-8")
    inspected = health.inspect(path, now=NOW)
    assert inspected["healthy"] is False
    assert inspected["global_fallback_available"] is False
    assert inspected["global_up"] == inspected["cn_up"] == 0


def test_consumer_drops_unknown_source_fields(tmp_path):
    path = tmp_path / "health.json"
    result = successful_report()
    result["private_endpoint"] = PRIVATE_MARKER
    health.atomic_report(path, result)
    inspected = health.inspect(path, now=NOW)
    assert inspected["healthy"] is True
    assert "private_endpoint" not in inspected
    assert PRIVATE_MARKER not in json.dumps(inspected)


@pytest.mark.parametrize("budget", [0, 301, True, "300"])
def test_consumer_invalid_freshness_budget_fails_closed(tmp_path, budget):
    path = tmp_path / "health.json"
    health.atomic_report(path, successful_report())
    result = health.inspect(path, max_age=budget, now=NOW)
    assert result["healthy"] is False
    assert result["global_fallback_available"] is False


def test_atomic_publication_does_not_expose_a_partial_file(tmp_path, monkeypatch):
    path = tmp_path / "health.json"
    before = successful_report()
    health.atomic_report(path, before)
    after = copy.deepcopy(before)
    after["checked_at"] += 1
    replace = health.os.replace
    replacements = []

    def observing_replace(source, target):
        assert read_report(path) == before
        assert read_report(Path(source)) == after
        assert Path(source).parent == path.parent
        replacements.append(source)
        return replace(source, target)

    monkeypatch.setattr(health.os, "replace", observing_replace)
    health.atomic_report(path, after)
    assert len(replacements) == 1
    assert read_report(path) == after
    assert sorted(item.name for item in tmp_path.iterdir()) == ["health.json"]


def test_cli_service_exit_and_sanitized_report_agree(tmp_path):
    path = config_file(tmp_path)
    config = json.loads(path.read_text(encoding="utf-8"))
    config["checks"]["global_backend"] = [
        command()[0], "-c",
        "import sys; print(sys.argv[1]); print(sys.argv[1], file=sys.stderr); raise SystemExit(1)",
        PRIVATE_MARKER,
    ]
    path.write_text(json.dumps(config), encoding="utf-8")
    report = tmp_path / "health.json"
    completed = subprocess.run(
        [sys.executable, str(Path(health.__file__).resolve()), "run",
         "--config", str(path), "--report", str(report)],
        capture_output=True, text=True, timeout=30, check=False,
    )
    assert completed.returncode == 1
    assert PRIVATE_MARKER not in completed.stdout + completed.stderr
    assert PRIVATE_MARKER not in report.read_text(encoding="utf-8")
    assert completed.stdout == ""
    result = read_report(report)
    assert result["healthy"] is False
    assert result["global_fallback_available"] is False
    assert result["failed_checks"] == ["global_backend"]
    checked = subprocess.run(
        [sys.executable, str(Path(health.__file__).resolve()), "check",
         "--report", str(report), "--max-age", "300"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert checked.returncode == 1
    assert json.loads(checked.stdout)["healthy"] is False


def test_cli_publish_failure_cannot_exit_success_or_expose_private_path(tmp_path):
    config = config_file(tmp_path)
    report = tmp_path / "synthetic-private-endpoint.invalid" / "health.json"
    report.mkdir(parents=True)
    completed = subprocess.run(
        [sys.executable, str(Path(health.__file__).resolve()), "run",
         "--config", str(config), "--report", str(report)],
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert completed.returncode == 2
    assert "synthetic-private-endpoint.invalid" not in completed.stdout + completed.stderr
    error = json.loads(completed.stderr or completed.stdout)
    assert error["healthy"] is False


def test_overlapping_writer_fails_without_replacing_active_report(tmp_path):
    config = config_file(tmp_path)
    report = tmp_path / "health.json"
    previous = successful_report()
    health.atomic_report(report, previous)
    with health.report_lock(report):
        completed = subprocess.run(
            [sys.executable, str(Path(health.__file__).resolve()), "run",
             "--config", str(config), "--report", str(report)],
            capture_output=True, text=True, timeout=10, check=False,
        )
        assert completed.returncode == 2
        assert json.loads(completed.stderr)["healthy"] is False
        assert read_report(report) == previous
