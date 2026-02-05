import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useEffect, useRef, useState } from "react";

import type { FibInst, PriceTimePoint } from "./types";
import { resolveTimeFromX } from "./chartCoord";

export function useFibPreview(params: {
  enabled: boolean;
  anchorA: PriceTimePoint | null;
  chartRef: React.MutableRefObject<IChartApi | null>;
  seriesRef: React.MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  candleTimesSecRef: React.MutableRefObject<number[]>;
  containerRef: React.RefObject<HTMLDivElement | null>;
}): FibInst | null {
  const { enabled, anchorA, chartRef, seriesRef, candleTimesSecRef, containerRef } = params;
  const [previewTool, setPreviewTool] = useState<FibInst | null>(null);

  const rafIdRef = useRef<number | null>(null);
  const lastPointRef = useRef<PriceTimePoint | null>(null);
  const lastMouseRef = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    if (!enabled || !anchorA) {
      lastPointRef.current = null;
      lastMouseRef.current = null;
      setPreviewTool(null);
      return;
    }
    const container = containerRef.current;
    if (!container) return;

    const schedule = () => {
      if (rafIdRef.current != null) return;
      rafIdRef.current = window.requestAnimationFrame(() => {
        rafIdRef.current = null;
        const chart = chartRef.current;
        const series = seriesRef.current;
        const mouse = lastMouseRef.current;
        if (!chart || !series || !mouse) return;

        const time = resolveTimeFromX({ chart, x: Number(mouse.x), candleTimesSec: candleTimesSecRef.current });
        const price = series.coordinateToPrice(Number(mouse.y));
        if (time == null || price == null) return;
        if (!Number.isFinite(time) || !Number.isFinite(Number(price))) return;

        const nextPoint: PriceTimePoint = { time: Number(time), price: Number(price) };
        const prev = lastPointRef.current;
        if (prev && prev.time === nextPoint.time && Math.abs(prev.price - nextPoint.price) < 1e-6) return;
        lastPointRef.current = nextPoint;

        setPreviewTool({
          id: "__fib_preview__",
          type: "fib_retracement",
          anchors: { a: anchorA, b: nextPoint },
          settings: {}
        });
      });
    };

    const onMove = (e: PointerEvent) => {
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;
      lastMouseRef.current = { x, y };
      schedule();
    };

    const onLeave = () => {
      setPreviewTool(null);
      lastMouseRef.current = null;
      lastPointRef.current = null;
    };

    container.addEventListener("pointermove", onMove, { passive: true });
    container.addEventListener("pointerleave", onLeave, { passive: true });
    return () => {
      container.removeEventListener("pointermove", onMove as EventListener);
      container.removeEventListener("pointerleave", onLeave as EventListener);
      if (rafIdRef.current != null) {
        window.cancelAnimationFrame(rafIdRef.current);
        rafIdRef.current = null;
      }
    };
  }, [anchorA, candleTimesSecRef, chartRef, containerRef, enabled, seriesRef]);

  if (!enabled || !anchorA || !previewTool) return null;
  const sameAnchor =
    previewTool.anchors.a.time === anchorA.time && Math.abs(previewTool.anchors.a.price - anchorA.price) < 1e-12;
  return sameAnchor ? previewTool : null;
}

