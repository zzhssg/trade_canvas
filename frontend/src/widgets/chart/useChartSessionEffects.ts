import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useEffect, type MutableRefObject } from "react";

import { startChartLiveSession } from "./liveSessionRuntime";
import type { StartChartLiveSessionArgs } from "./liveSessionRuntimeTypes";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import { resetReplayPackageState, syncReplayFocusFromIndex } from "./replayRuntimeHelpers";
import { syncCandlesToSeries, syncOverlayLayers } from "./seriesSyncRuntime";
import type { Candle } from "./types";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

type UseChartSeriesSyncEffectsArgs = {
  candles: Candle[];
  chartEpoch: number;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  candlesRef: MutableRefObject<Candle[]>;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  syncMarkers: () => void;
  visibleFeatures: Record<string, boolean | undefined>;
  effectiveVisible: (key: string) => boolean;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  enablePenSegmentColor: boolean;
  enableAnchorTopLayer: boolean;
  replayEnabled: boolean;
  setPenPointCount: (value: number) => void;
  anchorHighlightEpoch: number;
  seriesId: string;
};

export function useChartSeriesSyncEffects(args: UseChartSeriesSyncEffectsArgs) {
  useEffect(() => {
    const series = args.seriesRef.current;
    if (!series) return;
    syncCandlesToSeries({
      candles: args.candles,
      series,
      chart: args.chartRef.current,
      appliedRef: args.appliedRef,
      lineSeriesByKeyRef: args.lineSeriesByKeyRef,
      entryEnabledRef: args.entryEnabledRef,
      entryMarkersRef: args.entryMarkersRef,
      syncMarkers: args.syncMarkers
    });
  }, [args.candles, args.chartEpoch]);

  useEffect(() => {
    args.candlesRef.current = args.candles;
  }, [args.candles]);

  useEffect(() => {
    const chart = args.chartRef.current;
    const candleSeries = args.seriesRef.current;
    if (!chart || !candleSeries) return;
    syncOverlayLayers({
      chart,
      visibleFeatures: args.visibleFeatures,
      effectiveVisible: args.effectiveVisible,
      candlesRef: args.candlesRef,
      lineSeriesByKeyRef: args.lineSeriesByKeyRef,
      entryEnabledRef: args.entryEnabledRef,
      entryMarkersRef: args.entryMarkersRef,
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
      syncMarkers: args.syncMarkers
    });
  }, [
    args.anchorHighlightEpoch,
    args.chartEpoch,
    args.effectiveVisible,
    args.replayEnabled,
    args.rebuildOverlayPolylinesFromOverlay,
    args.rebuildPivotMarkersFromOverlay,
    args.rebuildAnchorSwitchMarkersFromOverlay,
    args.seriesId,
    args.syncMarkers,
    args.visibleFeatures
  ]);
}

type UseChartLiveSessionEffectArgs = StartChartLiveSessionArgs & {
  replayPackageEnabled: boolean;
  replayPrepareStatus: string;
};

export function useChartLiveSessionEffect(args: UseChartLiveSessionEffectArgs) {
  useEffect(() => {
    if (args.replayPackageEnabled) return;
    if (args.replayEnabled && args.replayPrepareStatus !== "ready") return;
    const session = startChartLiveSession(args);
    return () => session.stop();
  }, [
    args.applyOverlayDelta,
    args.applyPenAndAnchorFromFactorSlices,
    args.applyWorldFrame,
    args.effectiveVisible,
    args.fetchAndApplyAnchorHighlightAtTime,
    args.fetchOverlayLikeDelta,
    args.openMarketWs,
    args.rebuildOverlayPolylinesFromOverlay,
    args.rebuildPenPointsFromOverlay,
    args.rebuildPivotMarkersFromOverlay,
    args.rebuildAnchorSwitchMarkersFromOverlay,
    args.replayEnabled,
    args.replayPackageEnabled,
    args.replayPrepareStatus,
    args.replayPreparedAlignedTime,
    args.seriesId,
    args.showToast,
    args.syncMarkers,
    args.timeframe
  ]);
}

type UseReplayPackageResetEffectArgs = Parameters<typeof resetReplayPackageState>[0] & {
  replayPackageEnabled: boolean;
  seriesId: string;
};

export function useReplayPackageResetEffect(args: UseReplayPackageResetEffectArgs) {
  useEffect(() => {
    if (!args.replayPackageEnabled) return;
    resetReplayPackageState(args);
  }, [
    args.replayPackageEnabled,
    args.seriesId,
    args.setReplayCandle,
    args.setReplayDrawInstructions,
    args.setReplayFocusTime,
    args.setReplayFrame,
    args.setReplayIndex,
    args.setReplayPlaying,
    args.setReplaySlices,
    args.setReplayTotal
  ]);
}

export function useReplayFocusSyncEffect(args: Parameters<typeof syncReplayFocusFromIndex>[0]) {
  useEffect(() => {
    syncReplayFocusFromIndex(args);
  }, [
    args.applyReplayOverlayAtTime,
    args.fetchAndApplyAnchorHighlightAtTime,
    args.replayEnabled,
    args.replayIndex,
    args.replayPackageEnabled,
    args.replayTotal,
    args.requestReplayFrameAtTime,
    args.setReplayFocusTime,
    args.setReplayIndex
  ]);
}
