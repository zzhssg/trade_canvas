import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

import {
  ingestClosedCandlePrice,
  ingestClosedCandlesWithFallback,
  type CandleSeed,
} from "./helpers/marketIngest";
import {
  buildDefaultUiState,
  buildFactorsState,
  initTradeCanvasStorage,
} from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ??
  process.env.VITE_API_BASE ??
  process.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
const RECENT_WINDOW_CANDLES = 2000;
const WAVE_SEGMENT = 500;
const WAVE_TOTAL = WAVE_SEGMENT * 4;
const LIVE_INCREMENTAL_CANDLES = 6;

type TimeframeSeed = {
  timeframe: string;
  seriesId: string;
  latestTime: number;
  latestClose: number;
};

type FrameLiveResponse = {
  series_id: string;
  time: {
    aligned_time: number;
    candle_id: string;
  };
  factor_slices: {
    candle_id: string | null;
  };
  draw_state: {
    to_candle_time: number | null;
  };
};

type FactorSlicesResponse = {
  candle_id: string | null;
  factors: string[];
};

type CandlesResponse = {
  series_id: string;
  candles: Array<{
    candle_time: number;
    close: number;
  }>;
};

function btcSeriesId(timeframe: string): string {
  return `binance:futures:BTC/USDT:${timeframe}`;
}

function timeframeToSeconds(timeframe: string): number {
  switch (timeframe) {
    case "1m":
      return 60;
    case "5m":
      return 300;
    case "15m":
      return 900;
    case "1h":
      return 3600;
    case "4h":
      return 14400;
    case "1d":
      return 86400;
    default:
      throw new Error(`unsupported timeframe: ${timeframe}`);
  }
}

function wavePrice(index: number): number {
  const i = index % WAVE_TOTAL;
  if (i < WAVE_SEGMENT) return i + 1;
  if (i < WAVE_SEGMENT * 2) return WAVE_SEGMENT - (i - WAVE_SEGMENT);
  if (i < WAVE_SEGMENT * 3) return i - WAVE_SEGMENT * 2 + 1;
  return WAVE_SEGMENT - (i - WAVE_SEGMENT * 3);
}

function timeoutLeft(deadlineMs: number): number {
  return Math.max(1, deadlineMs - Date.now());
}

async function seedTimeframe(request: APIRequestContext, timeframe: string): Promise<TimeframeSeed> {
  const seriesId = btcSeriesId(timeframe);
  const tfSeconds = timeframeToSeconds(timeframe);
  const alignedStart = Math.floor(1_900_000_000 / tfSeconds) * tfSeconds;
  const candles: CandleSeed[] = [];
  for (let i = 0; i < WAVE_TOTAL; i++) {
    const candleTime = alignedStart + tfSeconds * (i + 1);
    const price = wavePrice(i);
    candles.push({
      candle_time: candleTime,
      open: price,
      high: price,
      low: price,
      close: price,
      volume: 10
    });
  }

  const warmupCount = Math.max(0, WAVE_TOTAL - LIVE_INCREMENTAL_CANDLES);
  const warmupCandles = candles.slice(0, warmupCount);
  if (warmupCandles.length > 0) {
    await ingestClosedCandlesWithFallback(request, {
      apiBase,
      seriesId,
      candles: warmupCandles,
      publishWs: false,
      timeoutMs: 120_000,
    });
  }

  let latestTime = 0;
  let latestClose = 0;
  for (const candle of candles.slice(warmupCount)) {
    const candleTime = candle.candle_time;
    const price = candle.close;
    await ingestClosedCandlePrice(request, {
      apiBase,
      seriesId,
      candleTime,
      price,
      timeoutMs: 120_000,
    });
    latestTime = candleTime;
    latestClose = price;
  }
  return {
    timeframe,
    seriesId,
    latestTime,
    latestClose
  };
}

async function verifyRecent2000FactorWindow(request: APIRequestContext, seed: TimeframeSeed): Promise<void> {
  const tfSeconds = timeframeToSeconds(seed.timeframe);
  const expectedStartTime = seed.latestTime - tfSeconds * (RECENT_WINDOW_CANDLES - 1);
  const candlesRes = await request.get(`${apiBase}/api/market/candles`, {
    params: {
      series_id: seed.seriesId,
      limit: RECENT_WINDOW_CANDLES
    }
  });
  expect(candlesRes.ok()).toBeTruthy();
  const candlesPayload = (await candlesRes.json()) as CandlesResponse;
  expect(candlesPayload.series_id).toBe(seed.seriesId);
  expect(candlesPayload.candles.length).toBe(RECENT_WINDOW_CANDLES);
  expect(candlesPayload.candles[0]?.candle_time).toBe(expectedStartTime);
  expect(candlesPayload.candles[candlesPayload.candles.length - 1]?.candle_time).toBe(seed.latestTime);

  const probeTimes = [expectedStartTime, expectedStartTime + tfSeconds * 1000, seed.latestTime];
  for (const atTime of probeTimes) {
    const factorRes = await request.get(`${apiBase}/api/factor/slices`, {
      params: {
        series_id: seed.seriesId,
        at_time: atTime,
        window_candles: RECENT_WINDOW_CANDLES
      }
    });
    expect(factorRes.ok()).toBeTruthy();
    const factorPayload = (await factorRes.json()) as FactorSlicesResponse;
    expect(factorPayload.candle_id).toBe(`${seed.seriesId}:${atTime}`);
    expect(Array.isArray(factorPayload.factors)).toBeTruthy();
  }
}

