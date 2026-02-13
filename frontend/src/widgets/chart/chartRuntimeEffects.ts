import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";

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
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayKlineBarV1,
  ReplayWindowV1,
  WorldStateV1
} from "./types";
import type { OpenMarketWs } from "./liveSessionRuntimeTypes";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

type ReplayPackageBundle = {
  window: ReplayWindowV1;
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

export type UseChartRuntimeEffectsArgs = {
  seriesId: string;
  timeframe: string;
  replayEnabled: boolean;
  replayPreparedAlignedTime: number | null;
  replayPrepareStatus: string;
  replayPackageEnabled: boolean;
  replayPackageStatus: string;
  replayPackageMeta: unknown;
  replayPackageHistory: unknown;
  replayPackageWindows: Record<number, ReplayPackageBundle>;
  replayEnsureWindowRange: (args: { start: number; end: number }) => Promise<void>;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  candles: Candle[];
  visibleFeatures: Record<string, boolean | undefined>;
  chartEpoch: number;
  anchorHighlightEpoch: number;
  enablePenSegmentColor: boolean;
  enableAnchorTopLayer: boolean;
  enableWorldFrame: boolean;
  windowCandles: number;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  candlesRef: MutableRefObject<Candle[]>;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  pivotMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  anchorSwitchMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  overlayPullInFlightRef: MutableRefObject<boolean>;
  overlayPolylineSeriesByIdRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  followPendingTimeRef: MutableRefObject<number | null>;
  followTimerIdRef: MutableRefObject<number | null>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  worldFrameHealthyRef: MutableRefObject<boolean>;
  replayAllCandlesRef: MutableRefObject<Array<Candle | null>>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  replayFrameLatestTimeRef: MutableRefObject<number | null>;
  syncMarkers: () => void;
  effectiveVisible: (key: string) => boolean;
  openMarketWs: OpenMarketWs;
  fetchOverlayLikeDelta: (params: { seriesId: string; cursorVersionId: number; windowCandles: number }) => Promise<OverlayLikeDeltaV1>;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  fetchAndApplyAnchorHighlightAtTime: (time: number) => Promise<void>;
  applyOverlayDelta: (delta: OverlayLikeDeltaV1) => void;
  applyWorldFrame: (frame: WorldStateV1) => void;
  applyPenAndAnchorFromFactorSlices: (slices: GetFactorSlicesResponseV1) => void;
  applyReplayOverlayAtTime: (toTime: number) => void;
  applyReplayPackageWindow: (bundle: ReplayPackageBundle, targetIdx: number) => string[];
  requestReplayFrameAtTime: (atTime: number) => Promise<void>;
  toReplayCandle: (bar: ReplayKlineBarV1) => Candle;
  setCandles: Dispatch<SetStateAction<Candle[]>>;
  setReplayTotal: (value: number) => void;
  setReplayPlaying: (value: boolean) => void;
  setReplayIndex: (value: number) => void;
  setReplayFocusTime: (value: number | null) => void;
  setReplayFrame: (frame: WorldStateV1 | null) => void;
  setReplaySlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setReplayCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  setReplayFrameLoading: (value: boolean) => void;
  setReplayFrameError: (value: string | null) => void;
  setLastWsCandleTime: (value: number | null) => void;
  setError: (value: string | null) => void;
  setZhongshuCount: (value: number) => void;
  setAnchorCount: (value: number) => void;
  setPivotCount: (value: number) => void;
  setAnchorSwitchCount: (value: number) => void;
  setPenPointCount: (value: number) => void;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  showToast: (message: string) => void;
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
