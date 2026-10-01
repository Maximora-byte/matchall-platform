import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { registerMocks } from '../../mocks/registerMocks';

test.describe('@layout Accessibility - Home (mobile)', () => {
  test.beforeEach(async ({ page }) => {
    await registerMocks(page, { authenticated: true, customProfiles: [{ id: 'prof_1', name: 'Default' }] });
  });

  test('has no serious a11y violations (filtered)', async ({ page }) => {
    await page.goto('/home');
    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .disableRules(['landmark-one-main'])
      .analyze();
    const IGNORE_IDS = ['button-name', 'color-contrast'];
    // Ignore scrollable-region-focusable if only caused by dev overlay (vite-error-overlay root element)
    const filtered = results.violations.filter(v => {
      if (IGNORE_IDS.includes(v.id)) return false;
      if (v.id === 'scrollable-region-focusable') {
        const onlyOverlay = v.nodes.every(n => n.target.join(' ').includes('vite-error-overlay'));
        if (onlyOverlay) return false;
      }
      return true;
    });
    const serious = filtered.filter(v => ['serious', 'critical'].includes(v.impact || ''));
    expect(serious, JSON.stringify(serious, null, 2)).toHaveLength(0);
  });
});
