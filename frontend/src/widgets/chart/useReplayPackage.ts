import { useCallback, useEffect, useMemo, useRef } from "react";
import type { ReplayStatus, ReplayWindowBundle } from "../../state/replayStore";
import { useReplayActions, useReplayPackageState } from "../../state/replayStoreSelectors";
import { fetchReplayWindow } from "./api";
import { buildWindowBundle, runReplayBuildFlow } from "./replayPackageRuntime";
import type { ReplayCoverageStatusResponseV1, ReplayCoverageV1, ReplayPackageMetadataV1 } from "./types";

export type ReplayPackageParams = {
  seriesId: string;
  enabled: boolean;
  windowCandles: number;
  windowSize: number;
  snapshotInterval: number;
};

type ReplayBuildStore = {
  resetPackage: () => void;
  setStatus: (status: ReplayStatus) => void;
  setError: (error: string | null) => void;
  setCoverage: (coverage: ReplayCoverageV1 | null) => void;
  setCoverageStatus: (status: ReplayCoverageStatusResponseV1 | null) => void;
  setMetadata: (metadata: ReplayPackageMetadataV1 | null) => void;
  setJobInfo: (jobId: string | null, cacheKey: string | null) => void;
};

type ReplayBuildSyncParams = Omit<ReplayPackageParams, "enabled"> & { effectiveEnabled: boolean; store: ReplayBuildStore };

function useReplayPackageBuildSync(args: ReplayBuildSyncParams) {
  const { effectiveEnabled, seriesId, windowCandles, windowSize, snapshotInterval, store } = args;
  const { resetPackage, setStatus, setError, setCoverage, setCoverageStatus, setMetadata, setJobInfo } = store;
  useEffect(() => {
    if (!effectiveEnabled) {
      resetPackage();
      return;
    }
    let cancelled = false;
    const fail = (detail: string, nextStatus: "error" | "out_of_sync" = "error") => {
      if (cancelled) return;
      setStatus(nextStatus);
      setError(detail || "build_failed");
    };
    resetPackage();
    setStatus("checking");
    setError(null);
    setCoverage(null);
    setCoverageStatus(null);
    setMetadata(null);
    void runReplayBuildFlow({
      seriesId,
      windowCandles,
      windowSize,
      snapshotInterval,
      isCancelled: () => cancelled,
      fail,
      setStatus,
      setError,
      setCoverage,
      setCoverageStatus,
      setMetadata,
      setJobInfo
    });
    return () => {
      cancelled = true;
    };
  }, [effectiveEnabled, resetPackage, seriesId, setCoverage, setCoverageStatus, setError, setJobInfo, setMetadata, setStatus, snapshotInterval, windowCandles, windowSize]);
}

function useReplayWindowLoader(args: {
  effectiveEnabled: boolean;
  jobId: string | null;
  windowSize: number;
  windows: Record<number, ReplayWindowBundle>;
  setWindowBundle: (windowIndex: number, bundle: ReplayWindowBundle) => void;
}) {
  const { effectiveEnabled, jobId, windowSize, windows, setWindowBundle } = args;
  const loadingWindowsRef = useRef<Set<number>>(new Set());
  const ensureWindowByIndex = useCallback(async (windowIndex: number) => {
    if (!effectiveEnabled || !jobId || windows[windowIndex] || loadingWindowsRef.current.has(windowIndex)) {
      return windows[windowIndex] ?? null;
    }
    loadingWindowsRef.current.add(windowIndex);
    try {
      const targetIdx = Math.max(0, windowIndex * windowSize);
      const bundle = buildWindowBundle(await fetchReplayWindow({ jobId, targetIdx }));
      setWindowBundle(windowIndex, bundle);
      return bundle;
    } finally {
      loadingWindowsRef.current.delete(windowIndex);
    }
  }, [effectiveEnabled, jobId, setWindowBundle, windowSize, windows]);

  const ensureWindowRange = useCallback(async (startIdx: number, endIdx: number) => {
    if (!effectiveEnabled) return;
    for (let w = Math.floor(startIdx / windowSize); w <= Math.floor(endIdx / windowSize); w += 1) {
      if (!windows[w]) await ensureWindowByIndex(w);
    }
  }, [effectiveEnabled, ensureWindowByIndex, windowSize, windows]);

  return { ensureWindowByIndex, ensureWindowRange };
}

export function useReplayPackage(params: ReplayPackageParams) {
  const { seriesId, enabled, windowCandles, windowSize, snapshotInterval } = params;
  const effectiveEnabled = enabled;
  const replayPackageState = useReplayPackageState();
  const replayActions = useReplayActions();
  useReplayPackageBuildSync({
    effectiveEnabled,
    seriesId,
    windowCandles,
    windowSize,
    snapshotInterval,
    store: {
      resetPackage: replayActions.resetPackage,
      setStatus: replayActions.setStatus,
      setError: replayActions.setError,
      setCoverage: replayActions.setCoverage,
      setCoverageStatus: replayActions.setCoverageStatus,
      setMetadata: replayActions.setMetadata,
      setJobInfo: replayActions.setJobInfo
    }
  });
  const { ensureWindowByIndex, ensureWindowRange } = useReplayWindowLoader({
    effectiveEnabled,
    jobId: replayPackageState.jobId,
    windowSize,
    windows: replayPackageState.windows,
    setWindowBundle: replayActions.setWindowBundle
  });
  return {
    enabled: effectiveEnabled,
    status: replayPackageState.status,
    error: replayPackageState.error,
    coverage: replayPackageState.coverage,
    coverageStatus: replayPackageState.coverageStatus,
    metadata: replayPackageState.metadata,
    windows: replayPackageState.windows,
    jobId: replayPackageState.jobId,
    cacheKey: replayPackageState.cacheKey,
    windowInfo: useMemo(() => ({ windowCandles, windowSize, snapshotInterval }), [windowCandles, windowSize, snapshotInterval]),
    ensureWindowByIndex,
    ensureWindowRange
  };
}
