import type { UTCTimestamp } from "lightweight-charts";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import { useCallback, useEffect } from "react";

import { CENTER_SCROLL_SELECTOR, chartWheelZoomRatio, normalizeWheelDeltaY } from "../../lib/wheelContract";

type UseChartWheelZoomGuardArgs = {
  wheelGuardRef: MutableRefObject<HTMLDivElement | null>;
  chartRef: MutableRefObject<import("lightweight-charts").IChartApi | null>;
  chartEpoch: number;
  setBarSpacing: Dispatch<SetStateAction<number | null>>;
};

export function useChartWheelZoomGuard(args: UseChartWheelZoomGuardArgs) {
  useEffect(() => {
    const el = args.wheelGuardRef.current;
    if (!el) return;
    let rafId: number | null = null;

    const onWheel = (event: WheelEvent) => {
      const chart = args.chartRef.current;
      if (!chart) return;
      if (event.deltaY === 0) return;

      const center = el.closest(CENTER_SCROLL_SELECTOR) as HTMLElement | null;
      if (center) {
        const overflowY = window.getComputedStyle(center).overflowY;
        if (overflowY !== "hidden") {
          event.stopPropagation();
          return;
        }
      }

      event.preventDefault();
      const ratio = chartWheelZoomRatio(normalizeWheelDeltaY(event));
      if (!ratio) return;
      const timeScale = chart.timeScale();
      const before = timeScale.options().barSpacing;
      if (rafId != null) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        const after = timeScale.options().barSpacing;
        if (after !== before) {
          args.setBarSpacing((prev) => (prev === after ? prev : after));
          return;
        }
        const next = Math.max(0.5, before * ratio);
        if (!Number.isFinite(next) || next === before) return;
        chart.applyOptions({ timeScale: { barSpacing: next } });
        args.setBarSpacing((prev) => (prev === next ? prev : next));
      });
    };

    el.addEventListener("wheel", onWheel, { passive: false, capture: true });
    return () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      el.removeEventListener("wheel", onWheel as EventListener, { capture: true });
    };
  }, [args.chartEpoch]);
}

type UseReplayViewportEffectsArgs = {
  replayEnabled: boolean;
  replayFocusTime: number | null;
  width?: number;
  height?: number;
  chartEpoch: number;
  chartRef: MutableRefObject<import("lightweight-charts").IChartApi | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  setReplayMaskX: Dispatch<SetStateAction<number | null>>;
  setBarSpacing: Dispatch<SetStateAction<number | null>>;
};

export function useReplayViewportEffects(args: UseReplayViewportEffectsArgs) {
  const updateReplayMask = useCallback(() => {
    if (!args.replayEnabled || args.replayFocusTime == null) {
      args.setReplayMaskX(null);
      return;
    }
    const chart = args.chartRef.current;
    if (!chart) return;
    const coord = chart.timeScale().timeToCoordinate(args.replayFocusTime as UTCTimestamp);
    if (coord == null || Number.isNaN(coord)) {
      args.setReplayMaskX(null);
      return;
    }
    const widthPx = args.containerRef.current?.clientWidth ?? null;
    const clamped = widthPx != null ? Math.max(0, Math.min(coord, widthPx)) : coord;
    args.setReplayMaskX(clamped);
  }, [args.replayEnabled, args.replayFocusTime]);

  useEffect(() => {
    updateReplayMask();
  }, [args.height, args.replayEnabled, args.replayFocusTime, updateReplayMask, args.width]);

  useEffect(() => {
    const chart = args.chartRef.current;
    if (!chart) return;
    const timeScale = chart.timeScale();

    const update = () => {
      const spacing = timeScale.options().barSpacing;
      args.setBarSpacing((prev) => (prev === spacing ? prev : spacing));
      updateReplayMask();
    };

    const handler = () => update();
    timeScale.subscribeVisibleLogicalRangeChange(handler);
    return () => timeScale.unsubscribeVisibleLogicalRangeChange(handler);
  }, [args.chartEpoch, updateReplayMask]);
}
