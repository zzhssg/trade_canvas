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

