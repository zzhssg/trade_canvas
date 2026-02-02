import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "@playwright/test";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId(symbol: string) {
  return `binance:futures:${symbol}:1m`;
}

async function ingestClosedCandle(
  request: APIRequestContext,
  symbol: string,
  candle_time: number,
  ohlc: { open: number; high: number; low: number; close: number } = { open: 1, high: 2, low: 0.5, close: 1.5 }
) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    data: {
      series_id: seriesId(symbol),
      candle: { candle_time, volume: 10, ...ohlc }
    }
  });
  expect(res.ok()).toBeTruthy();
}

async function expectChartCanvasVisible(page: Page) {
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();
  await expect(page.locator('[data-chart-area="true"] canvas').first()).toBeVisible();
}

async function readBarSpacing(page: Page): Promise<number | null> {
  const raw = await page.getByTestId("chart-view").getAttribute("data-bar-spacing");
  if (!raw) return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

test("mouse wheel zoom works and survives live updates", async ({ page, request }) => {
  await page.addInitScript(() => localStorage.clear());

  const symbol = "BTC/USDT";
  // Seed enough candles so zooming has a visible effect (fitContent + wheel scale).
  for (let i = 1; i <= 180; i++) {
    const t = i * 60;
    await ingestClosedCandle(request, symbol, t, { open: 1, high: 2, low: 0.5, close: 1000 + i });
  }

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expectChartCanvasVisible(page);

  await expect.poll(() => readBarSpacing(page), { timeout: 10_000 }).not.toBeNull();
  const baseline = (await readBarSpacing(page))!;
  expect(baseline).toBeGreaterThan(0);

  const box = await page.locator('[data-chart-area="true"]').boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.move(box!.x + box!.width / 2, box!.y + box!.height / 2);
  await page.mouse.wheel(0, -600);
  await page.mouse.wheel(0, -600);

  await expect.poll(() => readBarSpacing(page), { timeout: 5_000 }).not.toBeNull();
  const zoomed = (await readBarSpacing(page))!;
  expect(Math.abs(zoomed - baseline)).toBeGreaterThan(1e-3);

  // Ensure a live update doesn't reset the zoom level.
  const nextTime = 181 * 60;
  await ingestClosedCandle(request, symbol, nextTime, { open: 1, high: 2, low: 0.5, close: 999_999 });
  await expect(page.getByTestId("chart-view")).toHaveAttribute("data-last-ws-candle-time", String(nextTime), {
    timeout: 10_000
  });

  await expect.poll(() => readBarSpacing(page), { timeout: 5_000 }).not.toBeNull();
  const afterLiveUpdate = (await readBarSpacing(page))!;
  expect(Math.abs(afterLiveUpdate - baseline)).toBeGreaterThan(1e-3);
});
