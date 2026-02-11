import { expect, type APIRequestContext } from "@playwright/test";

export type CandleSeed = {
  candle_time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

type BatchIngestResponse = {
  ok: boolean;
  series_id: string;
  count: number;
  first_candle_time: number | null;
  last_candle_time: number | null;
};

type IngestBaseArgs = {
  apiBase: string;
  seriesId: string;
  timeoutMs?: number;
};

export function uniqueSymbol(prefix: string): string {
  const ts = Date.now().toString(36).toUpperCase();
  const rand = Math.floor(Math.random() * 1_000_000)
    .toString(36)
    .toUpperCase();
  return `${prefix}${ts}${rand}/USDT`;
}

export function buildSeriesId(symbol: string, timeframe: string): string {
  return `binance:futures:${symbol}:${timeframe}`;
}

export function flatCandle(candleTime: number, price: number, volume = 10): CandleSeed {
  return {
    candle_time: candleTime,
    open: price,
    high: price,
    low: price,
    close: price,
    volume,
  };
}

export async function ingestClosedCandle(
  request: APIRequestContext,
  args: IngestBaseArgs & {
    candle: CandleSeed;
  }
): Promise<void> {
  const { apiBase, seriesId, candle, timeoutMs } = args;
  const res = await request.post(`${apiBase}/api/market/ingest/candle_closed`, {
    timeout: timeoutMs,
    data: {
      series_id: seriesId,
      candle,
    },
  });
  expect(res.ok()).toBeTruthy();
}

export async function ingestClosedCandlePrice(
  request: APIRequestContext,
  args: IngestBaseArgs & {
    candleTime: number;
    price: number;
    volume?: number;
  }
): Promise<void> {
  const { candleTime, price, volume = 10, ...rest } = args;
  await ingestClosedCandle(request, {
    ...rest,
    candle: flatCandle(candleTime, price, volume),
  });
}

export async function ingestClosedCandlesBatch(
  request: APIRequestContext,
  args: IngestBaseArgs & {
    candles: CandleSeed[];
    publishWs?: boolean;
  }
): Promise<boolean> {
  const { apiBase, seriesId, candles, publishWs = false, timeoutMs } = args;
  if (candles.length === 0) return true;
  const res = await request.post(`${apiBase}/api/dev/market/ingest/candles_closed_batch`, {
    timeout: timeoutMs,
    data: {
      series_id: seriesId,
      candles,
      publish_ws: publishWs,
    },
  });
  if (!res.ok()) {
    return false;
  }
  const payload = (await res.json()) as BatchIngestResponse;
  expect(payload.ok).toBeTruthy();
  expect(payload.series_id).toBe(seriesId);
  expect(payload.count).toBe(candles.length);
  return true;
}

export async function ingestClosedCandlesWithFallback(
  request: APIRequestContext,
  args: IngestBaseArgs & {
    candles: CandleSeed[];
    publishWs?: boolean;
  }
): Promise<void> {
  const { candles, ...rest } = args;
  const batched = await ingestClosedCandlesBatch(request, {
    ...rest,
    candles,
  });
  if (batched) return;
  for (const candle of candles) {
    await ingestClosedCandle(request, {
      ...rest,
      candle,
    });
  }
}
