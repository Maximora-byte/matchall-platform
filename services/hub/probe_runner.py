"""Optional one-shot probe runner. Not deployed, scheduled, or connected by default."""
import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

import httpx

from monitoring import dns_config, run_probe, validate_public_url


def load_config(path: Path) -> list[dict]:
    with path.open("rb") as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError("configuration_too_large")
    body = json.loads(raw)
    if not isinstance(body, dict) or set(body) != {"probes"}:
        raise ValueError("invalid_configuration")
    probes = body["probes"]
    if not isinstance(probes, list) or not 1 <= len(probes) <= 20:
        raise ValueError("one_to_twenty_probes_required")
    result, names = [], set()
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) - {"name", "kind", "url", "domain", "expected_addresses"}:
            raise ValueError("invalid_probe")
        name, kind = probe.get("name", ""), probe.get("kind", "")
        if not isinstance(name, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", name) or name in names:
            raise ValueError("invalid_or_duplicate_name")
        names.add(name)
        url = probe.get("url", "")
        if not isinstance(url, str):
            raise ValueError("invalid_url")
        validate_public_url(url)
        if kind == "doh":
            if not all(isinstance(probe.get(key, ""), str) for key in ("domain", "expected_addresses")):
                raise ValueError("invalid_dns_configuration")
            spec = dns_config(url, probe.get("domain", ""), probe.get("expected_addresses", ""))
            if not spec["configured"]:
                raise ValueError("invalid_dns_configuration")
        elif kind in {"http", "nextcloud", "readiness"}:
            if "domain" in probe or "expected_addresses" in probe:
                raise ValueError("dns_fields_require_doh")
            spec = {"kind": kind, "probe": url}
        else:
            raise ValueError("unsupported_check")
        result.append({**spec, "name": name})
    return result


async def collect(probes: list[dict], transport=None) -> dict:
    results = []
    # No environment proxy, auth, redirect following, or persisted cookie jar.
    for spec in probes:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False, transport=transport) as client:
            start = time.monotonic()
            result = await run_probe(client, spec)
            results.append({"name": spec["name"], "kind": spec["kind"], "ok": result.ok,
                            "latency_ms": max(1, int((time.monotonic() - start) * 1000)),
                            "reason": result.detail})
    return {"schema_version": 1, "checked_at": int(time.time()),
            "vantage_point": "operator_managed_unverified", "probes": results}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    args = parser.parse_args()
    try:
        probes = load_config(args.config)
    except (OSError, ValueError, TypeError):
        print(json.dumps({"error": "invalid_or_missing_configuration"}), file=sys.stderr)
        return 2
    report = asyncio.run(collect(probes))
    print(json.dumps(report))
    return 0 if all(item["ok"] for item in report["probes"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
