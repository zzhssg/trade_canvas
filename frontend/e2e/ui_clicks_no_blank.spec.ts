import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";
import {
  buildSeriesId,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
} from "./helpers/marketIngest";
import { initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function seriesId(symbol: string) {
  return buildSeriesId(symbol, "1m");
}

async function expectChartCanvasVisible(page: Page) {
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible();
  await expect(page.locator('[data-chart-area="true"] canvas').first()).toBeVisible();
}

test("@smoke clicking tabs / changing symbol does not blank the app", async ({ page, request }) => {
  // Ensure persisted UI state doesn't leak between runs.
  await initTradeCanvasStorage(page, { clear: true });

  // Seed two series so symbol switching keeps a non-empty chart.
  const btcSeed: CandleSeed[] = [
    { candle_time: 60, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
    { candle_time: 120, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 }
  ];
  const ethSeed: CandleSeed[] = [
    { candle_time: 60, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
    { candle_time: 120, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 }
  ];
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId("BTC/USDT"),
    candles: btcSeed,
  });
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId("ETH/USDT"),
    candles: ethSeed,
  });

  const pageErrors: string[] = [];
  page.on("pageerror", (err) => pageErrors.push(err.message));

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expectChartCanvasVisible(page);

  // Sidebar tab switching should not affect chart rendering.
  await page.getByRole("button", { name: "Strategy" }).first().click();
  await page.getByRole("button", { name: "Market" }).first().click();
  await expectChartCanvasVisible(page);

  // Changing symbol should reload candles and keep chart canvas alive.
  // Ensure we actually change from a different symbol (fresh context should be BTC/USDT by default).
  const symbolSelect = page.getByTestId("symbol-select");
  await expect(symbolSelect).toHaveValue("BTC/USDT");

  const ethSeriesId = seriesId("ETH/USDT");
  const ethSidQuery = `series_id=${encodeURIComponent(ethSeriesId)}`;
  const candlesRespPromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/market/candles") &&
      r.url().includes(ethSidQuery) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });
  await symbolSelect.selectOption({ label: "ETH/USDT" });
  const candlesResp = await candlesRespPromise;
  const payload = (await candlesResp.json()) as GetCandlesResponse;
  expect(payload.series_id).toContain("ETH/USDT");
  await expectChartCanvasVisible(page);

  // Route/page switching should also not cause a blank screen.
  const backtestRouteLink = page.getByRole("link", { name: "Backtest" });
  if (await backtestRouteLink.count()) {
    await backtestRouteLink.click();
  } else {
    await page.getByRole("button", { name: "Backtest" }).first().click();
  }
  await expect(page.getByText("Backtest (freqtrade)")).toBeVisible();

  await page.getByRole("link", { name: "Settings" }).click();
  await page.getByRole("link", { name: "Live" }).click();
  await expectChartCanvasVisible(page);

  expect(pageErrors).toEqual([]);
});
