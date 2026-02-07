import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function ingestClosedCandle(request: APIRequestContext, candle_time: number, price: number) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    data: {
      series_id: "binance:futures:BTC/USDT:1m",
      candle: {
        candle_time,
        open: price,
        high: price,
        low: price,
        close: price,
        volume: 10
      }
    }
  });
  expect(res.ok()).toBeTruthy();
}

async function ensureScrollable(page: any) {
  await page.evaluate(() => {
    const el = document.querySelector('[data-testid="middle-scroll"]') as HTMLElement | null;
    if (!el) throw new Error("missing middle-scroll container");
    const spacer = document.createElement("div");
    spacer.setAttribute("data-testid", "e2e-scroll-spacer-wheel");
    spacer.style.height = "1600px";
    spacer.style.pointerEvents = "none";
    el.appendChild(spacer);
  });
}

test("wheel over chart zooms horizontally (no middle scroll) @smoke", async ({ page, request }) => {
  await page.addInitScript(() => localStorage.clear());
  const base = 60;
  for (let i = 0; i < 3; i++) {
    await ingestClosedCandle(request, base * (i + 1), i + 1);
  }
  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  const middle = page.getByTestId("middle-scroll");
  const chart = page.getByTestId("chart-view");
  await expect(middle).toBeVisible();
  await expect(chart).toBeVisible();
  await ensureScrollable(page);

  // Wait for chart to expose bar spacing.
  await expect(chart).toHaveAttribute("data-bar-spacing", /.+/);
  const barSpacingBefore = Number((await chart.getAttribute("data-bar-spacing")) ?? "0");
  expect(barSpacingBefore).toBeGreaterThan(0);

  // Give the middle scroll a non-zero scrollTop and verify chart wheel doesn't change it.
  await middle.evaluate((el) => (el.scrollTop = 200));
  const scrollTopBefore = await middle.evaluate((el) => el.scrollTop);
  expect(scrollTopBefore).toBeGreaterThan(0);

  // Hover the chart area to lock middle scrolling (app rule).
  const area = page.locator('[data-chart-area="true"]').first();
  const areaBox = await area.boundingBox();
  expect(areaBox).toBeTruthy();
  await page.mouse.move((areaBox?.x ?? 0) + (areaBox?.width ?? 0) / 2, (areaBox?.y ?? 0) + (areaBox?.height ?? 0) / 2);

  const box = await chart.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move((box?.x ?? 0) + (box?.width ?? 0) / 2, (box?.y ?? 0) + (box?.height ?? 0) / 2);
  await page.mouse.wheel(0, -260); // negative => zoom in on most platforms

  await expect.poll(async () => Number((await chart.getAttribute("data-bar-spacing")) ?? "0")).not.toBe(barSpacingBefore);
  const scrollTopAfter = await middle.evaluate((el) => el.scrollTop);
  expect(scrollTopAfter).toBe(scrollTopBefore);
});

test("wheel outside chart scrolls middle (no chart zoom) @smoke", async ({ page, request }) => {
  await page.addInitScript(() => localStorage.clear());
  const base = 60;
  for (let i = 0; i < 3; i++) {
    await ingestClosedCandle(request, base * (i + 1), i + 1);
  }
  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  const middle = page.getByTestId("middle-scroll");
  const chart = page.getByTestId("chart-view");
  await expect(middle).toBeVisible();
  await expect(chart).toBeVisible();
  await ensureScrollable(page);

  await expect(chart).toHaveAttribute("data-bar-spacing", /.+/);
  const barSpacingBefore = (await chart.getAttribute("data-bar-spacing")) ?? "";

  // Ensure we start at the top.
  await middle.evaluate((el) => (el.scrollTop = 0));
  const scrollTopBefore = await middle.evaluate((el) => el.scrollTop);
  expect(scrollTopBefore).toBe(0);

  // Move the pointer to a UI element that is outside the chart, then wheel to scroll.
  const outside = page.getByText("Factors").first();
  const outsideBox = await outside.boundingBox();
  expect(outsideBox).toBeTruthy();
  await page.mouse.move((outsideBox?.x ?? 0) + (outsideBox?.width ?? 0) / 2, (outsideBox?.y ?? 0) + (outsideBox?.height ?? 0) / 2);

  // Ensure chart-area hover lock is released.
  await expect.poll(async () => {
    return await middle.evaluate((el) => window.getComputedStyle(el).overflowY);
  }).not.toBe("hidden");

  await page.mouse.wheel(0, 360);

  await expect.poll(async () => middle.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const barSpacingAfter = (await chart.getAttribute("data-bar-spacing")) ?? "";
  expect(barSpacingAfter).toBe(barSpacingBefore);
});
