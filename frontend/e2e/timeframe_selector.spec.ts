import { expect, test } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";
import {
  buildSeriesId,
  ingestClosedCandle,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
  uniqueSymbol,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId(symbol: string, tf: string) {
  return buildSeriesId(symbol, tf);
}

test("@smoke timeframe switch loads correct candles and follows WS", async ({ page, request }) => {
  const symbol = uniqueSymbol("TCTF");

  // Ensure persisted UI state doesn't leak between runs.
  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol, timeframe: "1m" }),
  });

  // Seed 1m (not strictly required, but matches the UX of landing on defaults).
  const seed1m: CandleSeed[] = [
    { candle_time: 60, open: 1, high: 2, low: 0.5, close: 111, volume: 10 },
    { candle_time: 120, open: 1, high: 2, low: 0.5, close: 222, volume: 10 }
  ];
  const seed4h: CandleSeed[] = [
    { candle_time: 0, open: 1, high: 2, low: 0.5, close: 12345, volume: 10 },
    { candle_time: 14400, open: 10, high: 20, low: 5, close: 99999, volume: 10 }
  ];

  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId(symbol, "1m"),
    candles: seed1m,
  });
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId(symbol, "4h"),
    candles: seed4h,
  });

  // Open live page and wait for initial load.
  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();

  // Switch timeframe to 4h.
  const tfTag = page.getByTestId("timeframe-tag-4h");
  await expect(tfTag).toBeVisible();

  const candlesRespPromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/market/candles") &&
      r.url().includes(`series_id=${encodeURIComponent(seriesId(symbol, "4h"))}`) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });

  await tfTag.click();

  const resp = await candlesRespPromise;
  const payload = (await resp.json()) as GetCandlesResponse;
  expect(payload.series_id).toBe(seriesId(symbol, "4h"));
  expect(payload.candles?.length).toBeGreaterThanOrEqual(2);
  expect(payload.candles[payload.candles.length - 1]?.close).toBe(99999);

  // UI exposes last candle values as data attributes.
  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-series-id", seriesId(symbol, "4h"));
  await expect(chart).toHaveAttribute("data-last-close", "99999");
  await expect(chart).toHaveAttribute("data-last-open", "10");
  await expect(chart).toHaveAttribute("data-last-time", "14400");

  // Trigger "finalized candle" for 4h: new candle_time=28800 open=10000 close=10001.
  await ingestClosedCandle(request, {
    apiBase,
    seriesId: seriesId(symbol, "4h"),
    candle: {
      candle_time: 28800,
      open: 10000,
      high: 10010,
      low: 9990,
      close: 10001,
      volume: 10,
    },
  });

  // Ensure frontend receives it via WS and UI updates concrete values.
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", "28800");
  await expect(chart).toHaveAttribute("data-last-time", "28800");
  await expect(chart).toHaveAttribute("data-last-open", "10000");
  await expect(chart).toHaveAttribute("data-last-close", "10001");
});
