import type { APIRequestContext } from "@playwright/test";
import { expect, test } from "@playwright/test";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId() {
  return "binance:futures:BTC/USDT:5m";
}

async function ingestClosedCandleForSeries(request: APIRequestContext, sid: string, candle_time: number, price: number) {
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    data: {
      series_id: sid,
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

test("live debug tab shows read+write logs", async ({ page, request }) => {
  await page.addInitScript(() => {
    localStorage.clear();
    localStorage.setItem(
      "trade-canvas-ui",
      JSON.stringify({
        version: 5,
        state: {
          exchange: "binance",
          market: "futures",
          symbol: "BTC/USDT",
          timeframe: "5m",
          toolRailWidth: 52,
          sidebarCollapsed: false,
          sidebarWidth: 280,
          bottomCollapsed: false,
          activeSidebarTab: "Market",
          activeBottomTab: "Ledger"
        }
      })
    );
  });

  // Preload 1 candle to produce backend write logs (ring buffer).
  await ingestClosedCandleForSeries(request, seriesId(), 300, 1);

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  // Open right sidebar Debug tab.
  const debugTab = page.locator('[data-testid="sidebar-tab-Debug"]');
  await expect(debugTab).toBeVisible();
  await debugTab.click();

  await expect(page.locator('[data-testid="debug-panel"]')).toBeVisible();

  // Must have both read+write logs.
  await expect
    .poll(async () => {
      const n = await page.locator('[data-testid="debug-log-row"][data-pipe="read"]').count();
      return n;
    })
    .toBeGreaterThan(0);

  await expect
    .poll(async () => {
      const n = await page.locator('[data-testid="debug-log-row"][data-pipe="write"]').count();
      return n;
    })
    .toBeGreaterThan(0);

  // Ingest another candle and ensure a new write event arrives.
  await ingestClosedCandleForSeries(request, seriesId(), 600, 1);

  await expect
    .poll(async () => {
      const n = await page.locator('[data-testid="debug-log-row"][data-event="write.http.ingest_candle_closed_done"]').count();
      return n;
    })
    .toBeGreaterThanOrEqual(2);
});
