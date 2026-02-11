import { expect, test } from "@playwright/test";

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

test("backtest tab runs a backtest and prints output", async ({ page, request }) => {
  await initTradeCanvasStorage(page, { clear: true });

  // Seed a tiny candle history so Live chart loads cleanly.
  const seed: CandleSeed[] = [
    { candle_time: 60, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 },
    { candle_time: 120, open: 1, high: 2, low: 0.5, close: 1.5, volume: 10 }
  ];
  await ingestClosedCandlesWithFallback(request, {
    apiBase,
    seriesId: seriesId("BTC/USDT"),
    candles: seed,
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  await expect(page.locator('[data-chart-area="true"] canvas').first()).toBeVisible();

  await page.getByTestId("bottom-tab-Backtest").click();
  await expect(page.getByTestId("backtest-panel")).toBeVisible();

  const strategySelect = page.getByTestId("backtest-strategy-select");
  await expect(strategySelect).toBeVisible();
  await expect(strategySelect).toHaveValue("DemoStrategy");

  await page.getByTestId("backtest-timerange").fill("20260130-20260201");

  const runRespPromise = page.waitForResponse((r) => {
    return r.url().includes("/api/backtest/run") && r.request().method() === "POST" && r.status() === 200;
  });
  await page.getByTestId("backtest-run").click();
  const runResp = await runRespPromise;
  const payload = (await runResp.json()) as { ok: boolean };
  expect(payload.ok).toBeTruthy();

  const out = page.getByTestId("backtest-output");
  await expect(out).toContainText("TRADE_CANVAS MOCK BACKTEST");
  await expect(out).toContainText("strategy=DemoStrategy");
  await expect(out).toContainText("pair=BTC/USDT");
  await expect(out).toContainText("timeframe=1m");
  await expect(out).toContainText("timerange=20260130-20260201");
});
