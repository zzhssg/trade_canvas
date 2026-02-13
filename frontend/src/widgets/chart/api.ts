import { apiUrl } from "../../lib/api";
import { toChartCandle } from "./candles";
import type {
  Candle,
  DrawDeltaV1,
  GetCandlesResponse,
  GetFactorSlicesResponseV1,
  ReplayPrepareResponseV1,
  ReplayBuildRequestV1,
  ReplayBuildResponseV1,
  ReplayCoverageStatusResponseV1,
  ReplayEnsureCoverageRequestV1,
  ReplayEnsureCoverageResponseV1,
  ReplayStatusResponseV1,
  ReplayWindowResponseV1,
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

async function throwHttpError(res: Response): Promise<never> {
  let detail = "";
  try {
    const payload = (await res.json()) as { detail?: unknown };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      detail = payload.detail.trim();
    }
  } catch {
    detail = "";
  }
  throw new Error(detail ? `HTTP ${res.status}:${detail}` : `HTTP ${res.status}`);
}

export async function fetchCandles(params: {
  seriesId: string;
  since?: number;
  limit: number;
  bypassCache?: boolean;
}): Promise<{ candles: Candle[]; headTime: number | null }> {
  const url = new URL(apiUrl("/api/market/candles"), window.location.origin);
  url.searchParams.set("series_id", params.seriesId);
  url.searchParams.set("limit", String(params.limit));
  if (params.since !== undefined) url.searchParams.set("since", String(params.since));

  const key = url.toString();
  const now = Date.now();
  pruneFetchCache(now);

  if (!params.bypassCache) {
    const cached = candlesFetchCache.get(key);
    if (cached && now - cached.at <= CANDLES_FETCH_CACHE_MS) return cached.promise;
  }

  const promise = (async () => {
    const res = await fetch(key);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const payload = (await res.json()) as GetCandlesResponse;
    return { candles: payload.candles.map(toChartCandle), headTime: payload.server_head_time };
  })();

  if (!params.bypassCache) {
    candlesFetchCache.set(key, { at: now, promise });
    promise.catch(() => {
      const cur = candlesFetchCache.get(key);
      if (cur?.promise === promise) candlesFetchCache.delete(key);
    });
  }
  return promise;
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

export async function prepareReplay(params: {
  seriesId: string;
  toTime?: number;
  windowCandles?: number;
}): Promise<ReplayPrepareResponseV1> {
  const res = await fetch(apiUrl("/api/replay/prepare"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      series_id: params.seriesId,
      to_time: params.toTime ?? null,
      window_candles: params.windowCandles ?? null
    })
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ReplayPrepareResponseV1;
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

export async function fetchReplayEnsureCoverage(
  payload: ReplayEnsureCoverageRequestV1
): Promise<ReplayEnsureCoverageResponseV1> {
  const url = apiUrl("/api/replay/ensure_coverage");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ReplayEnsureCoverageResponseV1;
}

export async function fetchReplayCoverageStatus(params: { jobId: string }): Promise<ReplayCoverageStatusResponseV1> {
  const url = new URL(apiUrl("/api/replay/coverage_status"), window.location.origin);
  url.searchParams.set("job_id", params.jobId);
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ReplayCoverageStatusResponseV1;
}

export async function fetchReplayBuild(payload: ReplayBuildRequestV1): Promise<ReplayBuildResponseV1> {
  const url = apiUrl("/api/replay/build");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!res.ok) await throwHttpError(res);
  return (await res.json()) as ReplayBuildResponseV1;
}

export async function fetchReplayStatus(params: {
  jobId: string;
  includePreload?: boolean;
  includeHistory?: boolean;
}): Promise<ReplayStatusResponseV1> {
  const url = new URL(apiUrl("/api/replay/status"), window.location.origin);
  url.searchParams.set("job_id", params.jobId);
  if (params.includePreload) url.searchParams.set("include_preload", "1");
  if (params.includeHistory) url.searchParams.set("include_history", "1");
  const res = await fetch(url.toString());
  if (!res.ok) await throwHttpError(res);
  return (await res.json()) as ReplayStatusResponseV1;
}

export async function fetchReplayWindow(params: { jobId: string; targetIdx: number }): Promise<ReplayWindowResponseV1> {
  const url = new URL(apiUrl("/api/replay/window"), window.location.origin);
  url.searchParams.set("job_id", params.jobId);
  url.searchParams.set("target_idx", String(params.targetIdx));
  const res = await fetch(url.toString());
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ReplayWindowResponseV1;
}