async function assertTimeframeReady(
  page: Page,
  args: {
    seed: TimeframeSeed;
    deadlineMs: number;
    isInitial: boolean;
  }
): Promise<void> {
  const { seed, deadlineMs, isInitial } = args;
  const tfTag = page.getByTestId(`timeframe-tag-${seed.timeframe}`);
  if (!isInitial) {
    const sidQuery = `series_id=${encodeURIComponent(seed.seriesId)}`;
    const candlesPromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/market/candles") &&
        r.url().includes(sidQuery) &&
        r.request().method() === "GET" &&
        r.status() === 200,
      { timeout: timeoutLeft(deadlineMs) }
    );
    const framePromise = page.waitForResponse(
      (r) =>
        r.url().includes("/api/frame/live") &&
        r.url().includes(sidQuery) &&
        r.request().method() === "GET" &&
        r.status() === 200,
      { timeout: timeoutLeft(deadlineMs) }
    );
    await expect(tfTag).toBeVisible({ timeout: timeoutLeft(deadlineMs) });
    await tfTag.click();

    const candlesPayload = (await (await candlesPromise).json()) as CandlesResponse;
    expect(candlesPayload.series_id).toBe(seed.seriesId);
    expect(candlesPayload.candles.length).toBe(RECENT_WINDOW_CANDLES);
    expect(candlesPayload.candles[candlesPayload.candles.length - 1]?.candle_time).toBe(seed.latestTime);
    expect(candlesPayload.candles[candlesPayload.candles.length - 1]?.close).toBe(seed.latestClose);

    const framePayload = (await (await framePromise).json()) as FrameLiveResponse;
    expect(framePayload.series_id).toBe(seed.seriesId);
    expect(framePayload.time.aligned_time).toBe(seed.latestTime);
    expect(framePayload.time.candle_id).toBe(`${seed.seriesId}:${seed.latestTime}`);
    expect(framePayload.factor_slices.candle_id).toBe(`${seed.seriesId}:${seed.latestTime}`);
    expect(framePayload.draw_state.to_candle_time).toBe(seed.latestTime);
  }

  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-series-id", seed.seriesId, { timeout: timeoutLeft(deadlineMs) });
  await expect(chart).toHaveAttribute("data-last-time", String(seed.latestTime), { timeout: timeoutLeft(deadlineMs) });
  await expect(chart).toHaveAttribute("data-last-close", String(seed.latestClose), { timeout: timeoutLeft(deadlineMs) });
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-pivot-count")) ?? "0"),
      { timeout: timeoutLeft(deadlineMs) }
    )
    .toBeGreaterThan(0);
  await expect
    .poll(
      async () => Number((await chart.getAttribute("data-pen-point-count")) ?? "0"),
      { timeout: timeoutLeft(deadlineMs) }
    )
    .toBeGreaterThan(0);
}

test("btc all timeframes reach latest candles and factor drawings within 10s after open @mainflow", async ({
  page,
  request
}) => {
  test.setTimeout(480_000);

  const seeds: TimeframeSeed[] = [];
  for (let i = 0; i < TIMEFRAMES.length; i += 2) {
    const chunk = TIMEFRAMES.slice(i, i + 2);
    const chunkSeeds = await Promise.all(chunk.map((timeframe) => seedTimeframe(request, timeframe)));
    seeds.push(...chunkSeeds);
  }
  for (const seed of seeds) {
    await verifyRecent2000FactorWindow(request, seed);
  }

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol: "BTC/USDT", timeframe: "1m" }),
    factorsVersion: 4,
    factorsState: buildFactorsState({
      pivot: true,
      "pivot.major": true,
      pen: true,
      "pen.confirmed": true,
      anchor: true,
      "anchor.switch": true,
    }),
  });

  const openAt = Date.now();
  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });
  const deadlineMs = openAt + 10_000;
  await expect(page.locator('[data-chart-area="true"]')).toBeVisible({ timeout: timeoutLeft(deadlineMs) });

  for (let i = 0; i < seeds.length; i++) {
    await assertTimeframeReady(page, {
      seed: seeds[i]!,
      deadlineMs,
      isInitial: i === 0
    });
  }

  expect(Date.now()).toBeLessThanOrEqual(deadlineMs);

  const fourHourSeed = seeds.find((seed) => seed.timeframe === "4h");
  expect(fourHourSeed).toBeTruthy();
  if (!fourHourSeed) return;

  const chart = page.locator('[data-testid="chart-view"]');
  const fourHourTag = page.getByTestId("timeframe-tag-4h");
  await fourHourTag.click();
  await expect(chart).toHaveAttribute("data-series-id", fourHourSeed.seriesId);

  const fourHourNextTime = fourHourSeed.latestTime + timeframeToSeconds("4h");
  const fourHourNextClose = fourHourSeed.latestClose + 1;
  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId: fourHourSeed.seriesId,
    candleTime: fourHourNextTime,
    price: fourHourNextClose,
    timeoutMs: 120_000,
  });
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(fourHourNextTime));
  await expect(chart).toHaveAttribute("data-last-time", String(fourHourNextTime));
  await expect(chart).toHaveAttribute("data-last-close", String(fourHourNextClose));
});
