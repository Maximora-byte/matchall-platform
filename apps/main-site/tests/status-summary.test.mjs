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

async function badgeHarness(t, fetchImpl) {
  const { mountStatusBadge } = await import("../public/status-summary.js");
  const previousDocument = globalThis.document;
  const listeners = new Map();
  const label = { textContent: "服务状态待确认" };
  const element = { dataset: { status: "unknown" }, querySelector: () => label };
  globalThis.document = {
    hidden: false,
    addEventListener: (name, callback) => listeners.set(name, callback),
    removeEventListener: (name) => listeners.delete(name),
  };
  t.mock.method(globalThis, "fetch", fetchImpl);
  t.mock.timers.enable({ apis: ["Date", "setTimeout", "setInterval"], now: now * 1000 });
  const dispose = mountStatusBadge(element);
  t.after(() => { dispose(); globalThis.document = previousDocument; });
  const settle = async () => { for (let i = 0; i < 10; i += 1) await Promise.resolve(); };
  await settle();
  return { element, label, settle, resume: () => listeners.get("visibilitychange")() };
}

test("mounted badge expires old probes without another HTTP response", async (t) => {
  const data = payload();
  data.services[0].last_checked_at = now - 179;
  let calls = 0;
  const { element, label } = await badgeHarness(t, async () => {
    calls += 1;
    return { ok: true, json: async () => data };
  });
  assert.equal(element.dataset.status, "operational");
  t.mock.timers.tick(2000);
  assert.equal(element.dataset.status, "unknown");
  assert.equal(label.textContent, "服务状态待确认");
  assert.equal(calls, 1);
});

test("mounted badge clears prior health on refresh failure", async (t) => {
  let failed = false;
  const { element, label, resume, settle } = await badgeHarness(t, async () => {
    if (failed) throw new Error("offline");
    return { ok: true, json: async () => payload() };
  });
  assert.equal(element.dataset.status, "operational");
  failed = true;
  resume();
  await settle();
  assert.equal(element.dataset.status, "unknown");
  assert.equal(label.textContent, "服务状态待确认");
});

test("mounted badge times out and an older aborted refresh cannot overwrite the latest response", async (t) => {
  let mode = "healthy";
  const { element, resume, settle } = await badgeHarness(t, async (_url, options) => {
    if (mode === "waiting") return new Promise((_resolve, reject) => {
      options.signal.addEventListener("abort", () => reject(new Error("aborted")));
    });
    return { ok: true, json: async () => payload() };
  });
  mode = "waiting";
  resume();
  t.mock.timers.tick(6000);
  await settle();
  assert.equal(element.dataset.status, "unknown");
  resume();
  mode = "healthy";
  resume();
  await settle();
  assert.equal(element.dataset.status, "operational");
});
