import { useCallback, useEffect, useMemo, useRef } from "react";

import {
  fetchReplayBuild,
  fetchReplayCoverageStatus,
  fetchReplayEnsureCoverage,
  fetchReplayStatus,
  fetchReplayWindow
} from "./api";
import type { ReplayFactorHeadSnapshotV1, ReplayHistoryDeltaV1, ReplayHistoryEventV1, ReplayWindowResponseV1 } from "./types";
import { useReplayStore } from "../../state/replayStore";

const ENABLE_REPLAY_PACKAGE_V1 = import.meta.env.VITE_ENABLE_REPLAY_PACKAGE_V1 === "1";

const POLL_INTERVAL_MS = 300;

function sleep(ms: number) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function extractHttpDetail(err: unknown): string {
  if (!(err instanceof Error)) return "unknown_error";
  const message = String(err.message || "").trim();
  const idx = message.indexOf(":");
  if (idx <= 0) return message || "unknown_error";
  return message.slice(idx + 1).trim() || message;
}

function sortHistoryEvents(events: ReplayHistoryEventV1[]): ReplayHistoryEventV1[] {
  const list = events.slice();
  list.sort((a, b) => a.event_id - b.event_id);
  return list;
}

/** 将后端 window 响应转换为按 time/idx 索引的 bundle, 方便 O(1) 查找 */
function buildWindowBundle(resp: ReplayWindowResponseV1) {
  const headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>> = {};
  const historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1> = {};

  for (const snap of resp.factor_head_snapshots ?? []) {
    const t = Number(snap.candle_time);
    if (!Number.isFinite(t)) continue;
    if (!headByTime[t]) headByTime[t] = {};
    const cur = headByTime[t]![snap.factor_name];
    if (!cur || (snap.seq ?? 0) >= (cur.seq ?? 0)) {
      headByTime[t]![snap.factor_name] = snap as ReplayFactorHeadSnapshotV1;
    }
  }

  for (const delta of resp.history_deltas ?? []) {
    historyDeltaByIdx[delta.idx] = delta;
  }

  return {
    window: resp.window,
    headSnapshots: resp.factor_head_snapshots ?? [],
    historyDeltas: resp.history_deltas ?? [],
    headByTime,
    historyDeltaByIdx
  };
}

/**
 * 回放包生命周期管理 hook。
 *
 * 状态机: idle → checking → coverage → building → ready (或 error / out_of_sync)
 *
 * 流程:
 * 1. checking — 调用 fetchReplayBuild 尝试构建
 * 2. coverage — 若数据不足, 触发 ensureCoverage 轮询补数据
 * 3. building — 数据就绪后重新 build, 轮询 loadStatus 等待完成
 * 4. ready — 元数据 + historyEvents 就绪, 可按需加载 window
 *
 * 每次 seriesId / windowCandles / windowSize / snapshotInterval 变化都会重新触发。
 */
