import { expect, test } from "@playwright/test";

import {
  ingestClosedCandlesWithFallback,
  type CandleSeed,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ??
  process.env.VITE_API_BASE ??
  process.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

const TIMEFRAMES = [
  { label: "1m", step: 60 },
  { label: "5m", step: 300 },
] as const;

function seriesIdOf(symbol: string, timeframe: string): string {
  return `binance:futures:${symbol}:${timeframe}`;
}

function buildWave(step: number): CandleSeed[] {
  const segment = 40;
  const total = segment * 4;
  const candles: CandleSeed[] = [];
  for (let i = 0; i < total; i += 1) {
    const v =
      i < segment
        ? i + 1
        : i < segment * 2
          ? segment - (i - segment)
          : i < segment * 3
            ? i - segment * 2 + 1
            : segment - (i - segment * 3);
    candles.push({
      candle_time: step * (i + 1),
      open: v,
      high: v,
      low: v,
      close: v,
      volume: 10,
    });
  }
  return candles;
}

function buildTopMarketItems(symbols: string[]) {
  return symbols.map((symbol, idx) => ({
    exchange: "binance",
    market: "futures",
    symbol,
    symbol_id: symbol.replace("/", ""),
    base_asset: symbol.split("/")[0],
    quote_asset: "USDT",
    last_price: 200 + idx,
    quote_volume: 1_000_000 - idx * 10_000,
    price_change_percent: 1.2 + idx * 0.1,
  }));
}

test("live browse/click flow captures screenshots @smoke @mainflow", async ({ page, request }) => {
  test.setTimeout(120_000);
  const runId = Date.now().toString(36).toUpperCase();
  const symbols = [`BTCBR${runId}/USDT`, `ETHBR${runId}/USDT`, `SOLBR${runId}/USDT`];

  for (const symbol of symbols) {
    for (const timeframe of TIMEFRAMES) {
      await ingestClosedCandlesWithFallback(request, {
        apiBase,
        seriesId: seriesIdOf(symbol, timeframe.label),
        candles: buildWave(timeframe.step),
      });
    }
  }

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: symbols[0], timeframe: "1m" }),
  });

  await page.route("**/api/market/top_markets/stream*", async (route) => {
    await route.abort();
  });
  await page.route("**/api/market/top_markets*", async (route) => {
    const url = new URL(route.request().url());
    const market = url.searchParams.get("market") ?? "futures";
    const limit = Number(url.searchParams.get("limit") ?? "20");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        exchange: "binance",
        market,
        quote_asset: "USDT",
        limit,
        generated_at_ms: Date.now(),
        cached: false,
        items: buildTopMarketItems(symbols).slice(0, Math.max(1, limit)),
      }),
    });
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  const symbolSelect = page.getByTestId("symbol-select");

  const expectChartReady = async (symbol: string, timeframe: string) => {
    const seriesId = seriesIdOf(symbol, timeframe);
    await expect(chart).toHaveAttribute("data-series-id", seriesId, { timeout: 10_000 });
    await expect
      .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"), { timeout: 10_000 })
      .toBeGreaterThan(20);
  };

  const screenshot = async (name: string) => {
    await page.screenshot({
      path: `output/playwright/live_browse_${runId}_${name}.png`,
      fullPage: false,
    });
  };

  await expect(chart).toBeVisible();
  await expectChartReady(symbols[0], "1m");
  await screenshot("01_initial_btc_1m");

  await page.getByTestId("timeframe-tag-5m").click();
  await expectChartReady(symbols[0], "5m");
  await screenshot("02_btc_5m");

  await symbolSelect.selectOption(symbols[1]);
  await expect(symbolSelect).toHaveValue(symbols[1]);
  await expectChartReady(symbols[1], "5m");
  await screenshot("03_eth_5m");

  await page.getByTestId("timeframe-tag-1m").click();
  await expectChartReady(symbols[1], "1m");
  await screenshot("04_eth_1m");

  await symbolSelect.selectOption(symbols[2]);
  await expect(symbolSelect).toHaveValue(symbols[2]);
  await expectChartReady(symbols[2], "1m");
  await screenshot("05_sol_1m");

  await page.getByTestId("bottom-tab-Signals").click();
  await expect(page.getByText("Signals (MVP placeholder)")).toBeVisible();
  await screenshot("06_bottom_signals");

  await page.getByTestId("bottom-tab-Backtest").click();
  await expect(page.getByTestId("backtest-panel")).toBeVisible();
  await screenshot("07_bottom_backtest");

  await page.getByTestId("bottom-tab-Ledger").click();
  await expect(page.getByText("Ledger (MVP placeholder)")).toBeVisible();
  await screenshot("08_bottom_ledger");
});
