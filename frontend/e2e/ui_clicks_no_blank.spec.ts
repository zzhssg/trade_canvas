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

function seriesId(symbol: string, timeframe = "1m") {
  return buildSeriesId(symbol, timeframe);
}

async function expectLiveLoadTransition(
  page: Page,
  args: { sidQuery: string; trigger: () => Promise<void> }
) {
  const chart = page.getByTestId("chart-view");
  const candlesRespPromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/market/candles") &&
      r.url().includes(args.sidQuery) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });

  await args.trigger();

  await expect
    .poll(async () => (await chart.getAttribute("data-live-load-status")) ?? "", { timeout: 4_000 })
    .toMatch(/loading|backfilling/);

  await candlesRespPromise;

  await expect
    .poll(async () => (await chart.getAttribute("data-live-load-status")) ?? "", { timeout: 8_000 })
    .toMatch(/ready|empty|backfilling/);
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
  const eth5mSeriesId = seriesId("ETH/USDT", "5m");
  const eth5mSidQuery = `series_id=${encodeURIComponent(eth5mSeriesId)}`;
  const delayedQueries = new Set<string>();
  await page.route("**/api/market/candles*", async (route) => {
    const url = route.request().url();
    if (url.includes(ethSidQuery) && !delayedQueries.has(ethSidQuery)) {
      delayedQueries.add(ethSidQuery);
      await page.waitForTimeout(450);
    } else if (url.includes(eth5mSidQuery) && !delayedQueries.has(eth5mSidQuery)) {
      delayedQueries.add(eth5mSidQuery);
      await page.waitForTimeout(450);
    }
    await route.continue();
  });

  await expectLiveLoadTransition(page, {
    sidQuery: ethSidQuery,
    trigger: async () => {
      await symbolSelect.selectOption({ label: "ETH/USDT" });
    }
  });
  const ethCandleResp = await request.get(`${apiBase}/api/market/candles`, {
    params: { series_id: ethSeriesId, limit: 2000 }
  });
  const ethPayload = (await ethCandleResp.json()) as GetCandlesResponse;
  expect(ethPayload.series_id).toContain("ETH/USDT");
  await expectChartCanvasVisible(page);

  const tf5mTag = page.getByTestId("timeframe-tag-5m");
  await expect(tf5mTag).toBeVisible();
  await expectLiveLoadTransition(page, {
    sidQuery: eth5mSidQuery,
    trigger: async () => {
      await tf5mTag.click();
    }
  });
  await expect(page.getByTestId("chart-view")).toHaveAttribute("data-series-id", eth5mSeriesId);
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
