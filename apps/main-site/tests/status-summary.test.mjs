import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { deriveStatusSummary, fetchStatusPayload, REQUIRED_SERVICE_KEYS, STATUS_API } from "../public/status-summary.js";

const now = 2_000_000_000;
const payload = () => ({
  schema_version: 2, generated_at: now, stale_after_seconds: 180,
  services: REQUIRED_SERVICE_KEYS.map((key) => ({ key, status: "operational", last_checked_at: now - 10, stale: false })),
});

test("green requires fresh probes for the complete monitored registry", () => {
  assert.equal(deriveStatusSummary(payload(), now).status, "operational");
  for (const mutate of [
    (data) => { data.services = []; },
    (data) => { data.services.pop(); },
    (data) => { data.services[0] = null; },
    (data) => { data.services[0].key = data.services[1].key; },
    (data) => { data.services[0].status = "unexpected"; },
    (data) => { delete data.services[0].last_checked_at; },
    (data) => { data.services[0].last_checked_at = null; },
    (data) => { data.services[0].last_checked_at = "2000000000"; },
    (data) => { data.services[0].stale = true; },
    (data) => { data.schema_version = 1; },
    (data) => { delete data.generated_at; },
    (data) => { data.generated_at = now - 181; },
    (data) => { data.generated_at = now + 1; },
    (data) => { data.services[0].last_checked_at = now + 1; },
  ]) {
    const data = payload();
    mutate(data);
    assert.equal(deriveStatusSummary(data, now).status, "unknown");
  }
  assert.equal(deriveStatusSummary(null, now).status, "unknown");
  assert.equal(deriveStatusSummary({}, now).status, "unknown");
});

test("one old service or elapsed time expires health, even with a newly generated response", () => {
  const data = payload();
  data.services[0].last_checked_at = now - 180;
  assert.equal(deriveStatusSummary(data, now).status, "operational");
  assert.equal(deriveStatusSummary(data, now + 1).status, "unknown");
  data.generated_at = now + 1;
  data.stale_after_seconds = 3600;
  assert.equal(deriveStatusSummary(data, now + 1).status, "unknown");
});

test("all six states retain status-page priority and known incidents remain visible", () => {
  for (const state of ["degraded", "partial_outage", "outage", "maintenance", "unknown"]) {
    const data = payload();
    data.services[0].status = state;
    assert.equal(deriveStatusSummary(data, now).status, state);
  }
  const data = payload();
  data.services[0].status = "outage";
  data.services[1].last_checked_at = now - 181;
  assert.equal(deriveStatusSummary(data, now).status, "outage");
});

test("additional unconfigured services prevent green without hiding known incidents", () => {
  const data = payload();
  data.services.push({ key: "dns", status: "unknown", last_checked_at: null });
  assert.equal(deriveStatusSummary(data, now).status, "unknown");
  data.services[0].status = "degraded";
  assert.equal(deriveStatusSummary(data, now).status, "degraded");
});

test("status requests use the public endpoint without cookies or cached health", async () => {
  const controller = new AbortController();
  const data = await fetchStatusPayload(async (url, options) => {
    assert.equal(url, STATUS_API);
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.equal(options.signal, controller.signal);
    return { ok: true, json: async () => payload() };
  }, controller.signal);
  assert.equal(deriveStatusSummary(data, now).status, "operational");
});

test("HTTP, network and malformed JSON failures are rejected rather than made healthy", async () => {
  await assert.rejects(fetchStatusPayload(async () => ({ ok: false })), /unavailable/);
  await assert.rejects(fetchStatusPayload(async () => { throw new Error("network"); }), /network/);
  await assert.rejects(fetchStatusPayload(async () => ({ ok: true, json: async () => { throw new SyntaxError("bad JSON"); } })), /bad JSON/);
});

test("badge expectations track the actual Hub registry", async () => {
  const source = await readFile(new URL("../../../services/hub/app.py", import.meta.url), "utf8");
  const registry = source.match(/SERVICES = \[([\s\S]*?)\n\]/)[1];
  const keys = [...registry.matchAll(/"key": "([^"]+)"/g)].map((match) => match[1]);
  assert.deepEqual([...REQUIRED_SERVICE_KEYS].sort(), keys.sort());
});
