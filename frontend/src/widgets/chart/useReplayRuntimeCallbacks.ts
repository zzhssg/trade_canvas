import type { UTCTimestamp } from "lightweight-charts";
import { useCallback, useMemo, type MutableRefObject } from "react";
import {
  applyReplayOverlayAtTimeRuntime,
  applyReplayPackageWindowRuntime,
  requestReplayFrameAtTimeRuntime,
  type ReplayOverlayRuntimeArgs
} from "./replayOverlayRuntime";
import { timeframeToSeconds } from "./timeframe";
import type { Candle, OverlayInstructionPatchItemV1, ReplayFactorHeadSnapshotV1, ReplayHistoryDeltaV1, ReplayKlineBarV1, ReplayWindowV1 } from "./types";

export function toReplayCandle(bar: ReplayKlineBarV1): Candle {
  return { time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close };
}

type ReplayWindowBundleLike = {
  window: ReplayWindowV1;
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

type UseReplayOverlayRuntimeArgs = ReplayOverlayRuntimeArgs & {
  timeframe: string;
  windowCandles: number;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  replayWindowIndexRef: MutableRefObject<number | null>;
};

export function useReplayOverlayRuntime(args: UseReplayOverlayRuntimeArgs) {
  const overlayRuntimeArgs = useMemo<ReplayOverlayRuntimeArgs>(
    () => ({
      overlayCatalogRef: args.overlayCatalogRef,
      overlayActiveIdsRef: args.overlayActiveIdsRef,
      recomputeActiveIdsFromCatalog: args.recomputeActiveIdsFromCatalog,
      setReplayDrawInstructions: args.setReplayDrawInstructions,
      rebuildPivotMarkersFromOverlay: args.rebuildPivotMarkersFromOverlay,
      rebuildAnchorSwitchMarkersFromOverlay: args.rebuildAnchorSwitchMarkersFromOverlay,
      rebuildPenPointsFromOverlay: args.rebuildPenPointsFromOverlay,
      rebuildOverlayPolylinesFromOverlay: args.rebuildOverlayPolylinesFromOverlay,
      syncMarkers: args.syncMarkers,
      effectiveVisible: args.effectiveVisible,
      penSeriesRef: args.penSeriesRef,
      penPointsRef: args.penPointsRef,
      penSegmentsRef: args.penSegmentsRef,
      enablePenSegmentColor: args.enablePenSegmentColor,
      replayEnabled: args.replayEnabled,
      setPenPointCount: args.setPenPointCount
    }),
    [args.effectiveVisible, args.enablePenSegmentColor, args.rebuildOverlayPolylinesFromOverlay, args.rebuildPenPointsFromOverlay, args.rebuildPivotMarkersFromOverlay, args.rebuildAnchorSwitchMarkersFromOverlay, args.recomputeActiveIdsFromCatalog, args.replayEnabled, args.setPenPointCount, args.setReplayDrawInstructions, args.syncMarkers]
  );

  const applyReplayOverlayAtTime = useCallback(
    (toTime: number) =>
      applyReplayOverlayAtTimeRuntime({
        toTime,
        timeframeSeconds: timeframeToSeconds(args.timeframe),
        windowCandles: args.windowCandles,
        replayPatchRef: args.replayPatchRef,
        replayPatchAppliedIdxRef: args.replayPatchAppliedIdxRef,
        ...overlayRuntimeArgs
      }),
    [args.replayPatchAppliedIdxRef, args.replayPatchRef, args.timeframe, args.windowCandles, overlayRuntimeArgs]
  );

  const applyReplayPackageWindow = useCallback(
    (bundle: ReplayWindowBundleLike, targetIdx: number) =>
      applyReplayPackageWindowRuntime({
        bundle,
        targetIdx,
        replayWindowIndexRef: args.replayWindowIndexRef,
        ...overlayRuntimeArgs
      }),
    [args.replayWindowIndexRef, overlayRuntimeArgs]
  );

  return { applyReplayOverlayAtTime, applyReplayPackageWindow };
}

type UseReplayFrameRequestArgs = {
  replayEnabled: boolean;
  seriesId: string;
  windowCandles: number;
  replayFrameLatestTimeRef: MutableRefObject<number | null>;
  replayFramePendingTimeRef: MutableRefObject<number | null>;
  replayFramePullInFlightRef: MutableRefObject<boolean>;
  setReplayFrameLoading: (loading: boolean) => void;
  setReplayFrameError: (error: string | null) => void;
  setReplayFrame: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["setReplayFrame"];
  applyPenAndAnchorFromFactorSlices: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["applyPenAndAnchorFromFactorSlices"];
  setReplaySlices: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["setReplaySlices"];
  setReplayCandle: (value: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
};

export function useReplayFrameRequest(args: UseReplayFrameRequestArgs) {
  return useCallback(
    async (atTime: number) =>
      requestReplayFrameAtTimeRuntime({
        atTime,
        replayEnabled: args.replayEnabled,
        replayFrameLatestTimeRef: args.replayFrameLatestTimeRef,
        replayFramePendingTimeRef: args.replayFramePendingTimeRef,
        replayFramePullInFlightRef: args.replayFramePullInFlightRef,
        seriesId: args.seriesId,
        windowCandles: args.windowCandles,
        setReplayFrameLoading: args.setReplayFrameLoading,
        setReplayFrameError: args.setReplayFrameError,
        setReplayFrame: args.setReplayFrame,
        applyPenAndAnchorFromFactorSlices: args.applyPenAndAnchorFromFactorSlices,
        setReplaySlices: args.setReplaySlices,
        setReplayCandle: args.setReplayCandle,
        setReplayDrawInstructions: args.setReplayDrawInstructions
      }),
    [args.applyPenAndAnchorFromFactorSlices, args.replayEnabled, args.seriesId, args.setReplayCandle, args.setReplayDrawInstructions, args.setReplayFrame, args.setReplayFrameError, args.setReplayFrameLoading, args.setReplaySlices, args.windowCandles]
  );
}
