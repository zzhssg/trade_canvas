import type { UTCTimestamp } from "lightweight-charts";
import type { Candle } from "./types";

export function isSmaKey(key: string): number | null {
  const m = /^sma_(\d+)$/.exec(key);
  if (!m) return null;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n <= 0) return null;
  return n;
}

export function buildSmaLineData(candles: Candle[], period: number): Array<{ time: UTCTimestamp; value: number }> {
  if (period <= 0) return [];
  const out: Array<{ time: UTCTimestamp; value: number }> = [];
  let sum = 0;
  const window: number[] = [];
  for (const c of candles) {
    window.push(c.close);
    sum += c.close;
    if (window.length > period) sum -= window.shift()!;
    if (window.length === period) out.push({ time: c.time, value: sum / period });
  }
  return out;
}

export function computeSmaAtIndex(candles: Candle[], idx: number, period: number): number | null {
  if (period <= 0) return null;
  if (idx < period - 1) return null;
  if (idx >= candles.length) return null;
  let sum = 0;
  for (let i = idx; i > idx - period; i--) sum += candles[i]!.close;
  return sum / period;
}

