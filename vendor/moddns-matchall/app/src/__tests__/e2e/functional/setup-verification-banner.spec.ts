import { test, expect } from '@playwright/test';
import { registerMocks } from '../../mocks/registerMocks';
import { createMockAccount } from '../../mocks/apiMocks';

// E2E: Email verification banner appears on /setup when email not verified, then disappears after verification.

test.describe('Setup verification banner', () => {
  test('shows banner when unverified and hides after verification', async ({ page }) => {
    // Initial unverified account
    const unverified = { ...createMockAccount(), email_verified: false };
    await registerMocks(page, { accountOverride: unverified });

    await page.goto('/setup');
    const banner = page.getByTestId('verification-banner');
    await expect(banner).toBeVisible();
    await expect(banner).toContainText('your email is not verified');

    // Simulate verification: intercept current account call to return verified now
    // (UI flow to verify email is out of scope here; we focus on banner state reaction to account change)
    await page.route(/\/api\/v1\/accounts\/current(\/?|\?.*)$/i, route => {
      const verified = { ...unverified, email_verified: true };
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(verified) });
    });
    // Trigger refresh by reloading setup (store should rehydrate with verified account)
    await page.waitForTimeout(100);
    await page.reload();
    await expect(page.getByTestId('verification-banner')).toHaveCount(0); // banner no longer rendered
  });
});
