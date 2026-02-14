import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useCallback, type MutableRefObject } from "react";

import type { ChartToolKey } from "../../state/uiStore";

import { useFibPreview } from "./draw_tools/useFibPreview";
import { useDrawToolState } from "./draw_tools/useDrawToolState";
import { useChartDrawToolEffects } from "./useChartDrawToolEffects";
import type { Candle } from "./types";

type UseChartDrawToolRuntimeArgs = {
  enableDrawTools: boolean;
  activeChartTool: ChartToolKey;
  setActiveChartTool: (tool: ChartToolKey) => void;
  seriesId: string;
  candles: Candle[];
  candlesRef: MutableRefObject<Candle[]>;
  candleTimesSecRef: MutableRefObject<number[]>;
  chartEpoch: number;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  replayEnabled: boolean;
  setReplayIndexAndFocus: (nextIndex: number, opts?: { pause?: boolean }) => void;
};

export function useChartDrawToolRuntime(args: UseChartDrawToolRuntimeArgs) {
  const drawToolState = useDrawToolState({
    enableDrawTools: args.enableDrawTools,
    activeChartTool: args.activeChartTool,
    setActiveChartTool: args.setActiveChartTool,
    seriesId: args.seriesId
  });

  const findReplayIndexByTime = useCallback((timeSec: number) => {
    const all = args.candlesRef.current;
    if (all.length === 0) return null;
    let lo = 0;
    let hi = all.length - 1;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      const time = Number(all[mid]!.time);
      if (time === timeSec) return mid;
      if (time < timeSec) lo = mid + 1;
      else hi = mid - 1;
    }
    return Math.max(0, Math.min(all.length - 1, hi));
  }, []);

  const fibPreviewTool = useFibPreview({
    enabled: args.enableDrawTools && args.activeChartTool === "fib" && drawToolState.fibAnchorA != null,
    anchorA: drawToolState.fibAnchorA,
    chartRef: args.chartRef,
    seriesRef: args.seriesRef,
    candleTimesSecRef: args.candleTimesSecRef,
    containerRef: args.containerRef
  });

  useChartDrawToolEffects({
    enableDrawTools: args.enableDrawTools,
    candles: args.candles,
    activeChartTool: args.activeChartTool,
    chartEpoch: args.chartEpoch,
    chartRef: args.chartRef,
    seriesRef: args.seriesRef,
    containerRef: args.containerRef,
    candleTimesSecRef: args.candleTimesSecRef,
    interactionLockRef: drawToolState.interactionLockRef,
    measureStateRef: drawToolState.measureStateRef,
    setMeasureState: drawToolState.setMeasureState,
    setActiveChartTool: args.setActiveChartTool,
    activeChartToolRef: drawToolState.activeChartToolRef,
    activeToolIdRef: drawToolState.activeToolIdRef,
    fibAnchorARef: drawToolState.fibAnchorARef,
    setFibAnchorA: drawToolState.setFibAnchorA,
    setActiveToolId: drawToolState.setActiveToolId,
    replayEnabled: args.replayEnabled,
    findReplayIndexByTime,
    setReplayIndexAndFocus: args.setReplayIndexAndFocus,
    genId: drawToolState.genId,
    setPositionTools: drawToolState.setPositionTools,
    selectTool: drawToolState.selectTool,
    setFibTools: drawToolState.setFibTools,
    suppressDeselectUntilRef: drawToolState.suppressDeselectUntilRef
  });

  return {
    ...drawToolState,
    fibPreviewTool
  };
}
