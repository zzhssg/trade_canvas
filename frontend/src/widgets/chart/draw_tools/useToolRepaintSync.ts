import type { IChartApi } from "lightweight-charts";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { MutableRefObject, RefObject } from "react";

type UseToolRepaintSyncArgs = {
  chartRef: MutableRefObject<IChartApi | null>;
  containerRef: RefObject<HTMLDivElement | null>;
  candleTimesSec: number[];
};

export function useToolRepaintSync({ chartRef, containerRef, candleTimesSec }: UseToolRepaintSyncArgs): number {
  const [tick, setTick] = useState(0);
  const rafUpdateIdRef = useRef<number | null>(null);

  const scheduleUpdate = useCallback(() => {
    if (rafUpdateIdRef.current != null) return;
    rafUpdateIdRef.current = window.requestAnimationFrame(() => {
      rafUpdateIdRef.current = null;
      setTick((value) => value + 1);
    });
  }, []);

  useLayoutEffect(() => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart) return;
    const timeScale = chart.timeScale();

    timeScale.subscribeVisibleLogicalRangeChange(scheduleUpdate);
    timeScale.subscribeVisibleTimeRangeChange(scheduleUpdate);
    container?.addEventListener("pointermove", scheduleUpdate, { passive: true });
    container?.addEventListener("wheel", scheduleUpdate, { passive: true });

    return () => {
      timeScale.unsubscribeVisibleLogicalRangeChange(scheduleUpdate);
      timeScale.unsubscribeVisibleTimeRangeChange(scheduleUpdate);
      container?.removeEventListener("pointermove", scheduleUpdate);
      container?.removeEventListener("wheel", scheduleUpdate);
      if (rafUpdateIdRef.current != null) {
        window.cancelAnimationFrame(rafUpdateIdRef.current);
        rafUpdateIdRef.current = null;
      }
    };
  }, [chartRef, containerRef, scheduleUpdate]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const observer = new ResizeObserver(scheduleUpdate);
    observer.observe(container);
    return () => observer.disconnect();
  }, [containerRef, scheduleUpdate]);

  const firstCandleTime = candleTimesSec[0];
  const lastCandleTime = candleTimesSec[candleTimesSec.length - 1];
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setTick((value) => value + 1));
    return () => window.cancelAnimationFrame(id);
  }, [candleTimesSec.length, firstCandleTime, lastCandleTime]);

  return tick;
}
