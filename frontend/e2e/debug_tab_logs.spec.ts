import { expect, test } from "@playwright/test";

import {
  buildSeriesId,
  ingestClosedCandlePrice,
  uniqueSymbol,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId(symbol: string) {
  return buildSeriesId(symbol, "5m");
}

test("live debug tab shows read+write logs", async ({ page, request }) => {
  const symbol = uniqueSymbol("TCDBG");
  const sid = seriesId(symbol);

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 5,
    uiState: buildDefaultUiState({
      symbol,
      timeframe: "5m",
      overrides: {
        bottomHeight: undefined,
      },
    }),
  });

  // Preload 1 candle to produce backend write logs (ring buffer).
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: sid,
    candleTime: 300,
    price: 1,
  });

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
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: sid,
    candleTime: 600,
    price: 1,
  });

  await expect
    .poll(async () => {
      const n = await page
        .locator('[data-testid="debug-log-row"][data-event="write.http.ingest_candle_closed_done"]')
        .count();
      return n;
    })
    .toBeGreaterThanOrEqual(2);
});