export function useReplayPackage(params: {
  seriesId: string;
  enabled: boolean;
  windowCandles: number;
  windowSize: number;
  snapshotInterval: number;
}) {
  const { seriesId, enabled, windowCandles, windowSize, snapshotInterval } = params;
  const effectiveEnabled = ENABLE_REPLAY_PACKAGE_V1 && enabled;

  const status = useReplayStore((s) => s.status);
  const error = useReplayStore((s) => s.error);
  const coverage = useReplayStore((s) => s.coverage);
  const coverageStatus = useReplayStore((s) => s.coverageStatus);
  const metadata = useReplayStore((s) => s.metadata);
  const historyEvents = useReplayStore((s) => s.historyEvents);
  const windows = useReplayStore((s) => s.windows);
  const jobId = useReplayStore((s) => s.jobId);
  const cacheKey = useReplayStore((s) => s.cacheKey);

  const setStatus = useReplayStore((s) => s.setStatus);
  const setError = useReplayStore((s) => s.setError);
  const setCoverage = useReplayStore((s) => s.setCoverage);
  const setCoverageStatus = useReplayStore((s) => s.setCoverageStatus);
  const setMetadata = useReplayStore((s) => s.setMetadata);
  const setHistoryEvents = useReplayStore((s) => s.setHistoryEvents);
  const setJobInfo = useReplayStore((s) => s.setJobInfo);
  const setWindowBundle = useReplayStore((s) => s.setWindowBundle);
  const resetPackage = useReplayStore((s) => s.resetPackage);

  const loadingWindowsRef = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!effectiveEnabled) {
      resetPackage();
      return;
    }

    let cancelled = false;

    async function loadStatus(targetJobId: string) {
      while (!cancelled) {
        let payload;
        try {
          payload = await fetchReplayStatus({
            jobId: targetJobId,
            includePreload: true,
            includeHistory: true
          });
        } catch (err) {
          if (cancelled) return;
          setStatus("error");
          setError(extractHttpDetail(err));
          return;
        }
        if (cancelled) return;
        if (payload.status === "done") {
          setMetadata(payload.metadata ?? null);
          setHistoryEvents(sortHistoryEvents(payload.history_events ?? []));
          setStatus("ready");
          setError(null);
          return;
        }
        if (payload.status === "error") {
          setStatus("error");
          setError(payload.error ?? "build_failed");
          return;
        }
        await sleep(POLL_INTERVAL_MS);
      }
    }

    async function ensureCoverage(toTime?: number) {
      const ensure = await fetchReplayEnsureCoverage({
        series_id: seriesId,
        target_candles: windowCandles,
        to_time: toTime
      });
      setCoverageStatus({ status: "building", job_id: ensure.job_id, candles_ready: 0, required_candles: windowCandles });

      while (!cancelled) {
        const statusResp = await fetchReplayCoverageStatus({ jobId: ensure.job_id });
        if (cancelled) return statusResp;
        setCoverageStatus(statusResp);
        if (statusResp.status === "done") return statusResp;
        if (statusResp.status === "error") return statusResp;
        await sleep(POLL_INTERVAL_MS);
      }
      return null;
    }

    async function run() {
      resetPackage();
      setStatus("checking");
      setError(null);
      setCoverage(null);
      setCoverageStatus(null);
      setMetadata(null);
      setHistoryEvents([]);

      const buildPayload = {
        series_id: seriesId,
        window_candles: windowCandles,
        window_size: windowSize,
        snapshot_interval: snapshotInterval
      };

      let build;
      try {
        setStatus("building");
        build = await fetchReplayBuild(buildPayload);
      } catch (err) {
        if (cancelled) return;
        const detail = extractHttpDetail(err);
        if (detail.includes("coverage_missing")) {
          setStatus("coverage");
          const cov = await ensureCoverage(undefined);
          if (cancelled) return;
          if (!cov || cov.status === "error") {
            setStatus("error");
            setError(cov?.error ?? "coverage_failed");
            return;
          }
          setCoverage({
            required_candles: cov.required_candles,
            candles_ready: cov.candles_ready,
            from_time: null,
            to_time: cov.head_time ?? null
          });
          try {
            setStatus("building");
            build = await fetchReplayBuild(buildPayload);
          } catch (retryErr) {
            if (cancelled) return;
            const retryDetail = extractHttpDetail(retryErr);
            if (retryDetail.includes("ledger_out_of_sync")) {
              setStatus("out_of_sync");
              setError(retryDetail);
              return;
            }
            setStatus("error");
            setError(retryDetail || "build_failed");
            return;
          }
        } else if (detail.includes("ledger_out_of_sync")) {
          setStatus("out_of_sync");
          setError(detail);
          return;
        } else {
          setStatus("error");
          setError(detail || "build_failed");
          return;
        }
      }

      if (cancelled || !build) return;
      setJobInfo(build.job_id, build.cache_key);
      await loadStatus(build.job_id);
    }

    void run();

    return () => {
      cancelled = true;
    };
  }, [effectiveEnabled, seriesId, windowCandles, windowSize, snapshotInterval, resetPackage, setCoverage, setCoverageStatus, setError, setHistoryEvents, setJobInfo, setMetadata, setStatus]);

  const ensureWindowByIndex = useCallback(
    async (windowIndex: number) => {
      if (!effectiveEnabled) return null;
      const currentJobId = jobId;
      if (!currentJobId) return null;
      if (windows[windowIndex]) return windows[windowIndex];
      if (loadingWindowsRef.current.has(windowIndex)) return null;
      loadingWindowsRef.current.add(windowIndex);
      try {
        const targetIdx = Math.max(0, windowIndex * windowSize);
        const resp = await fetchReplayWindow({ jobId: currentJobId, targetIdx });
        const bundle = buildWindowBundle(resp);
        setWindowBundle(windowIndex, bundle);
        return bundle;
      } finally {
        loadingWindowsRef.current.delete(windowIndex);
      }
    },
    [effectiveEnabled, jobId, setWindowBundle, windowSize, windows]
  );

  const ensureWindowRange = useCallback(
    async (startIdx: number, endIdx: number) => {
      if (!effectiveEnabled) return;
      const startWindow = Math.floor(startIdx / windowSize);
      const endWindow = Math.floor(endIdx / windowSize);
      for (let w = startWindow; w <= endWindow; w += 1) {
        if (windows[w]) continue;
        await ensureWindowByIndex(w);
      }
    },
    [effectiveEnabled, ensureWindowByIndex, windowSize, windows]
  );

  const windowInfo = useMemo(() => ({ windowCandles, windowSize, snapshotInterval }), [windowCandles, windowSize, snapshotInterval]);

  return {
    enabled: effectiveEnabled,
    status,
    error,
    coverage,
    coverageStatus,
    metadata,
    historyEvents,
    windows,
    jobId,
    cacheKey,
    windowInfo,
    ensureWindowByIndex,
    ensureWindowRange
  };
}
