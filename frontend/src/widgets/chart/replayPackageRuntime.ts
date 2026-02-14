import {
  fetchReplayBuild,
  fetchReplayCoverageStatus,
  fetchReplayEnsureCoverage,
  fetchReplayStatus
} from "./api";
import type { ReplayStatus } from "../../state/replayStore";
import type {
  ReplayCoverageStatusResponseV1,
  ReplayCoverageV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayHistoryEventV1,
  ReplayPackageMetadataV1,
  ReplayWindowResponseV1
} from "./types";

const POLL_INTERVAL_MS = 300;

const sleep = (ms: number) => new Promise((resolve) => window.setTimeout(resolve, ms));
const hasFlag = (value: string, flag: string) => value.includes(flag);

function extractHttpDetail(err: unknown): string {
  if (!(err instanceof Error)) return "unknown_error";
  const message = String(err.message || "").trim();
  const parts = message.split(":");
  return (parts.length > 1 ? parts.slice(1).join(":") : message).trim() || "unknown_error";
}

function sortHistoryEvents(events: ReplayHistoryEventV1[]): ReplayHistoryEventV1[] {
  return events.slice().sort((a, b) => a.event_id - b.event_id);
}

export type ReplayWindowBundleRuntime = {
  window: ReplayWindowResponseV1["window"];
  headSnapshots: ReplayFactorHeadSnapshotV1[];
  historyDeltas: ReplayHistoryDeltaV1[];
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

export function buildWindowBundle(resp: ReplayWindowResponseV1): ReplayWindowBundleRuntime {
  const headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>> = {};
  const historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1> = {};

  for (const snap of resp.factor_head_snapshots ?? []) {
    const t = Number(snap.candle_time);
    if (!Number.isFinite(t)) continue;
    const byFactor = (headByTime[t] ??= {});
    const cur = byFactor[snap.factor_name];
    if (!cur || (snap.seq ?? 0) >= (cur.seq ?? 0)) byFactor[snap.factor_name] = snap as ReplayFactorHeadSnapshotV1;
  }
  for (const delta of resp.history_deltas ?? []) historyDeltaByIdx[delta.idx] = delta;

  return {
    window: resp.window,
    headSnapshots: resp.factor_head_snapshots ?? [],
    historyDeltas: resp.history_deltas ?? [],
    headByTime,
    historyDeltaByIdx
  };
}

type ReplayBuildContext = {
  seriesId: string;
  windowCandles: number;
  windowSize: number;
  snapshotInterval: number;
  isCancelled: () => boolean;
  fail: (detail: string, nextStatus?: "error" | "out_of_sync") => void;
  setStatus: (status: ReplayStatus) => void;
  setError: (error: string | null) => void;
  setCoverage: (coverage: ReplayCoverageV1 | null) => void;
  setCoverageStatus: (status: ReplayCoverageStatusResponseV1 | null) => void;
  setMetadata: (metadata: ReplayPackageMetadataV1 | null) => void;
  setHistoryEvents: (events: ReplayHistoryEventV1[]) => void;
  setJobInfo: (jobId: string | null, cacheKey: string | null) => void;
};

async function pollReplayBuildStatus(ctx: ReplayBuildContext, targetJobId: string): Promise<void> {
  while (!ctx.isCancelled()) {
    let payload;
    try {
      payload = await fetchReplayStatus({ jobId: targetJobId, includePreload: true, includeHistory: true });
    } catch (err) {
      ctx.fail(extractHttpDetail(err));
      return;
    }
    if (payload.status === "done") {
      ctx.setMetadata(payload.metadata ?? null);
      ctx.setHistoryEvents(sortHistoryEvents(payload.history_events ?? []));
      ctx.setStatus("ready");
      ctx.setError(null);
      return;
    }
    if (payload.status === "error") {
      ctx.fail(payload.error ?? "build_failed");
      return;
    }
    await sleep(POLL_INTERVAL_MS);
  }
}

async function ensureReplayCoverage(
  ctx: ReplayBuildContext,
  toTime?: number
): Promise<Awaited<ReturnType<typeof fetchReplayCoverageStatus>> | null> {
  try {
    const ensure = await fetchReplayEnsureCoverage({
      series_id: ctx.seriesId,
      target_candles: ctx.windowCandles,
      to_time: toTime
    });
    ctx.setCoverageStatus({
      status: "building",
      job_id: ensure.job_id,
      candles_ready: 0,
      required_candles: ctx.windowCandles
    });
    while (!ctx.isCancelled()) {
      const current = await fetchReplayCoverageStatus({ jobId: ensure.job_id });
      ctx.setCoverageStatus(current);
      if (current.status === "done" || current.status === "error") return current;
      await sleep(POLL_INTERVAL_MS);
    }
  } catch (err) {
    ctx.fail(extractHttpDetail(err));
  }
  return null;
}

export async function runReplayBuildFlow(ctx: ReplayBuildContext): Promise<void> {
  const buildPayload = {
    series_id: ctx.seriesId,
    window_candles: ctx.windowCandles,
    window_size: ctx.windowSize,
    snapshot_interval: ctx.snapshotInterval
  };
  const buildNow = async () => {
    ctx.setStatus("building");
    return fetchReplayBuild(buildPayload);
  };

  let build: Awaited<ReturnType<typeof fetchReplayBuild>> | null = null;
  try {
    build = await buildNow();
  } catch (err) {
    const detail = extractHttpDetail(err);
    if (hasFlag(detail, "ledger_out_of_sync")) {
      ctx.fail(detail, "out_of_sync");
      return;
    }
    if (!hasFlag(detail, "coverage_missing")) {
      ctx.fail(detail);
      return;
    }
    ctx.setStatus("coverage");
    const coverage = await ensureReplayCoverage(ctx);
    if (ctx.isCancelled()) return;
    if (!coverage || coverage.status === "error") {
      ctx.fail(coverage?.error ?? "coverage_failed");
      return;
    }
    ctx.setCoverage({
      required_candles: coverage.required_candles,
      candles_ready: coverage.candles_ready,
      from_time: null,
      to_time: coverage.head_time ?? null
    });
    try {
      build = await buildNow();
    } catch (retryErr) {
      const retryDetail = extractHttpDetail(retryErr);
      ctx.fail(retryDetail, hasFlag(retryDetail, "ledger_out_of_sync") ? "out_of_sync" : "error");
      return;
    }
  }

  if (!build || ctx.isCancelled()) return;
  ctx.setJobInfo(build.job_id, build.cache_key);
  await pollReplayBuildStatus(ctx, build.job_id);
}
