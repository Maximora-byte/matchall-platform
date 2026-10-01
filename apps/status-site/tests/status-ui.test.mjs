import test from "node:test";
import assert from "node:assert/strict";
import {
  deriveOverall,
  HISTORY_TIMEZONE_NOTE,
  historyAggregate,
  historyCells,
  normalizeService,
  overallHeadline,
  uptimeLabel,
} from "../public/status-app.js";

test("unknown data stays unknown and is not converted to outage", () => {
  const item = normalizeService(
    { status: "operational", last_checked_at: 100 },
    500,
    180,
  );
  assert.equal(item.status, "unknown");
});

test("overall preserves all six public states", () => {
  assert.equal(
    deriveOverall([{ status: "operational" }, { status: "maintenance" }]),
    "maintenance",
  );
  assert.equal(
    deriveOverall([{ status: "degraded" }, { status: "partial_outage" }]),
    "partial_outage",
  );
  assert.equal(
    deriveOverall([{ status: "outage" }, { status: "unknown" }]),
    "outage",
  );
});

test("old API cannot claim a fresh operational state", () => {
  const item = normalizeService(
    { state: "operational", uptime: 100, avg_latency: 12 },
    500,
    180,
    [],
  );
  assert.equal(item.status, "unknown");
  assert.equal(item.compatibility, true);
});

test("history fallback is sample weighted", () => {
  const result = historyAggregate([
    { uptime: 100, checks: 90 },
    { uptime: 0, checks: 10 },
    { uptime: null, checks: 0 },
  ]);
  assert.equal(result.samples, 100);
  assert.equal(result.uptime, 90);
});

test("maintenance and missing history have distinct accessible labels", () => {
  const html = historyCells([
    { date: "2026-09-29", uptime: null, checks: 0, maintenance_minutes: 60 },
    { date: "2026-09-30", uptime: null, checks: 0 },
  ]);
  assert.match(html, /maintenance/);
  assert.match(html, /维护 60 分钟/);
  assert.match(html, /unknown/);
  assert.match(html, /无数据/);
});

test("history day timezone is explicit", () => {
  assert.equal(HISTORY_TIMEZONE_NOTE, "历史按 UTC 日统计");
});

test("uptime keeps three decimals and never rounds failed samples to 100", () => {
  assert.equal(
    uptimeLabel({
      uptime_30d: 99.995,
      sample_count_30d: 42542,
      successful_samples_30d: 42540,
    }),
    "99.995%",
  );
  assert.equal(
    uptimeLabel({
      uptime_30d: 99.9996,
      sample_count_30d: 1000000,
      successful_samples_30d: 999996,
    }),
    "99.999%",
  );
  assert.equal(
    uptimeLabel({
      uptime_30d: 100,
      sample_count_30d: 100,
      successful_samples_30d: 100,
    }),
    "100.000%",
  );
});

test("overall headline counts the affected service", () => {
  assert.equal(
    overallHeadline("outage", [
      { status: "outage" },
      { status: "operational" },
    ]),
    "1 项服务不可用",
  );
  assert.equal(
    overallHeadline("operational", [{ status: "operational" }]),
    "所有服务运行正常",
  );
});

test("missing history renders unknown rather than fake 100%", () => {
  const html = historyCells([{ date: "2026-09-30", uptime: null, checks: 0 }]);
  assert.match(html, /unknown/);
  assert.match(html, /无数据/);
  assert.doesNotMatch(html, /100\.00%/);
});
