import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useEffect, type MutableRefObject } from "react";
import { syncCandlesToSeries, syncOverlayLayers, type SyncCandlesToSeriesArgs, type SyncOverlayLayersArgs } from "./seriesSyncRuntime";
import type { Candle } from "./types";
export {
  useChartLiveSessionEffect,
  useReplayFocusSyncEffect,
  useReplayPackageResetEffect
} from "./chartReplaySessionEffects";

type UseChartSeriesSyncEffectsArgs = Omit<SyncCandlesToSeriesArgs, "candles" | "series" | "chart"> &
  Omit<SyncOverlayLayersArgs, "chart"> & {
  candles: Candle[];
  chartEpoch: number;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
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
