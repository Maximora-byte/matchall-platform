const { chromium } = require('playwright');

(async () => {
  const base = process.env.TEST_ORIGIN || 'http://127.0.0.1:18086';
  const session = process.env.TEST_SESSION;
  if (!session) throw new Error('TEST_SESSION is required');
  const browser = await chromium.launch({
    executablePath: '/snap/bin/chromium',
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const context = await browser.newContext();
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => {
    if (message.type() === 'error') errors.push(message.text());
  });
  await page.setExtraHTTPHeaders({Cookie: `__Host-dns_session=${session}`});
  for (const width of [1280, 390, 320]) {
    await page.setViewportSize({width, height: 900});
    const response = await page.goto(base + '/', {waitUntil: 'networkidle'});
    if (!response || response.status() !== 200) throw new Error(`account status ${response && response.status()}`);
    if (await page.locator('#dns-ipv4').inputValue() !== '64.110.101.75') throw new Error('IPv4 value mismatch');
    if (await page.locator('#dns-ipv6').inputValue() !== '2603:c023:16:c400:0:249e:4aa8:be5a') throw new Error('IPv6 value mismatch');
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error(`account overflow ${width}`);
    await page.screenshot({path: `/tmp/dns-dual-stack-account-${width}.png`, fullPage: true});
  }
  const guide = await page.goto(base + '/guide', {waitUntil: 'networkidle'});
  if (!guide || guide.status() !== 200) throw new Error('guide status');
  if (!(await page.locator('#dual-stack').textContent()).includes('2603:c023:16:c400:0:249e:4aa8:be5a')) throw new Error('guide IPv6 missing');
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('guide overflow');
  if (errors.length) throw new Error('browser errors: ' + errors.join('; '));
  await browser.close();
  console.log('PASS account/guide dual-stack desktop and mobile layouts, values, no overflow or console errors');
})().catch(error => {
  console.error(error.message);
  process.exit(1);
});
