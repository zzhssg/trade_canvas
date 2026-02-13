import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useEffect, type Dispatch, type MutableRefObject, type SetStateAction } from "react";

import type { ChartToolKey } from "../../state/uiStore";

import {
  bindDrawToolChartClick,
  bindDrawToolHotkeys,
  bindMeasurePointerMove
} from "./draw_tools/drawToolInteractionsRuntime";
import { sortAndDeduplicateTimes } from "./draw_tools/chartCoord";
import type { DrawMeasureState } from "./draw_tools/useDrawToolState";
import type { FibInst, PositionInst, PriceTimePoint } from "./draw_tools/types";
import type { Candle } from "./types";

type UseChartDrawToolEffectsArgs = {
  enableDrawTools: boolean;
  candles: Candle[];
  activeChartTool: ChartToolKey;
  chartEpoch: number;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  candleTimesSecRef: MutableRefObject<number[]>;
  interactionLockRef: MutableRefObject<{ dragging: boolean }>;
  measureStateRef: MutableRefObject<DrawMeasureState>;
  setMeasureState: Dispatch<SetStateAction<DrawMeasureState>>;
  setActiveChartTool: (tool: ChartToolKey) => void;
  activeChartToolRef: MutableRefObject<ChartToolKey>;
  activeToolIdRef: MutableRefObject<string | null>;
  fibAnchorARef: MutableRefObject<PriceTimePoint | null>;
  setFibAnchorA: Dispatch<SetStateAction<PriceTimePoint | null>>;
  setActiveToolId: Dispatch<SetStateAction<string | null>>;
  replayEnabled: boolean;
  findReplayIndexByTime: (timeSec: number) => number | null;
  setReplayIndexAndFocus: (nextIndex: number, opts?: { pause?: boolean }) => void;
  genId: () => string;
  setPositionTools: Dispatch<SetStateAction<PositionInst[]>>;
  selectTool: (id: string | null) => void;
  setFibTools: Dispatch<SetStateAction<FibInst[]>>;
  suppressDeselectUntilRef: MutableRefObject<number>;
};

export function useChartDrawToolEffects(args: UseChartDrawToolEffectsArgs) {
  useEffect(() => {
    args.candleTimesSecRef.current = sortAndDeduplicateTimes(
      args.candles.map((candle) => Number(candle.time)).filter((time) => Number.isFinite(time))
    );
  }, [args.candles]);

  useEffect(() => {
    return bindMeasurePointerMove({
      enabled: args.enableDrawTools,
      activeChartTool: args.activeChartTool,
      containerRef: args.containerRef,
      chartRef: args.chartRef,
      seriesRef: args.seriesRef,
      candleTimesSecRef: args.candleTimesSecRef,
      interactionLockRef: args.interactionLockRef,
      measureStateRef: args.measureStateRef,
      setMeasureState: args.setMeasureState
    });
  }, [args.activeChartTool, args.chartEpoch, args.interactionLockRef, args.measureStateRef, args.seriesRef]);

  useEffect(() => {
    return bindDrawToolHotkeys({
      enabled: args.enableDrawTools,
      setActiveChartTool: args.setActiveChartTool,
      activeChartToolRef: args.activeChartToolRef,
      activeToolIdRef: args.activeToolIdRef,
      fibAnchorARef: args.fibAnchorARef,
      measureStateRef: args.measureStateRef,
      setFibAnchorA: args.setFibAnchorA,
      setMeasureState: args.setMeasureState,
      setActiveToolId: args.setActiveToolId
    });
  }, [
    args.activeChartToolRef,
    args.activeToolIdRef,
    args.fibAnchorARef,
    args.measureStateRef,
    args.setActiveChartTool
  ]);

  useEffect(() => {
    return bindDrawToolChartClick({
      enabled: args.enableDrawTools,
      chartRef: args.chartRef,
      seriesRef: args.seriesRef,
      interactionLockRef: args.interactionLockRef,
      replayEnabled: args.replayEnabled,
      activeChartToolRef: args.activeChartToolRef,
      findReplayIndexByTime: args.findReplayIndexByTime,
      setReplayIndexAndFocus: args.setReplayIndexAndFocus,
      candleTimesSecRef: args.candleTimesSecRef,
      genId: args.genId,
      setPositionTools: args.setPositionTools,
      selectTool: args.selectTool,
      setActiveChartTool: args.setActiveChartTool,
      setFibAnchorA: args.setFibAnchorA,
      fibAnchorARef: args.fibAnchorARef,
      setFibTools: args.setFibTools,
      measureStateRef: args.measureStateRef,
      setMeasureState: args.setMeasureState,
      suppressDeselectUntilRef: args.suppressDeselectUntilRef,
      setActiveToolId: args.setActiveToolId
    });
  }, [
    args.activeChartToolRef,
    args.chartEpoch,
    args.chartRef,
    args.findReplayIndexByTime,
    args.fibAnchorARef,
    args.genId,
    args.interactionLockRef,
    args.measureStateRef,
    args.replayEnabled,
    args.selectTool,
    args.seriesRef,
    args.setActiveChartTool,
    args.setReplayIndexAndFocus,
    args.suppressDeselectUntilRef
  ]);
}
