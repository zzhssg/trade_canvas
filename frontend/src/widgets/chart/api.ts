import { apiUrl } from "../../lib/api";
import { toChartCandle } from "./candles";
import type {
  Candle,
  DrawDeltaV1,
  GetCandlesResponse,
  GetFactorSlicesResponseV1,
  OverlayDeltaV1,
  PlotCursorV1,
  PlotDeltaV1,
  WorldDeltaPollResponseV1
} from "./types";
import type { WorldStateV1 } from "./types";

const CANDLES_FETCH_CACHE_MS = 1000;
const candlesFetchCache = new Map<
  string,
  { at: number; promise: Promise<{ candles: Candle[]; headTime: number | null }> }
>();

function pruneFetchCache(nowMs: number) {
  for (const [k, v] of candlesFetchCache.entries()) {
    if (nowMs - v.at > CANDLES_FETCH_CACHE_MS) candlesFetchCache.delete(k);
  }
}

export async function fetchCandles(params: {
  seriesId: string;
  since?: number;
  limit: number;
}): Promise<{ candles: Candle[]; headTime: number | null }> {
  const url = new URL(apiUrl("/api/market/candles"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("limit", String(params.limit));
  if (params.since !== undefined) url.searchParams.set("since", String(params.since));

  const key = url.toString();
  const now = Date.now();
  pruneFetchCache(now);

  const cached = candlesFetchCache.get(key);
  if (cached && now - cached.at <= CANDLES_FETCH_CACHE_MS) return cached.promise;

  const promise = (async () => {
    const res = await fetch(key);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = (await res.json()) as GetCandlesResponse;
    return { candles: payload.candles.map(toChartCandle), headTime: payload.server_head_time };
  })();

  candlesFetchCache.set(key, { at: now, promise });
  promise.catch(() => {
    const cur = candlesFetchCache.get(key);
    if (cur?.promise === promise) candlesFetchCache.delete(key);
  });
  return promise;
}

export async function fetchPlotDelta(params: {
  seriesId: string;
  windowCandles: number;
  cursor?: PlotCursorV1 | null;
}): Promise<PlotDeltaV1> {
  const url = new URL(apiUrl("/api/plot/delta"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("window_candles", String(params.windowCandles));
  if (params.cursor?.candle_time != null) url.searchParams.set("cursor_candle_time", String(params.cursor.candle_time));
  if (params.cursor?.overlay_event_id != null)
    url.searchParams.set("cursor_overlay_event_id", String(params.cursor.overlay_event_id));

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as PlotDeltaV1;
}

export async function fetchOverlayDelta(params: {
  seriesId: string;
  windowCandles: number;
  cursorVersionId?: number;
}): Promise<OverlayDeltaV1> {
  const url = new URL(apiUrl("/api/overlay/delta"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("window_candles", String(params.windowCandles));
  url.searchParams.set("cursor_version_id", String(params.cursorVersionId ?? 0));

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as OverlayDeltaV1;
}

export async function fetchDrawDelta(params: {
  seriesId: string;
  windowCandles: number;
  cursorVersionId?: number;
  atTime?: number;
}): Promise<DrawDeltaV1> {
  const url = new URL(apiUrl("/api/draw/delta"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("window_candles", String(params.windowCandles));
  url.searchParams.set("cursor_version_id", String(params.cursorVersionId ?? 0));
  if (params.atTime !== undefined) url.searchParams.set("at_time", String(params.atTime));

  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as DrawDeltaV1;
}

export async function fetchFactorSlices(params: {
  seriesId: string;
  atTime: number;
  windowCandles: number;
}): Promise<GetFactorSlicesResponseV1> {
  const url = new URL(apiUrl("/api/factor/slices"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("at_time", String(params.atTime));
  url.searchParams.set("window_candles", String(params.windowCandles));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as GetFactorSlicesResponseV1;
}

export async function fetchWorldFrameLive(params: {
  seriesId: string;
  windowCandles: number;
}): Promise<WorldStateV1> {
  const url = new URL(apiUrl("/api/frame/live"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("window_candles", String(params.windowCandles));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as WorldStateV1;
}

export async function fetchWorldFrameAtTime(params: {
  seriesId: string;
  atTime: number;
  windowCandles: number;
}): Promise<WorldStateV1> {
  const url = new URL(apiUrl("/api/frame/at_time"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("at_time", String(params.atTime));
  url.searchParams.set("window_candles", String(params.windowCandles));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as WorldStateV1;
}

export async function pollWorldDelta(params: {
  seriesId: string;
  afterId: number;
  windowCandles: number;
  limit?: number;
}): Promise<WorldDeltaPollResponseV1> {
  const url = new URL(apiUrl("/api/delta/poll"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("after_id", String(params.afterId));
  url.searchParams.set("window_candles", String(params.windowCandles));
  url.searchParams.set("limit", String(params.limit ?? 2000));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as WorldDeltaPollResponseV1;
}
