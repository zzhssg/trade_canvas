import type { MutableRefObject, RefCallback } from "react";

import type { IChartApi, ISeriesApi } from "lightweight-charts";

import { ChartViewOverlayLayer } from "./ChartViewOverlayLayer";
import type { FibInst, PositionInst } from "./draw_tools/types";
import type { DrawMeasureState } from "./draw_tools/useDrawToolState";
import type { LiveLoadStatus } from "./liveSessionRuntimeTypes";

type ChartViewShellProps = {
  wheelGuardRef: MutableRefObject<HTMLDivElement | null>;
  bindContainerRef: RefCallback<HTMLDivElement>;
  seriesId: string;
  candlesLength: number;
  lastCandle: { time: number | string; open: number; high: number; low: number; close: number } | null;
  lastWsCandleTime: number | null;
  chartEpoch: number;
  barSpacing: number | null;
  pivotCount: number;
  penPointCount: number;
  zhongshuCount: number;
  anchorCount: number;
  anchorSwitchCount: number;
  enableAnchorTopLayer: boolean;
  anchorTopLayerPathCount: number;
  replayEnabled: boolean;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  replayPlaying: boolean;
  error: string | null;
  replayMaskX: number | null;
  enableDrawTools: boolean;
  activeChartTool: string;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  candleTimesSec: number[];
  measureState: DrawMeasureState;
  positionTools: PositionInst[];
  fibTools: FibInst[];
  fibPreviewTool: FibInst | null;
  activeToolId: string | null;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  onUpdatePositionTool: (id: string, updates: Partial<PositionInst>) => void;
  onRemovePositionTool: (id: string) => void;
  onUpdateFibTool: (id: string, updates: Partial<FibInst>) => void;
  onRemoveFibTool: (id: string) => void;
  onSelectTool: (id: string | null) => void;
  onInteractionLockChange: (locked: boolean) => void;
  liveLoadStatus: LiveLoadStatus;
  liveLoadMessage: string;
  toastMessage: string | null;
};

export function ChartViewShell(props: ChartViewShellProps) {
  return (
    <div
      ref={props.wheelGuardRef}
      data-testid="chart-view"
      data-series-id={props.seriesId}
      data-candles-len={String(props.candlesLength)}
      data-last-time={props.lastCandle ? String(props.lastCandle.time) : ""}
      data-last-open={props.lastCandle ? String(props.lastCandle.open) : ""}
      data-last-high={props.lastCandle ? String(props.lastCandle.high) : ""}
      data-last-low={props.lastCandle ? String(props.lastCandle.low) : ""}
      data-last-close={props.lastCandle ? String(props.lastCandle.close) : ""}
      data-last-ws-candle-time={props.lastWsCandleTime != null ? String(props.lastWsCandleTime) : ""}
      data-chart-epoch={String(props.chartEpoch)}
      data-bar-spacing={props.barSpacing != null ? String(props.barSpacing) : ""}
      data-pivot-count={String(props.pivotCount)}
      data-pen-point-count={String(props.penPointCount)}
      data-zhongshu-count={String(props.zhongshuCount)}
      data-anchor-count={String(props.anchorCount)}
      data-anchor-switch-count={String(props.anchorSwitchCount)}
      data-anchor-on={props.anchorCount > 0 ? "1" : "0"}
      data-anchor-top-layer={props.enableAnchorTopLayer ? "1" : "0"}
      data-anchor-top-layer-path-count={String(props.anchorTopLayerPathCount)}
      data-replay-mode={props.replayEnabled ? "replay" : "live"}
      data-replay-index={String(props.replayIndex)}
      data-replay-total={String(props.replayTotal)}
      data-replay-focus-time={props.replayFocusTime != null ? String(props.replayFocusTime) : ""}
      data-replay-playing={props.replayPlaying ? "1" : "0"}
      data-live-load-status={props.liveLoadStatus}
      data-live-load-message={props.liveLoadMessage}
      className="relative h-full w-full"
      title={props.error ?? undefined}
    >
      <div ref={props.bindContainerRef} className="h-full w-full" />

      <ChartViewOverlayLayer
        replayEnabled={props.replayEnabled}
        replayMaskX={props.replayMaskX}
        enableDrawTools={props.enableDrawTools}
        activeChartTool={props.activeChartTool}
        containerRef={props.containerRef}
        candleTimesSec={props.candleTimesSec}
        measureState={props.measureState}
        positionTools={props.positionTools}
        fibTools={props.fibTools}
        fibPreviewTool={props.fibPreviewTool}
        activeToolId={props.activeToolId}
        chartRef={props.chartRef}
        seriesRef={props.seriesRef}
        onUpdatePositionTool={props.onUpdatePositionTool}
        onRemovePositionTool={props.onRemovePositionTool}
        onUpdateFibTool={props.onUpdateFibTool}
        onRemoveFibTool={props.onRemoveFibTool}
        onSelectTool={props.onSelectTool}
        onInteractionLockChange={props.onInteractionLockChange}
        error={props.error}
        candlesLength={props.candlesLength}
        liveLoadStatus={props.liveLoadStatus}
        liveLoadMessage={props.liveLoadMessage}
        toastMessage={props.toastMessage}
      />
    </div>
  );
}
