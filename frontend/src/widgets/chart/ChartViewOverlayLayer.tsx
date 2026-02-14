import type { MutableRefObject } from "react";

import type { IChartApi, ISeriesApi } from "lightweight-charts";

import { FibTool } from "./draw_tools/FibTool";
import { MeasureTool } from "./draw_tools/MeasureTool";
import { PositionTool } from "./draw_tools/PositionTool";
import type { FibInst, PositionInst } from "./draw_tools/types";
import type { DrawMeasureState } from "./draw_tools/useDrawToolState";
import type { LiveLoadStatus } from "./liveSessionRuntimeTypes";

export type ChartViewOverlayLayerProps = {
  replayEnabled: boolean;
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
  error: string | null;
  candlesLength: number;
  liveLoadStatus: LiveLoadStatus;
  liveLoadMessage: string;
  toastMessage: string | null;
};

export function ChartViewOverlayLayer(props: ChartViewOverlayLayerProps) {
  const noop = () => {};
  const showReplayLoading = props.replayEnabled && props.candlesLength === 0;
  const showLoadingMask =
    showReplayLoading ||
    props.liveLoadStatus === "loading" ||
    props.liveLoadStatus === "backfilling" ||
    (props.liveLoadStatus === "idle" && props.candlesLength === 0);
  const showEmptyHint = props.liveLoadStatus === "empty" && props.candlesLength === 0;
  const loadingMessage = showReplayLoading ? "正在加载回放K线..." : props.liveLoadMessage;

  return (
    <>
      {props.replayEnabled && props.replayMaskX != null ? (
        <>
          <div
            data-testid="replay-mask"
            className="pointer-events-none absolute inset-y-0 right-0 z-10 bg-black/55"
            style={{ left: `${props.replayMaskX}px` }}
          />
          <div
            className="pointer-events-none absolute inset-y-0 z-20 w-px bg-amber-300/70"
            style={{ left: `${props.replayMaskX}px` }}
          />
        </>
      ) : null}

      {props.enableDrawTools ? (
        <div className="pointer-events-none absolute inset-0 z-30">
          <MeasureTool
            enabled={props.activeChartTool === "measure"}
            containerRef={props.containerRef}
            candleTimesSec={props.candleTimesSec}
            startPoint={props.measureState.start}
            currentPoint={props.measureState.current}
            locked={props.measureState.locked}
          />

          {props.positionTools.map((tool) => (
            <PositionTool
              key={tool.id}
              chartRef={props.chartRef}
              seriesRef={props.seriesRef}
              containerRef={props.containerRef}
              candleTimesSec={props.candleTimesSec}
              tool={tool}
              isActive={props.activeToolId === tool.id}
              interactive={true}
              onUpdate={props.onUpdatePositionTool}
              onRemove={props.onRemovePositionTool}
              onSelect={props.onSelectTool}
              onInteractionLockChange={props.onInteractionLockChange}
            />
          ))}

          {props.fibTools.map((tool) => (
            <FibTool
              key={tool.id}
              chartRef={props.chartRef}
              seriesRef={props.seriesRef}
              containerRef={props.containerRef}
              candleTimesSec={props.candleTimesSec}
              tool={tool}
              isActive={props.activeToolId === tool.id}
              interactive={true}
              onUpdate={props.onUpdateFibTool}
              onRemove={props.onRemoveFibTool}
              onSelect={props.onSelectTool}
              onInteractionLockChange={props.onInteractionLockChange}
            />
          ))}

          {props.fibPreviewTool ? (
            <FibTool
              key="__fib_preview__"
              chartRef={props.chartRef}
              seriesRef={props.seriesRef}
              containerRef={props.containerRef}
              candleTimesSec={props.candleTimesSec}
              tool={props.fibPreviewTool}
              isActive={false}
              interactive={false}
              onUpdate={noop}
              onRemove={noop}
              onSelect={noop}
            />
          ) : null}
        </div>
      ) : null}

      {props.error ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-red-500/30 bg-red-950/60 px-2 py-1 text-[11px] text-red-200">
          {props.error}
        </div>
      ) : showLoadingMask ? (
        <div className="pointer-events-none absolute inset-0 z-40 grid place-items-center bg-black/35">
          <div className="flex items-center gap-2 rounded-md border border-white/15 bg-black/60 px-3 py-2 text-[12px] text-white/80 backdrop-blur">
            <span className="inline-block size-2 animate-pulse rounded-full bg-sky-300" />
            <span>{loadingMessage}</span>
          </div>
        </div>
      ) : showEmptyHint ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-amber-300/30 bg-amber-950/45 px-2 py-1 text-[11px] text-amber-100">
          {props.liveLoadMessage}
        </div>
      ) : null}

      {props.toastMessage ? (
        <div className="pointer-events-none absolute left-1/2 top-3 z-40 -translate-x-1/2 rounded-md border border-amber-300/35 bg-amber-500/15 px-3 py-1.5 text-[12px] text-amber-100 shadow-[0_6px_24px_rgba(0,0,0,0.35)]">
          {props.toastMessage}
        </div>
      ) : null}
    </>
  );
}
