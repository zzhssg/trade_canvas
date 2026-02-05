import { useCallback, useEffect, useMemo, useState } from "react";

import type { PriceTimePoint } from "./types";
import { estimateTimeStep } from "./chartCoord";

export type MeasurePoint = PriceTimePoint & { x: number; y: number };

type MeasureResult = {
  priceDiff: number;
  pricePct: number;
  candleCount: number;
  timeDiff: string;
  startPrice: number;
  endPrice: number;
};

function formatTimeDiff(seconds: number): string {
  const s = Math.max(0, Math.floor(Number(seconds)));
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const parts: string[] = [];
  if (days > 0) parts.push(`${days}天`);
  if (hours > 0) parts.push(`${hours}小时`);
  if (minutes > 0 || parts.length === 0) parts.push(`${minutes}分钟`);
  return parts.join(" ");
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function formatSigned(num: number, dp = 2): string {
  const n = Number(num);
  if (!Number.isFinite(n)) return "--";
  const sign = n >= 0 ? "+" : "";
  return `${sign}${n.toFixed(dp)}`;
}

export function MeasureTool({
  enabled,
  containerRef,
  candleTimesSec,
  startPoint,
  currentPoint,
  locked
}: {
  enabled: boolean;
  containerRef: React.RefObject<HTMLDivElement | null>;
  candleTimesSec: number[];
  startPoint: MeasurePoint | null;
  currentPoint: MeasurePoint | null;
  locked: boolean;
}) {
  const [containerHeight, setContainerHeight] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const update = () => {
      setContainerHeight(container.getBoundingClientRect().height);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(container);
    return () => ro.disconnect();
  }, [containerRef]);

  const result = useMemo((): MeasureResult | null => {
    if (!startPoint || !currentPoint) return null;
    const priceDiff = Number(currentPoint.price) - Number(startPoint.price);
    const pricePct = startPoint.price === 0 ? 0 : (priceDiff / Number(startPoint.price)) * 100;

    const minTime = Math.min(startPoint.time, currentPoint.time);
    const maxTime = Math.max(startPoint.time, currentPoint.time);
    let candleCount = 0;
    if (candleTimesSec.length > 0) {
      const startIdx = candleTimesSec.findIndex((t) => t >= minTime);
      const endIdx = candleTimesSec.findIndex((t) => t >= maxTime);
      if (startIdx >= 0 && endIdx >= 0) {
        candleCount = Math.abs(endIdx - startIdx);
      } else {
        const step = estimateTimeStep(candleTimesSec);
        candleCount = Math.max(0, Math.round((maxTime - minTime) / step));
      }
    }

    const timeDiffSec = Math.abs(currentPoint.time - startPoint.time);
    return {
      priceDiff,
      pricePct,
      candleCount,
      timeDiff: formatTimeDiff(timeDiffSec),
      startPrice: Number(startPoint.price),
      endPrice: Number(currentPoint.price)
    };
  }, [candleTimesSec, currentPoint, startPoint]);

  const displayEnd = currentPoint;
  const showOverlay = enabled && startPoint && displayEnd && result;

  const getLabelPosition = useCallback(() => {
    if (!startPoint || !displayEnd || containerHeight <= 0) {
      return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" } as const;
    }

    const labelHeight = 100;
    const labelPadding = 8;
    const boxTop = Math.min(startPoint.y, displayEnd.y);
    const boxBottom = Math.max(startPoint.y, displayEnd.y);
    const boxWidth = Math.abs(displayEnd.x - startPoint.x);
    const isGoingUp = displayEnd.price > startPoint.price;

    if (isGoingUp) {
      if (boxTop > labelHeight + labelPadding) {
        return { top: `-${labelPadding}px`, left: `${boxWidth / 2}px`, transform: "translate(-50%, -100%)" } as const;
      }
    } else {
      if (containerHeight - boxBottom > labelHeight + labelPadding) {
        return { top: `calc(100% + ${labelPadding}px)`, left: `${boxWidth / 2}px`, transform: "translate(-50%, 0)" } as const;
      }
    }

    if (isGoingUp) {
      if (containerHeight - boxBottom > labelHeight + labelPadding) {
        return { top: `calc(100% + ${labelPadding}px)`, left: `${boxWidth / 2}px`, transform: "translate(-50%, 0)" } as const;
      }
    } else {
      if (boxTop > labelHeight + labelPadding) {
        return { top: `-${labelPadding}px`, left: `${boxWidth / 2}px`, transform: "translate(-50%, -100%)" } as const;
      }
    }

    return { top: "50%", left: "50%", transform: "translate(-50%, -50%)" } as const;
  }, [containerHeight, displayEnd, startPoint]);

  if (!showOverlay || !result) return null;

  const labelStyle = getLabelPosition();
  const left = Math.min(startPoint!.x, displayEnd!.x);
  const top = Math.min(startPoint!.y, displayEnd!.y);
  const width = Math.max(Math.abs(displayEnd!.x - startPoint!.x), 1);
  const height = Math.max(Math.abs(displayEnd!.y - startPoint!.y), 1);
  const positive = result.pricePct >= 0;

  const borderColor = positive ? "rgba(34,197,94,0.85)" : "rgba(239,68,68,0.85)";
  const bgColor = positive ? "rgba(34,197,94,0.18)" : "rgba(239,68,68,0.18)";

  return (
    <div
      className="absolute pointer-events-none z-30"
      style={{
        left,
        top,
        width,
        height
      }}
    >
      <div
        className="absolute inset-0 border-2"
        style={{
          borderColor,
          backgroundColor: bgColor,
          borderStyle: locked ? "solid" : "dashed"
        }}
      />

      <div
        className="absolute rounded-lg border border-white/10 bg-black/80 p-2 text-xs shadow-lg"
        style={{
          ...labelStyle,
          minWidth: "130px"
        }}
      >
        <div className={["mb-1 text-center text-base font-bold", positive ? "text-green-400" : "text-red-400"].join(" ")}>
          {formatSigned(result.pricePct, 2)}%
        </div>
        <div className="space-y-0.5 text-white/70">
          <div className="flex justify-between gap-3">
            <span>价差:</span>
            <span className={positive ? "text-green-400" : "text-red-400"}>{formatSigned(result.priceDiff, 2)}</span>
          </div>
          <div className="flex justify-between gap-3">
            <span>K线:</span>
            <span className="text-white/90">{clamp(result.candleCount, 0, 1_000_000)} 根</span>
          </div>
          <div className="flex justify-between gap-3">
            <span>时间:</span>
            <span className="text-white/90">{result.timeDiff}</span>
          </div>
        </div>
        {locked ? (
          <div className="mt-1.5 border-t border-white/10 pt-1.5 text-center text-[10px] text-white/50">点击清除</div>
        ) : null}
      </div>
    </div>
  );
}

