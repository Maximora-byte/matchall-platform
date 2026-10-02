import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { deriveStatusSummary, fetchStatusPayload, REQUIRED_SERVICE_KEYS, STATUS_API } from "../public/status-summary.js";

const now = 2_000_000_000;
const payload = () => ({
  schema_version: 2, generated_at: now, stale_after_seconds: 180,
  services: REQUIRED_SERVICE_KEYS.map((key) => ({ key, status: "operational", last_checked_at: now - 10, stale: false })),
});

test("DNS coverage is required and its incidents and stale data affect the headline", () => {
  const data = payload();
  assert.ok(REQUIRED_SERVICE_KEYS.includes("dns"));
  data.services = data.services.filter((service) => service.key !== "dns");
  assert.equal(deriveStatusSummary(data, now).status, "unknown");
  data.services.push({ key: "dns", status: "outage", last_checked_at: now - 10, stale: false });
  assert.equal(deriveStatusSummary(data, now).status, "outage");
  data.services.at(-1).status = "operational";
  assert.equal(deriveStatusSummary(data, now).status, "operational");
  data.services.at(-1).stale = true;
  assert.equal(deriveStatusSummary(data, now).status, "unknown");
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

test("stale_after_seconds must be a positive safe integer without fallback coercion", () => {
  for (const value of [undefined, null, "180", "", true, false, 0, -1, 0.5, 180.5, NaN, Infinity, -Infinity, Number.MAX_SAFE_INTEGER + 1, [], {}]) {
    const data = payload();
    if (value === undefined) delete data.stale_after_seconds;
    else data.stale_after_seconds = value;
    assert.equal(deriveStatusSummary(data, now).status, "unknown", `freshness window: ${String(value)}`);
  }
});

test("valid freshness windows are honored for response and probes, with a local upper limit", () => {
  const data = payload();
  data.stale_after_seconds = 10;
  assert.equal(deriveStatusSummary(data, now).status, "operational");
  assert.equal(deriveStatusSummary(data, now + 0.5).status, "unknown");
  data.services.forEach((service) => { service.last_checked_at = now; });
  assert.equal(deriveStatusSummary(data, now + 10).status, "operational");
  assert.equal(deriveStatusSummary(data, now + 10.5).status, "unknown");
  data.stale_after_seconds = Number.MAX_SAFE_INTEGER;
  assert.equal(deriveStatusSummary(data, now + 180).status, "operational");
  assert.equal(deriveStatusSummary(data, now + 180.5).status, "unknown");
});

test("stale must be an explicit boolean on every service", () => {
  for (const value of [undefined, null, "false", "true", 0, 1, "", [], {}]) {
    const data = payload();
    if (value === undefined) delete data.services[0].stale;
    else data.services[0].stale = value;
    assert.equal(deriveStatusSummary(data, now).status, "unknown", `stale: ${String(value)}`);
  }
  const data = payload();
  data.services[0].stale = true;
  assert.equal(deriveStatusSummary(data, now).status, "unknown");
});

test("API timestamps must be positive safe integer seconds and cannot claim future probes", () => {
  for (const field of ["generated_at", "last_checked_at"]) {
    for (const value of [undefined, null, "2000000000", true, false, 0, -1, now - 0.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1, [], {}, now + 1]) {
      const data = payload();
      const target = field === "generated_at" ? data : data.services[0];
      if (value === undefined) delete target[field];
      else target[field] = value;
      assert.equal(deriveStatusSummary(data, now).status, "unknown", `${field}: ${String(value)}`);
    }
  }
  const data = payload();
  data.generated_at = now - 5;
  data.services[0].last_checked_at = now - 1;
  assert.equal(deriveStatusSummary(data, now).status, "unknown", "probe cannot be newer than its response");
  for (const clock of [null, "2000000000", false, 0, -1, NaN, Infinity]) {
    assert.equal(deriveStatusSummary(payload(), clock).status, "unknown", `clock: ${String(clock)}`);
  }
});

test("malformed response shapes fail closed even when another service reports an incident", () => {
  for (const data of [undefined, null, [], "healthy", 1, true]) {
    assert.equal(deriveStatusSummary(data, now).status, "unknown");
  }
  for (const mutate of [
    (data) => { data.schema_version = "2"; },
    (data) => { delete data.services; },
    (data) => { data.services = {}; },
    (data) => { data.services.pop(); },
    (data) => { data.services[1] = null; },
    (data) => { data.services[1] = []; },
    (data) => { delete data.services[1]; },
    (data) => { data.services[1].key = data.services[0].key; },
    (data) => { delete data.services[1].key; },
    (data) => { data.services[1].key = 1; },
    (data) => { data.services[1].key = " "; },
    (data) => { data.services[1].status = "unexpected"; },
    (data) => { data.services[1].status = null; },
    (data) => { delete data.services[1].status; },
    (data) => { data.services[1].stale = "false"; },
    (data) => { data.services[1].last_checked_at = null; },
    (data) => { data.services.push({ key: "dns", status: "operational", last_checked_at: now }); },
  ]) {
    const data = payload();
    data.services[0].status = "outage";
    mutate(data);
    assert.equal(deriveStatusSummary(data, now).status, "unknown");
  }
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
  data.services.push({ key: "additional-service", status: "unknown", last_checked_at: null, stale: true });
  assert.equal(deriveStatusSummary(data, now).status, "unknown");
  data.services[0].status = "degraded";
  assert.equal(deriveStatusSummary(data, now).status, "degraded");
});

test("legitimate stale and unprobed services retain another service's known incident", () => {
  for (const state of ["unknown", "maintenance"]) {
    for (const timestamp of [null, now - 181]) {
      const data = payload();
      data.services[0].last_checked_at = timestamp;
      data.services[0].stale = true;
      data.services[0].status = state;
      assert.equal(deriveStatusSummary(data, now).status, "unknown");
      data.services[1].status = "outage";
      assert.equal(deriveStatusSummary(data, now).status, "outage");
    }
  }
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
  keys.push(...[...source.matchAll(/SERVICES\.append\(\{"key": "([^"]+)"/g)].map((match) => match[1]));
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

test("mounted badge clears prior health on malformed refresh and recovers from valid data", async (t) => {
  let data = payload();
  const { element, label, resume, settle } = await badgeHarness(t, async () => ({
    ok: true, json: async () => data,
  }));
  assert.equal(element.dataset.status, "operational");
  data = payload();
  data.services[0].stale = "false";
  resume();
  await settle();
  assert.equal(element.dataset.status, "unknown");
  assert.equal(label.textContent, "服务状态待确认");
  data = payload();
  resume();
  await settle();
  assert.equal(element.dataset.status, "operational");
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
