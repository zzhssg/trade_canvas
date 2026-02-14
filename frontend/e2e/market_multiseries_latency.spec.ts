import { expect, test, type APIRequestContext } from "@playwright/test";

import type { GetCandlesResponse } from "../src/widgets/chart/types";
import {
  ingestClosedCandlePrice,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ?? process.env.VITE_API_BASE ?? process.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

const TIMEFRAMES = [
  { label: "1m", step: 60 },
  { label: "5m", step: 300 },
  { label: "15m", step: 900 },
  { label: "1h", step: 3600 },
  { label: "4h", step: 14400 },
  { label: "1d", step: 86400 },
] as const;

type WorldFrameAtTimeApiResponse = {
  time: {
    candle_id: string;
  };
  factor_slices: {
    candle_id: string | null;
  };
  draw_state: {
    to_candle_time: number | null;
  };
};

function seriesIdOf(symbol: string, timeframe: string): string {
  return `binance:futures:${symbol}:${timeframe}`;
}

function buildWave(step: number): CandleSeed[] {
  const segment = 60;
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
    last_price: 100 + idx,
    quote_volume: 1_000_000 - idx * 1_000,
    price_change_percent: 0.5 + idx,
  }));
}

async function waitSeriesCandlesReady(
  request: APIRequestContext,
  seriesId: string,
  minimumCount: number,
  timeoutMs = 15_000
) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const res = await request.get(`${apiBase}/api/market/candles`, {
      params: { series_id: seriesId, limit: 2000 },
    });
    expect(res.ok()).toBeTruthy();
    const payload = (await res.json()) as GetCandlesResponse;
    if ((payload.candles?.length ?? 0) >= minimumCount) return;
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`series candles not ready: ${seriesId}`);
}

test("btc eth sol all timeframes refresh latest kline/factor/draw within 3s after close", async ({ page, request }) => {
  test.setTimeout(180_000);
  const runId = Date.now().toString(36).toUpperCase();
  const symbols = [`BTCTC${runId}/USDT`, `ETHTC${runId}/USDT`, `SOLTC${runId}/USDT`];

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: symbols[0], timeframe: "1m" }),
  });

  const latestTimeBySeries = new Map<string, number>();
  for (const symbol of symbols) {
    for (const timeframe of TIMEFRAMES) {
      const seriesId = seriesIdOf(symbol, timeframe.label);
      const wave = buildWave(timeframe.step);
      await ingestClosedCandlesWithFallback(request, {
        apiBase,
        seriesId,
        candles: wave,
      });
      latestTimeBySeries.set(seriesId, wave[wave.length - 1]!.candle_time);
      await waitSeriesCandlesReady(request, seriesId, 2);
    }
  }

  await page.route("**/api/market/top_markets/stream*", async (route) => {
    await route.abort();
  });

  await page.route("**/api/market/top_markets*", async (route) => {
    const url = new URL(route.request().url());
    const market = url.searchParams.get("market") ?? "futures";
    const limit = Number(url.searchParams.get("limit") ?? "20");
    const items = buildTopMarketItems(symbols).slice(0, Math.max(1, limit));
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
        items,
      }),
    });
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const chart = page.locator('[data-testid="chart-view"]');
  const symbolSelect = page.getByTestId("symbol-select");
  await expect(chart).toBeVisible();

  for (const symbol of symbols) {
    await expect
      .poll(
        async () =>
          symbolSelect.locator("option").evaluateAll(
            (nodes, target) => nodes.some((node) => (node as HTMLOptionElement).value === target),
            symbol
          ),
        { timeout: 10_000 }
      )
      .toBeTruthy();
    await symbolSelect.selectOption(symbol);
    await expect(symbolSelect).toHaveValue(symbol);

    for (const timeframe of TIMEFRAMES) {
      const seriesId = seriesIdOf(symbol, timeframe.label);
      const timeframeButton = page.getByTestId(`timeframe-tag-${timeframe.label}`);
      await timeframeButton.click();
      await expect(chart).toHaveAttribute("data-series-id", seriesId, { timeout: 3_000 });
      await expect
        .poll(async () => Number((await chart.getAttribute("data-candles-len")) ?? "0"), { timeout: 3_000 })
        .toBeGreaterThan(10);

      const previousTime = latestTimeBySeries.get(seriesId);
      expect(previousTime).toBeDefined();
      const nextTime = (previousTime as number) + timeframe.step;
      await ingestClosedCandlePrice(request, {
        apiBase,
        seriesId,
        candleTime: nextTime,
        price: 100,
      });
      latestTimeBySeries.set(seriesId, nextTime);

      await expect(chart).toHaveAttribute("data-last-time", String(nextTime), { timeout: 3_000 });
      await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(nextTime), { timeout: 3_000 });
      await expect
        .poll(
          async () => {
            const res = await request.get(`${apiBase}/api/frame/at_time`, {
              params: {
                series_id: seriesId,
                at_time: nextTime,
                window_candles: 2000,
              },
            });
            if (!res.ok()) return "not_ready";
            const payload = (await res.json()) as WorldFrameAtTimeApiResponse;
            return `${payload.time.candle_id}|${payload.factor_slices.candle_id}|${payload.draw_state.to_candle_time}`;
          },
          { timeout: 3_000 }
        )
        .toBe(`${seriesId}:${nextTime}|${seriesId}:${nextTime}|${nextTime}`);
    }
  }
});
