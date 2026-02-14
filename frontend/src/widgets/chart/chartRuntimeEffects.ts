import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";
import type { ReplayWindowBundle } from "../../state/replayStore";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import { buildReplayFactorSlices } from "./replayFactorSlices";
import {
  useChartLiveSessionEffect,
  useChartSeriesSyncEffects,
  useReplayFocusSyncEffect,
  useReplayPackageResetEffect
} from "./useChartSessionEffects";
import { useReplayPackageWindowSync } from "./useReplayPackageWindowSync";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  ReplayHistoryEventV1,
  ReplayKlineBarV1,
  ReplayPackageMetadataV1,
  WorldStateV1
} from "./types";
import type { ReplayPenPreviewFeature, StartChartLiveSessionArgs } from "./liveSessionRuntimeTypes";

type ReplayOverlayBundle = {
  window: ReplayWindowBundle["window"];
  headByTime: ReplayWindowBundle["headByTime"];
  historyDeltaByIdx: ReplayWindowBundle["historyDeltaByIdx"];
};
type UseChartRuntimeEffectsBaseArgs = Omit<StartChartLiveSessionArgs, "candleSeriesRef"> & {
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
};

export type UseChartRuntimeEffectsArgs = UseChartRuntimeEffectsBaseArgs & {
  replayPrepareStatus: string;
  replayPackageEnabled: boolean;
  replayPackageStatus: string;
  replayPackageMeta: ReplayPackageMetadataV1 | null;
  replayPackageHistory: ReplayHistoryEventV1[];
  replayPackageWindows: Record<number, ReplayWindowBundle>;
  replayEnsureWindowRange: (startIdx: number, endIdx: number) => Promise<void>;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  candles: Candle[];
  visibleFeatures: Record<string, boolean | undefined>;
  chartEpoch: number;
  anchorHighlightEpoch: number;
  enableAnchorTopLayer: boolean;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  applyReplayOverlayAtTime: (toTime: number) => void;
  applyReplayPackageWindow: (bundle: ReplayOverlayBundle, targetIdx: number) => string[];
  requestReplayFrameAtTime: (atTime: number) => Promise<void>;
  toReplayCandle: (bar: ReplayKlineBarV1) => Candle;
  setReplayFocusTime: (value: number | null) => void;
  setReplayFrame: (frame: WorldStateV1 | null) => void;
  setReplaySlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setReplayCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  setReplayFrameLoading: (value: boolean) => void;
  setReplayFrameError: (value: string | null) => void;
};

