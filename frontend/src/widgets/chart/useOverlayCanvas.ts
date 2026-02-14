import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useEffect, useRef, type MutableRefObject } from "react";
import {
  drawAnchorTopLayer,
  drawZhongshuRects,
  ensureCanvas,
  type OverlayCanvasPath,
  type PenLinePoint,
  resizeCanvas,
  subscribeChartRedraw
} from "./overlayCanvasRuntime";
import type { OverlayInstructionPatchItemV1 } from "./types";

export type { OverlayCanvasPath };

type CanvasLayerParams = {
  enabled: boolean;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  canvasRef: MutableRefObject<HTMLCanvasElement | null>;
  zIndex: number;
  deps: readonly unknown[];
  paint: (ctx: CanvasRenderingContext2D, chart: IChartApi, series: ISeriesApi<"Candlestick">) => void;
};

function useCanvasLayer({ enabled, chartRef, seriesRef, containerRef, canvasRef, zIndex, deps, paint }: CanvasLayerParams) {
  useEffect(() => {
    if (!enabled) return;
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;
    const draw = () => {
      const canvas = ensureCanvas(canvasRef.current, container, zIndex);
      canvasRef.current = canvas;
      const ctx = resizeCanvas(canvas, container);
      if (!ctx) return;
      ctx.clearRect(0, 0, container.clientWidth, container.clientHeight);
      paint(ctx, chart, series);
    };
    return subscribeChartRedraw(chart, container, draw);
  }, [enabled, chartRef, seriesRef, containerRef, canvasRef, zIndex, paint, ...deps]);
}

export type UseOverlayCanvasParams = {
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  anchorTopLayerPathsRef: MutableRefObject<OverlayCanvasPath[]>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  effectiveVisible: (key: string) => boolean;
  chartEpoch: number;
  overlayPaintEpoch: number;
  anchorHighlightEpoch: number;
  enableAnchorTopLayer: boolean;
};

export function useOverlayCanvas(params: UseOverlayCanvasParams) {
  const zhongshuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const anchorCanvasRef = useRef<HTMLCanvasElement | null>(null);

  useCanvasLayer({
    enabled: true,
    chartRef: params.chartRef,
    seriesRef: params.seriesRef,
    containerRef: params.containerRef,
    canvasRef: zhongshuCanvasRef,
    zIndex: 5,
    deps: [params.chartEpoch, params.overlayPaintEpoch, params.effectiveVisible],
    paint: (ctx, chart, series) =>
      drawZhongshuRects(ctx, chart, series, params.overlayActiveIdsRef.current, params.overlayCatalogRef.current, params.effectiveVisible)
  });

  useCanvasLayer({
    enabled: params.enableAnchorTopLayer,
    chartRef: params.chartRef,
    seriesRef: params.seriesRef,
    containerRef: params.containerRef,
    canvasRef: anchorCanvasRef,
    zIndex: 8,
    deps: [params.chartEpoch, params.overlayPaintEpoch, params.anchorHighlightEpoch, params.effectiveVisible],
    paint: (ctx, chart, series) =>
      drawAnchorTopLayer(
        ctx,
        chart,
        series,
        params.anchorTopLayerPathsRef.current,
        params.anchorPenPointsRef.current,
        params.anchorPenIsDashedRef.current,
        params.effectiveVisible
      )
  });

  return {
    cleanupCanvases: () => {
      for (const ref of [zhongshuCanvasRef, anchorCanvasRef]) {
        const canvas = ref.current;
        if (canvas?.parentElement) canvas.parentElement.removeChild(canvas);
        ref.current = null;
      }
    }
  };
}
