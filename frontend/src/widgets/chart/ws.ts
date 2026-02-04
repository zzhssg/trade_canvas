import type { CandleClosed } from "./types";

type MarketWsGap = {
  type: "gap";
  series_id?: string;
  expected_next_time?: number;
  actual_time?: number;
};

type MarketWsError = {
  type: "error";
  code?: string;
  message?: string;
};

export type MarketWsMessage =
  | { type: "candle_forming"; candle: CandleClosed }
  | { type: "candle_closed"; candle: CandleClosed }
  | { type: "candles_batch"; candles: CandleClosed[] }
  | MarketWsGap
  | MarketWsError;

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

function isCandleClosed(value: unknown): value is CandleClosed {
  if (!isRecord(value)) return false;
  return (
    isFiniteNumber(value.candle_time) &&
    isFiniteNumber(value.open) &&
    isFiniteNumber(value.high) &&
    isFiniteNumber(value.low) &&
    isFiniteNumber(value.close) &&
    isFiniteNumber(value.volume)
  );
}

export function parseMarketWsMessage(payload: string): MarketWsMessage | null {
  let raw: unknown;
  try {
    raw = JSON.parse(payload) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(raw)) return null;
  const type = raw.type;
  if (typeof type !== "string") return null;

  if ((type === "candle_forming" || type === "candle_closed") && isCandleClosed(raw.candle)) {
    return { type, candle: raw.candle };
  }

  if (type === "candles_batch") {
    const candlesRaw = raw.candles;
    if (!Array.isArray(candlesRaw)) return null;
    const candles: CandleClosed[] = [];
    for (const c of candlesRaw) {
      if (!isCandleClosed(c)) return null;
      candles.push(c);
    }
    return { type: "candles_batch", candles };
  }

  if (type === "gap") {
    return {
      type: "gap",
      series_id: typeof raw.series_id === "string" ? raw.series_id : undefined,
      expected_next_time: isFiniteNumber(raw.expected_next_time) ? raw.expected_next_time : undefined,
      actual_time: isFiniteNumber(raw.actual_time) ? raw.actual_time : undefined
    };
  }

  if (type === "error") {
    return {
      type: "error",
      code: typeof raw.code === "string" ? raw.code : undefined,
      message: typeof raw.message === "string" ? raw.message : undefined
    };
  }

  return null;
}
