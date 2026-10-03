import { test, expect } from "@playwright/test";

const consoleURL = "https://console.maximoraverse.org/login";
const guideURL = "https://docs.maximoraverse.org/docs/getting-started/";
const registerURL = "https://auth.maximoraverse.org/register";
const destinations = new Map([
  [consoleURL, "Synthetic console login"],
  [guideURL, "Synthetic getting started guide"],
  [registerURL, "Synthetic invitation registration"],
]);

test.beforeEach(async ({ context, baseURL }) => {
  const localOrigin = new URL(baseURL).origin;
  const fixtures = new Map([...destinations, [new URL("/contact/", baseURL).href, "Synthetic contact support"]]);
  await context.route("**/*", (route) => {
    const request = route.request();
    const url = request.url();
    // Follow links without contacting production, including on failure or redirects.
    if (request.isNavigationRequest() && fixtures.has(url)) {
      return route.fulfill({
        contentType: "text/html; charset=utf-8",
        body: `<!doctype html><html><body><h1>${fixtures.get(url)}</h1></body></html>`,
      });
    }
    return new URL(url).origin === localOrigin ? route.continue() : route.abort();
  });
});

function entryLinks(page, names = ["登录控制台", "已有账户，登录控制台", "第一次使用，查看指南", "没有邀请码？联系支持"]) {
  const main = page.getByRole("main");
  return [
    [page.getByRole("banner").getByRole("link", { name: names[0], exact: true }), consoleURL],
    [main.getByRole("link", { name: names[1], exact: true }), consoleURL],
    [main.getByRole("link", { name: names[2], exact: true }), guideURL],
    [main.getByRole("link", { name: names[3], exact: true }), "/contact/"],
  ];
}

async function expectUsableEntries(page, names) {
  for (const [link, href] of entryLinks(page, names)) {
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", href);
    const box = await link.boundingBox();
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(page.viewportSize().width);
  }
  await expect(entryLinks(page, names)[0][0]).toBeInViewport();
  // The existing desktop orbit artwork extends beyond the shell; mobile content must fit.
  if (page.viewportSize().width <= 720) {
    expect(await page.evaluate(() => document.documentElement.scrollWidth))
      .toBeLessThanOrEqual(page.viewportSize().width);
  }
}

test("new and returning visitors have distinct visible entry paths", async ({ page }) => {
  await page.goto("/?lang=zh");
  await expectUsableEntries(page);
  const hero = page.locator("main .hero");
  await expect(hero).toContainText(/注册.*邀请码|邀请码.*注册/);
  await expect(hero).toContainText(/服务.*权限/);
  await expect(hero).toContainText(/单独|分别|另行|不等于|不代表/);
  const registration = page.getByRole("main").getByRole("link", { name: "使用邀请码注册", exact: true });
  await expect(registration).toHaveCount(1);
  await expect(registration).toHaveAttribute("href", registerURL);
});

for (const [locale, names, note] of [
  ["en", ["Sign in", "Have an account? Sign in", "New here? Start with the guide", "No invite? Contact support"],
    "Registration requires a valid invite"],
  ["ja", ["ログイン", "アカウントをお持ちの方：ログイン", "初めての方：利用ガイド", "招待コードがない方：お問い合わせ"],
    "新規登録には有効な招待コードが必要です。"],
]) {
  test(`${locale} entry labels and guidance translate and stay on screen`, async ({ page }) => {
    await page.goto(`/?lang=${locale}`);
    await expectUsableEntries(page, names);
    await expect(page.locator("main .hero")).toContainText(note);
  });
}

test("entry links navigate to login, the guide, support, and invitation registration", async ({ page, baseURL }) => {
  await page.goto("/?lang=zh");
  const links = [
    ...entryLinks(page),
    [page.getByRole("main").getByRole("link", { name: "使用邀请码注册", exact: true }), registerURL],
  ];
  for (const [link, href] of links) {
    await page.goto("/?lang=zh");
    await link.click();
    await expect(page).toHaveURL(new URL(href, baseURL).href);
    await expect(page.getByRole("heading", {
      level: 1,
      name: destinations.get(href) ?? "Synthetic contact support",
      exact: true,
    })).toBeVisible();
  }
});

test("the existing service menu opens by keyboard and restores focus after Escape", async ({ page }) => {
  await page.goto("/?lang=zh");
  const trigger = page.getByRole("button", { name: "打开服务菜单", exact: true });
  await expect(trigger).toHaveCount(1);
  await expect(trigger).toBeVisible();
  // Reach the menu through the real tab order rather than forcing DOM focus.
  for (let step = 0; step < 20 && !(await trigger.evaluate((element) => element === document.activeElement)); step++) {
    await page.keyboard.press("Tab");
  }
  await expect(trigger).toBeFocused();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "MatchAll 服务菜单", exact: true });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole("link", { name: "总览", exact: true })).toBeFocused();
  await expect(dialog.getByRole("link", { name: "控制台", exact: true }))
    .toHaveAttribute("href", "https://console.maximoraverse.org/");
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(entryLinks(page)[0][0]).toBeVisible();
});

test.describe("no JavaScript", () => {
  test.use({ javaScriptEnabled: false });
  test("primary entry links remain visible and navigate without the menu script", async ({ page }) => {
    await page.goto("/?lang=zh");
    await expectUsableEntries(page);
    await entryLinks(page)[2][0].click();
    await expect(page).toHaveURL(guideURL);
    await expect(page.getByRole("heading", { level: 1, name: destinations.get(guideURL) })).toBeVisible();
  });
});
