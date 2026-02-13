import type { ISeriesApi, UTCTimestamp } from "lightweight-charts";
import { useCallback, type MutableRefObject } from "react";

import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import {
  applyReplayOverlayAtTimeRuntime,
  applyReplayPackageWindowRuntime,
  requestReplayFrameAtTimeRuntime
} from "./replayOverlayRuntime";
import { timeframeToSeconds } from "./timeframe";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayKlineBarV1,
  ReplayWindowV1
} from "./types";

export function toReplayCandle(bar: ReplayKlineBarV1): Candle {
  return {
    time: bar.time as UTCTimestamp,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close
  };
}

type UseReplayOverlayRuntimeArgs = {
  timeframe: string;
  windowCandles: number;
  replayEnabled: boolean;
  enablePenSegmentColor: boolean;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  recomputeActiveIdsFromCatalog: (params: { cutoffTime: number; toTime: number }) => string[];
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  syncMarkers: () => void;
  effectiveVisible: (key: string) => boolean;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  setPenPointCount: (value: number) => void;
};

export function useReplayOverlayRuntime(args: UseReplayOverlayRuntimeArgs) {
  const applyReplayOverlayAtTime = useCallback(
    (toTime: number) => {
      applyReplayOverlayAtTimeRuntime({
        toTime,
        timeframeSeconds: timeframeToSeconds(args.timeframe),
        windowCandles: args.windowCandles,
        replayPatchRef: args.replayPatchRef,
        replayPatchAppliedIdxRef: args.replayPatchAppliedIdxRef,
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
      });
    },
    [
      args.effectiveVisible,
      args.enablePenSegmentColor,
      args.rebuildOverlayPolylinesFromOverlay,
      args.rebuildPenPointsFromOverlay,
      args.rebuildPivotMarkersFromOverlay,
      args.rebuildAnchorSwitchMarkersFromOverlay,
      args.recomputeActiveIdsFromCatalog,
      args.replayEnabled,
      args.setPenPointCount,
      args.setReplayDrawInstructions,
      args.syncMarkers,
      args.timeframe,
      args.windowCandles
    ]
  );

  const applyReplayPackageWindow = useCallback(
    (
      bundle: {
        window: ReplayWindowV1;
        headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
        historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
      },
      targetIdx: number
    ) => {
      return applyReplayPackageWindowRuntime({
        bundle,
        targetIdx,
        replayWindowIndexRef: args.replayWindowIndexRef,
        overlayCatalogRef: args.overlayCatalogRef,
        overlayActiveIdsRef: args.overlayActiveIdsRef,
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
      });
    },
    [
      args.effectiveVisible,
      args.enablePenSegmentColor,
      args.rebuildOverlayPolylinesFromOverlay,
      args.rebuildPenPointsFromOverlay,
      args.rebuildPivotMarkersFromOverlay,
      args.rebuildAnchorSwitchMarkersFromOverlay,
      args.replayEnabled,
      args.setPenPointCount,
      args.setReplayDrawInstructions,
      args.syncMarkers
    ]
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
    async (atTime: number) => {
      await requestReplayFrameAtTimeRuntime({
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
      });
    },
    [
      args.applyPenAndAnchorFromFactorSlices,
      args.replayEnabled,
      args.seriesId,
      args.setReplayCandle,
      args.setReplayDrawInstructions,
      args.setReplayFrame,
      args.setReplayFrameError,
      args.setReplayFrameLoading,
      args.setReplaySlices,
      args.windowCandles
    ]
  );
}
