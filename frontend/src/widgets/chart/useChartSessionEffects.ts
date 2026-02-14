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
      ...args,
      candles: args.candles,
      series,
      chart: args.chartRef.current
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
      ...args,
      chart
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