export function useChartRuntimeEffects(args: UseChartRuntimeEffectsArgs) {
  useChartSeriesSyncEffects({
    candles: args.candles,
    chartEpoch: args.chartEpoch,
    chartRef: args.chartRef,
    seriesRef: args.seriesRef,
    candlesRef: args.candlesRef,
    appliedRef: args.appliedRef,
    lineSeriesByKeyRef: args.lineSeriesByKeyRef,
    entryEnabledRef: args.entryEnabledRef,
    entryMarkersRef: args.entryMarkersRef,
    syncMarkers: args.syncMarkers,
    visibleFeatures: args.visibleFeatures,
    effectiveVisible: args.effectiveVisible,
    rebuildPivotMarkersFromOverlay: args.rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay: args.rebuildAnchorSwitchMarkersFromOverlay,
    rebuildOverlayPolylinesFromOverlay: args.rebuildOverlayPolylinesFromOverlay,
    penSeriesRef: args.penSeriesRef,
    penSegmentSeriesByKeyRef: args.penSegmentSeriesByKeyRef,
    penSegmentsRef: args.penSegmentsRef,
    penPointsRef: args.penPointsRef,
    anchorPenSeriesRef: args.anchorPenSeriesRef,
    anchorPenPointsRef: args.anchorPenPointsRef,
    anchorPenIsDashedRef: args.anchorPenIsDashedRef,
    replayPenPreviewSeriesByFeatureRef: args.replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef: args.replayPenPreviewPointsRef,
    enablePenSegmentColor: args.enablePenSegmentColor,
    enableAnchorTopLayer: args.enableAnchorTopLayer,
    replayEnabled: args.replayEnabled,
    setPenPointCount: args.setPenPointCount,
    anchorHighlightEpoch: args.anchorHighlightEpoch,
    seriesId: args.seriesId
  });

  useChartLiveSessionEffect({
    seriesId: args.seriesId,
    timeframe: args.timeframe,
    replayEnabled: args.replayEnabled,
    replayPreparedAlignedTime: args.replayPreparedAlignedTime,
    replayPackageEnabled: args.replayPackageEnabled,
    replayPrepareStatus: args.replayPrepareStatus,
    windowCandles: args.windowCandles,
    enableWorldFrame: args.enableWorldFrame,
    enablePenSegmentColor: args.enablePenSegmentColor,
    openMarketWs: args.openMarketWs,
    chartRef: args.chartRef,
    candleSeriesRef: args.seriesRef,
    candlesRef: args.candlesRef,
    setCandles: args.setCandles,
    lastWsCandleTimeRef: args.lastWsCandleTimeRef,
    setLastWsCandleTime: args.setLastWsCandleTime,
    setLiveLoadState: args.setLiveLoadState,
    appliedRef: args.appliedRef,
    pivotMarkersRef: args.pivotMarkersRef,
    anchorSwitchMarkersRef: args.anchorSwitchMarkersRef,
    overlayCatalogRef: args.overlayCatalogRef,
    overlayActiveIdsRef: args.overlayActiveIdsRef,
    overlayCursorVersionRef: args.overlayCursorVersionRef,
    overlayPullInFlightRef: args.overlayPullInFlightRef,
    overlayPolylineSeriesByIdRef: args.overlayPolylineSeriesByIdRef,
    replayPenPreviewSeriesByFeatureRef: args.replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef: args.replayPenPreviewPointsRef,
    followPendingTimeRef: args.followPendingTimeRef,
    followTimerIdRef: args.followTimerIdRef,
    penSegmentsRef: args.penSegmentsRef,
    anchorPenPointsRef: args.anchorPenPointsRef,
    factorPullPendingTimeRef: args.factorPullPendingTimeRef,
    factorPullInFlightRef: args.factorPullInFlightRef,
    lastFactorAtTimeRef: args.lastFactorAtTimeRef,
    worldFrameHealthyRef: args.worldFrameHealthyRef,
    replayAllCandlesRef: args.replayAllCandlesRef,
    replayPatchRef: args.replayPatchRef,
    replayPatchAppliedIdxRef: args.replayPatchAppliedIdxRef,
    replayFrameLatestTimeRef: args.replayFrameLatestTimeRef,
    penSeriesRef: args.penSeriesRef,
    penPointsRef: args.penPointsRef,
    effectiveVisible: args.effectiveVisible,
    showToast: args.showToast,
    setError: args.setError,
    setZhongshuCount: args.setZhongshuCount,
    setAnchorCount: args.setAnchorCount,
    setAnchorHighlightEpoch: args.setAnchorHighlightEpoch,
    setPivotCount: args.setPivotCount,
    setAnchorSwitchCount: args.setAnchorSwitchCount,
    setPenPointCount: args.setPenPointCount,
    setReplayTotal: args.setReplayTotal,
    setReplayPlaying: args.setReplayPlaying,
    setReplayIndex: args.setReplayIndex,
    applyOverlayDelta: args.applyOverlayDelta,
    fetchOverlayLikeDelta: args.fetchOverlayLikeDelta,
    rebuildPivotMarkersFromOverlay: args.rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay: args.rebuildAnchorSwitchMarkersFromOverlay,
    rebuildPenPointsFromOverlay: args.rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay: args.rebuildOverlayPolylinesFromOverlay,
    syncMarkers: args.syncMarkers,
    fetchAndApplyAnchorHighlightAtTime: args.fetchAndApplyAnchorHighlightAtTime,
    applyWorldFrame: args.applyWorldFrame,
    applyPenAndAnchorFromFactorSlices: args.applyPenAndAnchorFromFactorSlices
  });

  useReplayPackageResetEffect({
    replayPackageEnabled: args.replayPackageEnabled,
    seriesId: args.seriesId,
    setCandles: args.setCandles,
    candlesRef: args.candlesRef,
    replayAllCandlesRef: args.replayAllCandlesRef,
    replayWindowIndexRef: args.replayWindowIndexRef,
    pivotMarkersRef: args.pivotMarkersRef,
    overlayCatalogRef: args.overlayCatalogRef,
    overlayActiveIdsRef: args.overlayActiveIdsRef,
    overlayCursorVersionRef: args.overlayCursorVersionRef,
    overlayPullInFlightRef: args.overlayPullInFlightRef,
    penSegmentsRef: args.penSegmentsRef,
    anchorPenPointsRef: args.anchorPenPointsRef,
    replayPenPreviewPointsRef: args.replayPenPreviewPointsRef,
    factorPullPendingTimeRef: args.factorPullPendingTimeRef,
    lastFactorAtTimeRef: args.lastFactorAtTimeRef,
    replayPatchRef: args.replayPatchRef,
    replayPatchAppliedIdxRef: args.replayPatchAppliedIdxRef,
    setAnchorHighlightEpoch: args.setAnchorHighlightEpoch,
    setPivotCount: args.setPivotCount,
    setPenPointCount: args.setPenPointCount,
    setError: args.setError,
    setReplayIndex: args.setReplayIndex,
    setReplayPlaying: args.setReplayPlaying,
    setReplayTotal: args.setReplayTotal,
    setReplayFocusTime: args.setReplayFocusTime,
    setReplayFrame: args.setReplayFrame,
    setReplaySlices: args.setReplaySlices,
    setReplayCandle: args.setReplayCandle,
    setReplayDrawInstructions: args.setReplayDrawInstructions
  });

  useReplayPackageWindowSync({
    enabled: args.replayPackageEnabled,
    status: args.replayPackageStatus,
    metadata: args.replayPackageMeta,
    windows: args.replayPackageWindows,
    historyEvents: args.replayPackageHistory,
    ensureWindowRange: args.replayEnsureWindowRange,
    replayIndex: args.replayIndex,
    replayFocusTime: args.replayFocusTime,
    seriesId: args.seriesId,
    replayAllCandlesRef: args.replayAllCandlesRef,
    lastFactorAtTimeRef: args.lastFactorAtTimeRef,
    candlesRef: args.candlesRef,
    toReplayCandle: args.toReplayCandle,
    applyReplayPackageWindow: args.applyReplayPackageWindow,
    buildReplayFactorSlices: useCallback(
      (runtimeArgs) => buildReplayFactorSlices({ ...runtimeArgs, seriesId: args.seriesId }),
      [args.seriesId]
    ),
    applyPenAndAnchorFromFactorSlices: args.applyPenAndAnchorFromFactorSlices,
    setReplayTotal: args.setReplayTotal,
    setReplayIndex: args.setReplayIndex,
    setReplayFocusTime: args.setReplayFocusTime,
    setReplaySlices: args.setReplaySlices,
    setReplayCandle: args.setReplayCandle,
    setCandles: args.setCandles
  });

  useReplayFocusSyncEffect({
    replayEnabled: args.replayEnabled,
    replayPackageEnabled: args.replayPackageEnabled,
    replayIndex: args.replayIndex,
    replayTotal: args.replayTotal,
    replayAllCandlesRef: args.replayAllCandlesRef,
    setReplayIndex: args.setReplayIndex,
    setReplayFocusTime: args.setReplayFocusTime,
    applyReplayOverlayAtTime: args.applyReplayOverlayAtTime,
    fetchAndApplyAnchorHighlightAtTime: args.fetchAndApplyAnchorHighlightAtTime,
    requestReplayFrameAtTime: args.requestReplayFrameAtTime
  });
}
