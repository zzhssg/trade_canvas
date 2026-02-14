import type { MutableRefObject, RefCallback } from "react";

import { ChartViewOverlayLayer, type ChartViewOverlayLayerProps } from "./ChartViewOverlayLayer";

type ChartViewShellProps = ChartViewOverlayLayerProps & {
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
  anchorHighlightPointCount: number;
  anchorHighlightStartTime: number | null;
  anchorHighlightEndTime: number | null;
  anchorHighlightDashed: boolean;
  enableAnchorTopLayer: boolean;
  anchorTopLayerPathCount: number;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  replayPlaying: boolean;
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
      data-anchor-highlight-point-count={String(props.anchorHighlightPointCount)}
      data-anchor-highlight-start-time={props.anchorHighlightStartTime != null ? String(props.anchorHighlightStartTime) : ""}
      data-anchor-highlight-end-time={props.anchorHighlightEndTime != null ? String(props.anchorHighlightEndTime) : ""}
      data-anchor-highlight-dashed={props.anchorHighlightDashed ? "1" : "0"}
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
