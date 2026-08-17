// Playwright smoke test for PR #38's UI overhaul.
//
// Catches the "the whole app is broken" class of regression from the
// ~1,350-line CSS diff + Sidebar/ChatPanel/ToolActivity rewrites in PR #38.
//
// Not wired into CI yet — Playwright isn't installed in this repo (see
// research/benchmarks-frontend-graphviz PR for the recommended install).
// To run locally:
//   npm install --save-dev @playwright/test
//   npx playwright install chromium
//   (start backend on :8000 and frontend on :5173)
//   npx playwright test frontend/e2e/pr-38-smoke.spec.js

const { test, expect } = require('@playwright/test');

const APP_URL = process.env.APP_URL || 'http://localhost:5173';

test.describe('PR #38 UI smoke', () => {
  test('app loads with Claude-style sidebar', async ({ page }) => {
    await page.goto(APP_URL);
    // Sidebar is present in some form
    await expect(page.locator('aside, [class*="sidebar" i]').first()).toBeVisible({
      timeout: 10_000,
    });
  });

  test('legacy upload panel is gone', async ({ page }) => {
    await page.goto(APP_URL);
    // The old UploadPanel was deleted in PR #38 — assert it doesn't come back
    const legacy = page.locator('[data-testid="upload-panel"], .upload-panel');
    await expect(legacy).toHaveCount(0);
  });

  test('chat send shows an in-progress phase, then a result', async ({ page }) => {
    await page.goto(APP_URL);
    const input = page.getByRole('textbox').first();
    await input.fill('list phases');
    await input.press('Enter');

    // In-progress indicator appears within a few seconds (added by PR #38)
    await expect(
      page.getByText(/in progress|thinking|working/i).first()
    ).toBeVisible({ timeout: 8_000 });

    // Result eventually settles with a known phase name
    await expect(page.getByText(/Pre-requisites/i).first()).toBeVisible({
      timeout: 30_000,
    });
  });

  test('only the chat area scrolls, not the whole viewport', async ({ page }) => {
    await page.goto(APP_URL);
    // Push a lot of content into the chat to force scroll
    const input = page.getByRole('textbox').first();
    for (let i = 0; i < 6; i++) {
      await input.fill(`test scroll message ${i}`);
      await input.press('Enter');
      await page.waitForTimeout(200);
    }

    // Body/html shouldn't gain a scrollbar — PR #38 fixed this
    const bodyScrollHeight = await page.evaluate(
      () => document.body.scrollHeight - window.innerHeight
    );
    // Allow a small tolerance; the point is it's not a fully-scrollable viewport
    expect(bodyScrollHeight).toBeLessThan(200);
  });
});
