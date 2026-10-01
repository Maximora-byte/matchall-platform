import { test, expect } from "@playwright/test";

const service = () => ({
  key: "home", name: "MatchAll 主站", name_en: "MatchAll Home", category: "content",
  url: "https://www.maximoraverse.org/", status: "operational", stale: false,
  last_checked_at: Math.floor(Date.now() / 1000) - 10, last_success_at: Math.floor(Date.now() / 1000) - 10,
  uptime_30d: 99.995, sample_count_30d: 42542, successful_samples_30d: 42540,
  sample_count_24h: 1440, avg_latency: 123, coverage_ratio_30d: 99.8,
  coverage_start_at: 1788220800, coverage_end_at: 1790812800, coverage_complete_30d: false,
  check_type: "HTTPS GET", scope: "只读首页检查，不覆盖登录、上传或下载全过程。",
  probe_region: "MatchAll-" + "very-long-region-name-without-breaks".repeat(5),
});
const days = Array.from({ length: 30 }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, "0")}`, checks: 1440, uptime: 100 }));

async function mockStatus(page) {
  await page.route("**/api/status", (route) => route.fulfill({ json: {
    schema_version: 2, generated_at: Math.floor(Date.now() / 1000), stale_after_seconds: 180,
    services: [service()], incidents: [],
  } }));
  await page.route("**/api/status/history?days=30", (route) => route.fulfill({ json: { services: [{ key: "home", days }] } }));
}

test("probe information wraps without page or content overflow, including repeated keyboard toggles", async ({ page }) => {
  await mockStatus(page);
  await page.goto("/");
  await expect(page.locator("#summary")).toHaveClass("summary operational");
  const trigger = page.locator(".summary-line summary");
  const popup = page.locator(".summary-line dl");
  const initialWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  await trigger.focus();
  await page.keyboard.press("Enter");
  await expect(popup).toBeVisible();
  const dimensions = await popup.evaluate((el) => ({
    width: el.clientWidth, scrollWidth: el.scrollWidth,
    left: el.getBoundingClientRect().left, right: el.getBoundingClientRect().right,
    columns: getComputedStyle(el).gridTemplateColumns.split(" ").length,
    childrenFit: [...el.querySelectorAll("dd")].every((dd) => dd.scrollWidth <= dd.clientWidth),
  }));
  expect(dimensions.columns).toBe(1);
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.width);
  expect(dimensions.childrenFit).toBe(true);
  expect(dimensions.left).toBeGreaterThanOrEqual(0);
  expect(dimensions.right).toBeLessThanOrEqual(page.viewportSize().width);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(initialWidth);
  expect(initialWidth).toBeLessThanOrEqual(page.viewportSize().width);
  await page.keyboard.press("Enter");
  await expect(popup).toBeHidden();
  await trigger.click();
  await expect(popup).toBeVisible();
  await trigger.click();
  await expect(popup).toBeHidden();
});

test("service details retain precision, coverage, scope and interactive history", async ({ page }) => {
  await mockStatus(page);
  await page.goto("/");
  const row = page.locator("#home");
  await expect(row.locator(".metric").first()).toContainText("99.995%");
  await expect(row.locator(".metric").first()).toContainText("42542 样本");
  await row.locator("summary .service-title").click();
  await expect(row.locator("summary")).toHaveAttribute("aria-expanded", "true");
  await expect(row.locator(".service-detail")).toContainText("覆盖 99.8%");
  await expect(row.locator(".service-detail")).toContainText("不覆盖登录、上传或下载全过程");
  const history = page.viewportSize().width <= 560 ? row.locator(".mobile-history") : row.locator("summary .history-block");
  await expect(history.locator(".history-cell")).toHaveCount(30);
  await history.locator(".history-cell").first().click();
  await expect(history.locator(".history-readout")).toContainText("2026-09-01");
  await expect(row).toHaveAttribute("open", "");
  await row.locator("summary .service-title").click();
  await expect(row.locator(".service-detail")).toBeHidden();
});
