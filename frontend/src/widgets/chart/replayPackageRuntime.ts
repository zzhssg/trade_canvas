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
  ReplayFactorSnapshotV1,
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

export type ReplayWindowBundleRuntime = {
  window: ReplayWindowResponseV1["window"];
  factorSnapshots: ReplayFactorSnapshotV1[];
  factorSnapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>;
};

export function buildWindowBundle(resp: ReplayWindowResponseV1): ReplayWindowBundleRuntime {
  const factorSnapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>> = {};

  for (const row of resp.factor_snapshots ?? []) {
    const t = Number(row.candle_time);
    if (!Number.isFinite(t)) continue;
    const byFactor = (factorSnapshotByTime[t] ??= {});
    const factorName = String(row.factor_name || "").trim();
    if (!factorName) continue;
    byFactor[factorName] = row as ReplayFactorSnapshotV1;
  }

  return {
    window: resp.window,
    factorSnapshots: resp.factor_snapshots ?? [],
    factorSnapshotByTime
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
  setJobInfo: (jobId: string | null, cacheKey: string | null) => void;
};

async function pollReplayBuildStatus(ctx: ReplayBuildContext, targetJobId: string): Promise<void> {
  while (!ctx.isCancelled()) {
    let payload;
    try {
      payload = await fetchReplayStatus({ jobId: targetJobId, includePreload: true });
    } catch (err) {
      ctx.fail(extractHttpDetail(err));
      return;
    }
    if (payload.status === "done") {
      ctx.setMetadata(payload.metadata ?? null);
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
  const buildNow = async (windowCandles: number) => {
    ctx.setStatus("building");
    return fetchReplayBuild({
      series_id: ctx.seriesId,
      window_candles: windowCandles,
      window_size: ctx.windowSize,
      snapshot_interval: ctx.snapshotInterval
    });
  };

  let build: Awaited<ReturnType<typeof fetchReplayBuild>> | null = null;
  try {
    build = await buildNow(ctx.windowCandles);
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
    const canUsePartialCoverage =
      coverage?.status === "error" &&
      hasFlag(String(coverage.error ?? ""), "coverage_missing") &&
      Number(coverage.candles_ready || 0) > 0;
    if (!coverage || (coverage.status === "error" && !canUsePartialCoverage)) {
      ctx.fail(coverage?.error ?? "coverage_failed");
      return;
    }
    ctx.setCoverage({
      required_candles: coverage.required_candles,
      candles_ready: coverage.candles_ready,
      from_time: null,
      to_time: coverage.head_time ?? null
    });
    const fallbackWindowCandles = Math.min(
      Math.max(1, Number(coverage.candles_ready || 0)),
      Math.max(1, ctx.windowCandles)
    );
    try {
      build = await buildNow(fallbackWindowCandles);
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
