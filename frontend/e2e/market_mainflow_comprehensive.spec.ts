import { expect, test, type APIRequestContext } from "@playwright/test";

import {
  ingestClosedCandlePrice,
  uniqueSymbol,
} from "./helpers/marketIngest";
import { buildDefaultUiState, initTradeCanvasStorage } from "./helpers/localStorage";

const frontendBase = process.env.E2E_BASE_URL ?? "http://127.0.0.1:5173";
const apiBase =
  process.env.E2E_API_BASE_URL ??
  process.env.VITE_API_BASE ??
  process.env.VITE_API_BASE_URL ??
  "http://127.0.0.1:8000";

type CandleApiRow = {
  candle_time: number;
  close: number;
};

type CandlesApiResponse = {
  series_id: string;
  candles: CandleApiRow[];
};

type FactorSlicesApiResponse = {
  candle_id: string | null;
};

type WorldFrameApiResponse = {
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

async function getFactorSlices(
  request: APIRequestContext,
  args: {
    seriesId: string;
    atTime: number;
  }
): Promise<FactorSlicesApiResponse> {
  const { seriesId, atTime } = args;
  const res = await request.get(`${apiBase}/api/factor/slices`, {
    params: {
      series_id: seriesId,
      at_time: atTime,
      window_candles: 2000
    }
  });
  expect(res.ok()).toBeTruthy();
  return (await res.json()) as FactorSlicesApiResponse;
}

test("mainflow comprehensive: ingest -> frame -> ws -> factor stays consistent @mainflow", async ({ page, request }) => {
  const symbol = uniqueSymbol("TCMAIN");
  const seriesId = `binance:futures:${symbol}:1m`;
  const seedTimes = [1700000000, 1700000060, 1700000120];
  const followupTime = 1700000180;
  const followupClose = 44;

  await initTradeCanvasStorage(page, {
    clear: true,
    uiVersion: 2,
    uiState: buildDefaultUiState({ symbol, timeframe: "1m" }),
  });

  for (const [index, candleTime] of seedTimes.entries()) {
    await ingestClosedCandlePrice(request, {
      apiBase,
      seriesId,
      candleTime,
      price: index + 1,
    });
  }

  const wsReceivedFrames: string[] = [];
  page.on("websocket", (ws) => {
    if (!ws.url().includes("/ws/market")) return;
    ws.on("framereceived", (event) => {
      wsReceivedFrames.push(event.payload);
    });
  });

  const sidQuery = `series_id=${encodeURIComponent(seriesId)}`;
  const frameResponsePromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/frame/live") &&
      r.url().includes(sidQuery) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });
  const candlesResponsePromise = page.waitForResponse((r) => {
    return (
      r.url().includes("/api/market/candles") &&
      r.url().includes(sidQuery) &&
      r.request().method() === "GET" &&
      r.status() === 200
    );
  });

  await page.goto(`${frontendBase}/live`, { waitUntil: "domcontentloaded" });

  const frameResponseRaw = await frameResponsePromise;
  const frameResponse = (await frameResponseRaw.json()) as WorldFrameApiResponse;
  expect(frameResponse.series_id).toBe(seriesId);
  expect(frameResponse.time.aligned_time).toBe(seedTimes[seedTimes.length - 1]);
  expect(frameResponse.time.candle_id).toBe(`${seriesId}:${seedTimes[seedTimes.length - 1]}`);

  const candlesResponseRaw = await candlesResponsePromise;
  const candlesResponse = (await candlesResponseRaw.json()) as CandlesApiResponse;
  expect(candlesResponse.series_id).toBe(seriesId);
  const candleTimes = candlesResponse.candles.map((candle) => Number(candle.candle_time));
  expect(candleTimes.length).toBeGreaterThanOrEqual(2);
  expect(Math.max(...candleTimes)).toBe(seedTimes[seedTimes.length - 1]);

  const chart = page.locator('[data-testid="chart-view"]');
  await expect(chart).toHaveAttribute("data-series-id", seriesId);
  await expect(chart).toHaveAttribute("data-last-time", String(seedTimes[seedTimes.length - 1]));

  await ingestClosedCandlePrice(request, {
    apiBase,
    seriesId,
    candleTime: followupTime,
    price: followupClose,
  });

  await expect(chart).toHaveAttribute("data-last-time", String(followupTime));
  await expect(chart).toHaveAttribute("data-last-close", String(followupClose));
  await expect(chart).toHaveAttribute("data-last-ws-candle-time", String(followupTime));

  await expect
    .poll(() =>
      wsReceivedFrames.some((payload) => {
        return (
          payload.includes('"type":"candle_closed"') &&
          payload.includes(`"series_id":"${seriesId}"`) &&
          payload.includes(`"candle_time":${followupTime}`)
        );
      })
    )
    .toBeTruthy();

  const factorFirstRead = await getFactorSlices(request, {
    seriesId,
    atTime: followupTime
  });
  expect(factorFirstRead.candle_id).toBe(`${seriesId}:${followupTime}`);

  const factorSecondRead = await getFactorSlices(request, {
    seriesId,
    atTime: followupTime
  });
  expect(factorSecondRead).toEqual(factorFirstRead);

  const worldAtTimeResponse = await request.get(`${apiBase}/api/frame/at_time`, {
    params: {
      series_id: seriesId,
      at_time: followupTime,
      window_candles: 2000
    }
  });
  expect(worldAtTimeResponse.ok()).toBeTruthy();
  const worldAtTime = (await worldAtTimeResponse.json()) as WorldFrameApiResponse;
  expect(worldAtTime.time.candle_id).toBe(`${seriesId}:${followupTime}`);
  expect(worldAtTime.factor_slices.candle_id).toBe(`${seriesId}:${followupTime}`);
  expect(worldAtTime.draw_state.to_candle_time).toBe(followupTime);
});
