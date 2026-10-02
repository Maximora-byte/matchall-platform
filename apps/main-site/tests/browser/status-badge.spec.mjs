import { test, expect } from "@playwright/test";
import { REQUIRED_SERVICE_KEYS, STATUS_API } from "../../public/status-summary.js";

const fulfill = (route, response) => route.fulfill({
  ...response, headers: { "access-control-allow-origin": "http://127.0.0.1:4173" },
});

const payload = () => ({
  schema_version: 2, generated_at: Math.floor(Date.now() / 1000), stale_after_seconds: 180,
  services: REQUIRED_SERVICE_KEYS.map((key) => ({ key, status: "operational", last_checked_at: Math.floor(Date.now() / 1000) - 10, stale: false })),
});

test("badge uses actual API status and keeps a usable status link", async ({ page }) => {
  let data = payload();
  await page.route(STATUS_API, (route) => fulfill(route, { json: data }));
  await page.goto("/");
  const badge = page.locator(".status-pill");
  await expect(badge).toHaveAttribute("data-status", "operational");
  await expect(badge).toContainText("所有受监测服务运行正常");
  await expect(badge).toHaveAttribute("href", "https://status.maximoraverse.org/");
  await expect(badge).toBeVisible();
  const box = await badge.boundingBox();
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width);
  data.services[0].status = "outage";
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(badge).toHaveAttribute("data-status", "outage");
  await expect(badge).toContainText("部分受监测服务不可用");
});

test("missing, stale, malformed and failed responses never show green", async ({ page }) => {
  let mode = "healthy";
  await page.route(STATUS_API, (route) => {
    const data = payload();
    if (mode === "empty") data.services = [];
    if (mode === "incomplete") data.services.pop();
    if (mode === "stale") data.services[0].last_checked_at -= 200;
    if (mode === "stale-string") data.services[0].stale = "false";
    if (mode === "stale-number") data.services[0].stale = 0;
    if (mode === "missing-stale") delete data.services[0].stale;
    if (mode === "missing-window") delete data.stale_after_seconds;
    if (mode === "invalid-window") data.stale_after_seconds = "180";
    if (mode === "future-probe") data.services[0].last_checked_at = data.generated_at + 1;
    if (mode === "malformed-incident") {
      data.services[0].status = "outage";
      data.services[1].stale = null;
    }
    if (mode === "http") return fulfill(route, { status: 503, body: "unavailable" });
    if (mode === "malformed") return fulfill(route, { body: "not json" });
    if (mode === "network") return route.abort();
    return fulfill(route, { json: data });
  });
  await page.goto("/");
  const badge = page.locator(".status-pill");
  for (const failure of ["empty", "incomplete", "stale", "stale-string", "stale-number", "missing-stale",
    "missing-window", "invalid-window", "future-probe", "malformed-incident", "http", "malformed", "network"]) {
    mode = "healthy";
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await expect(badge).toHaveAttribute("data-status", "operational");
    mode = failure;
    await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
    await expect(badge).toHaveAttribute("data-status", "unknown");
    await expect(badge).toContainText("服务状态待确认");
  }
});

test("a once-healthy badge expires between refreshes and failed refresh clears prior health", async ({ page }) => {
  await page.clock.install();
  let mode = "healthy";
  await page.route(STATUS_API, (route) => {
    if (mode === "failed") return fulfill(route, { status: 503, body: "unavailable" });
    const data = payload();
    data.services[0].last_checked_at = Math.floor(Date.now() / 1000) - 175;
    return fulfill(route, { json: data });
  });
  await page.goto("/");
  const badge = page.locator(".status-pill");
  await expect(badge).toHaveAttribute("data-status", "operational");
  await page.clock.runFor(6100);
  await expect(badge).toHaveAttribute("data-status", "unknown");
  await page.clock.setSystemTime(new Date());
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(badge).toHaveAttribute("data-status", "operational");
  mode = "failed";
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(badge).toHaveAttribute("data-status", "unknown");
});

test.describe("no JavaScript", () => {
  test.use({ javaScriptEnabled: false });
  test("static fallback is unknown and the status page remains reachable", async ({ page }) => {
    await page.goto("/");
    const badge = page.locator(".status-pill");
    await expect(badge).toHaveAttribute("data-status", "unknown");
    await expect(badge).toContainText("服务状态待确认");
    await expect(badge).toHaveAttribute("href", "https://status.maximoraverse.org/");
  });
});
