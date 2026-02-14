import { expect, test } from "@playwright/test";

import { initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";

test("oracle/settings pages use standalone layout without live side rails", async ({ page }) => {
  await initTradeCanvasStorage(page, { clear: true });

  await page.goto(`${frontendBase}/settings`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Settings (MVP placeholder)")).toBeVisible();
  await expect(page.getByTestId("middle-scroll")).toHaveCount(0);
  await expect(page.getByTestId("bottom-tabs")).toHaveCount(0);
  await expect(page.locator('[data-testid="sidebar-tab-Market"]')).toHaveCount(0);

  await page.goto(`${frontendBase}/oracle`, { waitUntil: "domcontentloaded" });
  await expect(page.getByText("Trade Oracle")).toBeVisible();
  await expect(page.getByTestId("middle-scroll")).toHaveCount(0);
  await expect(page.getByTestId("bottom-tabs")).toHaveCount(0);
  await expect(page.locator('[data-testid="sidebar-tab-Market"]')).toHaveCount(0);
});
