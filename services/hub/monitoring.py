"""Bounded, credential-free read probes shared by Hub and an optional remote runner."""
import asyncio
import base64
import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

import dns.exception
import dns.message
import dns.name
import dns.rcode
import dns.rdatatype
import httpx

MAX_RESPONSE_BYTES = 65535
PROBE_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class ProbeResult:
    ok: bool
    code: int = 0
    detail: str = ""


def dns_config(url: str, domain: str, expected_addresses: str = "") -> dict:
    """No default resolver or account token: explicit URL AND domain are required."""
    result = {"kind": "doh", "probe": url.strip(), "domain": domain.strip(),
              "configured": False, "configuration_state": "unconfigured"}
    if not url and not domain and not expected_addresses:
        return result
    try:
        validate_public_url(url)
        # Account-specific/token-bearing resolver paths are deliberately unsupported.
        if urlsplit(url).path != "/dns-query":
            raise ValueError("public_resolver_path_required")
        name = dns.name.from_text(domain)
        if not domain or len(name.labels) < 3 or any(not part for part in name.labels[:-1]):
            raise ValueError("absolute_domain_required")
        name.to_wire()
        addresses = [str(ipaddress.IPv4Address(value.strip()))
                     for value in expected_addresses.split(",") if value.strip()]
    except (ValueError, dns.exception.DNSException):
        result["configuration_state"] = "invalid"
        return result
    return {**result, "configured": True, "configuration_state": "configured",
            "domain": name.to_text(), "expected_addresses": addresses}


def validate_public_url(url: str) -> None:
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.port not in (None, 443)):
            raise ValueError("https_public_url_required")
    except ValueError:
        raise ValueError("https_public_url_required") from None


async def run_probe(client: httpx.AsyncClient, spec: dict) -> ProbeResult:
    """GET only; no redirects, cookies, credentials, or raw errors in result data."""
    client.cookies.clear()
    try:
        async with asyncio.timeout(PROBE_TIMEOUT_SECONDS):
            return await _run_probe(client, spec)
    except TimeoutError:
        return ProbeResult(False, detail="timeout")


async def _run_probe(client: httpx.AsyncClient, spec: dict) -> ProbeResult:
    if not spec.get("configured", True):
        return ProbeResult(False, detail="unconfigured")
    kind = spec.get("kind", "http")
    params, query = None, None
    headers = {"User-Agent": "MatchAll-Status/2.0"}
    try:
        if kind == "doh":
            query = dns.message.make_query(spec["domain"], "A")
            params = {"dns": base64.urlsafe_b64encode(query.to_wire()).decode().rstrip("=")}
            headers["Accept"] = "application/dns-message"
        async with client.stream("GET", spec["probe"], params=params, headers=headers,
                                 follow_redirects=False) as response:
            code = response.status_code
            if code not in spec.get("expect", [200]):
                return ProbeResult(False, code, "unexpected_http_status")
            # Plain HTTP checks intentionally claim reachability only.
            if kind == "http":
                return ProbeResult(True, code)
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=8192):
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    return ProbeResult(False, code, "response_too_large")
            if kind == "doh":
                if response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/dns-message":
                    return ProbeResult(False, code, "unexpected_content_type")
                answer = dns.message.from_wire(bytes(content))
                if not query.is_response(answer):
                    return ProbeResult(False, code, "dns_response_mismatch")
                if answer.rcode() != dns.rcode.NOERROR:
                    return ProbeResult(False, code, "dns_rcode_failure")
                chain = answer.resolve_chaining()
                addresses = {item.address for item in chain.answer or []
                             if item.rdtype == dns.rdatatype.A}
                if not addresses:
                    return ProbeResult(False, code, "dns_answer_missing")
                expected = set(spec.get("expected_addresses", []))
                if expected and not addresses.issubset(expected):
                    return ProbeResult(False, code, "dns_answer_mismatch")
                return ProbeResult(True, code)
            import json
            body = json.loads(content)
            if kind == "nextcloud":
                ok = (isinstance(body, dict) and body.get("installed") is True
                      and body.get("maintenance") is False and body.get("needsDbUpgrade") is False)
            elif kind == "readiness":
                ok = isinstance(body, dict) and body.get("ready") is True
            else:
                return ProbeResult(False, code, "unsupported_check")
            return ProbeResult(ok, code, "" if ok else "read_only_contract_failed")
    except httpx.TimeoutException:
        return ProbeResult(False, detail="timeout")
    except httpx.HTTPError:
        return ProbeResult(False, detail="transport_error")
    except (ValueError, KeyError, dns.exception.DNSException):
        return ProbeResult(False, detail="invalid_response")
