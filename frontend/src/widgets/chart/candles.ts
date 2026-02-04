import type { UTCTimestamp } from "lightweight-charts";
import type { Candle, CandleClosed } from "./types";

export function toChartCandle(c: CandleClosed): Candle {
  return {
    time: c.candle_time as UTCTimestamp,
    open: c.open,
    high: c.high,
    low: c.low,
    close: c.close
  };
}

export function mergeCandle(list: Candle[], next: Candle): Candle[] {
  const last = list[list.length - 1];
  if (!last) return [next];
  if (next.time === last.time) return [...list.slice(0, -1), next];
  if (next.time > last.time) return [...list, next];
  return list;
}

export function mergeCandleWindow(list: Candle[], next: Candle, limit: number): Candle[] {
  const merged = mergeCandle(list, next);
  if (limit > 0 && merged.length > limit) return merged.slice(-limit);
  return merged;
}

export function mergeCandlesWindow(list: Candle[], next: Candle[], limit: number): Candle[] {
  let out = list;
  for (const c of next) out = mergeCandle(out, c);
  if (limit > 0 && out.length > limit) out = out.slice(-limit);
  return out;
}
