import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { computeFibLevelPrices, pairFibLevels } from "./fib";
import { resolveTimeFromX, timeToCoordinateContinuous } from "./chartCoord";
import type { FibInst } from "./types";
import { formatUnixSecondsMdHm } from "../timeFormat";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function approx(a: number, b: number, eps = 1e-6): boolean {
  return Math.abs(a - b) <= eps;
}

function formatRatio(ratio: number): string {
  const r = Number(ratio);
  if (!Number.isFinite(r)) return "--";
  return r.toFixed(3).replace(/0+$/, "").replace(/\.$/, "");
}

function formatPrice(price: number): string {
  const p = Number(price);
  if (!Number.isFinite(p)) return "--";
  const abs = Math.abs(p);
  const dp = abs >= 1000 ? 2 : abs >= 1 ? 4 : 6;
  return p.toFixed(dp);
}

type DragMode = "a" | "b" | "move" | null;

export function FibTool({
  chartRef,
  seriesRef,
  containerRef,
  candleTimesSec,
  tool,
  isActive,
  interactive,
  onUpdate,
  onRemove,
  onSelect,
  onInteractionLockChange
}: {
  chartRef: React.MutableRefObject<IChartApi | null>;
  seriesRef: React.MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: React.RefObject<HTMLDivElement | null>;
  candleTimesSec: number[];
  tool: FibInst;
  isActive: boolean;
  interactive: boolean;
  onUpdate: (id: string, updates: Partial<FibInst>) => void;
  onRemove: (id: string) => void;
  onSelect: (id: string | null) => void;
  onInteractionLockChange?: (locked: boolean) => void;
}) {
  const [dragMode, setDragMode] = useState<DragMode>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [updater, setUpdater] = useState(0);
  const rafUpdateIdRef = useRef<number | null>(null);
  const dragStartRef = useRef<{
    startMouseTime: number;
    startMousePrice: number;
    startA: { time: number; price: number };
    startB: { time: number; price: number };
  } | null>(null);

  type Coords = {
    ax: number;
    ay: number;
    bx: number;
    by: number;
    containerWidth: number;
    containerHeight: number;
    levelCoords: Array<{ ratio: number; price: number; y: number }>;
  };
  const [coords, setCoords] = useState<Coords | null>(null);
  const [lastGoodCoords, setLastGoodCoords] = useState<Coords | null>(null);

  const resolveTime = useCallback(
    (x: number): number | null => {
      const chart = chartRef.current;
      if (!chart) return null;
      return resolveTimeFromX({ chart, x, candleTimesSec });
    },
    [candleTimesSec, chartRef]
  );

  const levelPrices = useMemo(() => {
    return computeFibLevelPrices({
      priceA: tool.anchors.a.price,
      priceB: tool.anchors.b.price,
      levels: tool.settings.levels
    });
  }, [tool.anchors.a.price, tool.anchors.b.price, tool.settings.levels]);

  const showLabels = tool.settings.showLabels ?? true;
  const bandPairs = useMemo(() => pairFibLevels(levelPrices), [levelPrices]);

  const getCoordinates = useCallback((): Coords | null => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return null;

    const timeScale = chart.timeScale();
    const ax = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: tool.anchors.a.time });
    const bx = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: tool.anchors.b.time });
    const ay = series.priceToCoordinate(Number(tool.anchors.a.price));
    const by = series.priceToCoordinate(Number(tool.anchors.b.price));
    if (ax == null || bx == null || ay == null || by == null) return null;

    const rect = container.getBoundingClientRect();
    const containerWidth = Math.max(1, Number(rect.width));
    const containerHeight = Math.max(1, Number(rect.height));

    const levelCoords = levelPrices
      .map((lvl) => {
        const y = series.priceToCoordinate(Number(lvl.price));
        if (y == null) return null;
        return { ratio: Number(lvl.ratio), price: Number(lvl.price), y: Number(y) };
      })
      .filter((x): x is { ratio: number; price: number; y: number } => Boolean(x));

    return {
      ax: Number(ax),
      ay: Number(ay),
      bx: Number(bx),
      by: Number(by),
      containerWidth,
      containerHeight,
      levelCoords
    };
  }, [candleTimesSec, chartRef, containerRef, levelPrices, seriesRef, tool.anchors.a, tool.anchors.b]);

  const scheduleUpdate = useCallback(() => {
    if (rafUpdateIdRef.current !== null) return;
    rafUpdateIdRef.current = window.requestAnimationFrame(() => {
      rafUpdateIdRef.current = null;
      setUpdater((v) => v + 1);
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
      if (rafUpdateIdRef.current !== null) {
        window.cancelAnimationFrame(rafUpdateIdRef.current);
        rafUpdateIdRef.current = null;
      }
    };
  }, [chartRef, containerRef, scheduleUpdate]);

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver(() => scheduleUpdate());
    ro.observe(container);
    return () => ro.disconnect();
  }, [containerRef, scheduleUpdate]);

  const firstCandleTime = candleTimesSec[0];
  const lastCandleTime = candleTimesSec[candleTimesSec.length - 1];
  useEffect(() => {
    const id = window.requestAnimationFrame(() => setUpdater((prev) => prev + 1));
    return () => window.cancelAnimationFrame(id);
  }, [candleTimesSec.length, firstCandleTime, lastCandleTime]);

  useLayoutEffect(() => {
    const id = window.requestAnimationFrame(() => {
      const next = getCoordinates();
      setCoords(next);
      if (next) setLastGoodCoords(next);
    });
    return () => window.cancelAnimationFrame(id);
  }, [getCoordinates, updater]);

  const effective = coords ?? lastGoodCoords;

  const lineWidth = useMemo(() => {
    const raw = Number(tool.settings.lineWidth);
    const w = Number.isFinite(raw) && raw > 0 ? raw : 2;
    return clamp(Math.round(w), 1, 6);
  }, [tool.settings.lineWidth]);
  const goldenLineWidth = Math.min(6, Math.max(lineWidth, lineWidth + 1));

  const startDrag = useCallback(
    (mode: Exclude<DragMode, null>, e: React.PointerEvent) => {
      if (!interactive) return;
      const container = containerRef.current;
      const series = seriesRef.current;
      if (!container || !series) return;
      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const price = series.coordinateToPrice(y);
      const time = resolveTime(x);
      if (price == null || time == null) return;

      dragStartRef.current = {
        startMouseTime: Number(time),
        startMousePrice: Number(price),
        startA: { time: tool.anchors.a.time, price: tool.anchors.a.price },
        startB: { time: tool.anchors.b.time, price: tool.anchors.b.price }
      };
      setDragMode(mode);
      onInteractionLockChange?.(true);
      onSelect(tool.id);

      try {
        (e.target as HTMLElement | null)?.setPointerCapture?.(e.pointerId);
      } catch {
        // ignore
      }
      e.preventDefault();
      e.stopPropagation();
    },
    [containerRef, interactive, onInteractionLockChange, onSelect, resolveTime, seriesRef, tool.anchors.a, tool.anchors.b, tool.id]
  );

  useEffect(() => {
    if (!dragMode) return;

    const handleMove = (e: PointerEvent) => {
      const container = containerRef.current;
      const chart = chartRef.current;
      const series = seriesRef.current;
      if (!container || !chart || !series) return;

      const rect = container.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;

      const price = series.coordinateToPrice(y);
      const time = resolveTime(x);
      if (price == null || time == null) return;

      try {
        chart.setCrosshairPosition(Number(price), Number(time) as any, series);
      } catch {
        // ignore
      }

      if (dragMode === "a") {
        onUpdate(tool.id, { anchors: { ...tool.anchors, a: { time: Number(time), price: Number(price) } } });
        return;
      }
      if (dragMode === "b") {
        onUpdate(tool.id, { anchors: { ...tool.anchors, b: { time: Number(time), price: Number(price) } } });
        return;
      }

      const base = dragStartRef.current;
      if (!base) return;
      const dt = Number(time) - Number(base.startMouseTime);
      const dp = Number(price) - Number(base.startMousePrice);
      if (!Number.isFinite(dt) || !Number.isFinite(dp)) return;

      onUpdate(tool.id, {
        anchors: {
          a: { time: Math.round(Number(base.startA.time) + dt), price: Number(base.startA.price) + dp },
          b: { time: Math.round(Number(base.startB.time) + dt), price: Number(base.startB.price) + dp }
        }
      });
    };

    const handleUp = () => {
      setDragMode(null);
      dragStartRef.current = null;
      onInteractionLockChange?.(false);
    };

    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp, { once: true });
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp as EventListener);
    };
  }, [chartRef, containerRef, dragMode, onInteractionLockChange, onUpdate, resolveTime, seriesRef, tool.anchors, tool.id]);

  useEffect(() => {
    if (!interactive) return;
    if (isActive || isHovered || dragMode) return;
    onInteractionLockChange?.(false);
  }, [interactive, isActive, isHovered, dragMode, onInteractionLockChange]);

  if (!effective) return null;

  const left = Math.min(effective.ax, effective.bx);
  const width = Math.max(1, Math.abs(effective.bx - effective.ax));
  const dx = Number(effective.bx) - Number(effective.ax);
  const dy = Number(effective.by) - Number(effective.ay);
  const angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
  const baseLen = Math.hypot(dx, dy);

  const clampX = (x: number): number => {
    const w = Number(effective.containerWidth);
    if (!Number.isFinite(w) || w <= 0) return x;
    return clamp(x, 0, w);
  };
  const clampY = (y: number): number => {
    const h = Number(effective.containerHeight);
    if (!Number.isFinite(h) || h <= 0) return y;
    return clamp(y, 0, h);
  };

  const bandColors = [
    "rgba(220, 38, 38, 0.20)",
    "rgba(249, 115, 22, 0.18)",
    "rgba(234, 179, 8, 0.16)",
    "rgba(34, 197, 94, 0.16)",
    "rgba(14, 165, 233, 0.16)",
    "rgba(37, 99, 235, 0.16)",
    "rgba(99, 102, 241, 0.16)"
  ];

  const levelCoords = effective.levelCoords ?? [];
  const yByRatio = new Map(levelCoords.map((x) => [x.ratio, x.y] as const));
  const bandCoords = bandPairs.flatMap(({ from, to }, idx) => {
    const yFrom = yByRatio.get(from.ratio);
    const yTo = yByRatio.get(to.ratio);
    if (yFrom == null || yTo == null) return [];
    const top = Math.min(yFrom, yTo);
    const height = Math.max(1, Math.abs(yTo - yFrom));
    return [{ key: `${from.ratio}:${to.ratio}`, top, height, color: bandColors[idx % bandColors.length]! }];
  });

  const toolbarTop = clampY(Math.min(effective.ay, effective.by) - 36);
  const toolbarLeft = clampX(left + width - 10);

  const opacity = (isActive || isHovered) ? 1 : 0.7;

  return (
    <div className="absolute inset-0 z-30" style={{ pointerEvents: "none" }}>
      {isActive && interactive ? (
        <div
          className="absolute flex items-center gap-1 rounded border border-white/10 bg-black/60 px-2 py-1 shadow"
          style={{ left: toolbarLeft, top: toolbarTop, transform: "translateX(-100%)", pointerEvents: "auto" }}
          onClick={(e) => e.stopPropagation()}
          onPointerDown={(e) => e.stopPropagation()}
        >
          {[1, 2, 3, 4].map((w) => (
            <button
              key={w}
              type="button"
              className={[
                "rounded border px-1.5 py-0.5 text-[10px] transition-colors",
                lineWidth === w ? "border-indigo-400/50 bg-indigo-500/20 text-indigo-200" : "border-white/10 text-white/70 hover:bg-white/10"
              ].join(" ")}
              onClick={(e) => {
                e.stopPropagation();
                onUpdate(tool.id, { settings: { ...tool.settings, lineWidth: w } });
              }}
              title="线宽"
            >
              {w}px
            </button>
          ))}
          <button
            type="button"
            className="ml-1 grid h-6 w-6 place-items-center rounded border border-white/10 text-white/70 hover:bg-red-500/20 hover:text-red-200"
            onClick={(e) => {
              e.stopPropagation();
              onRemove(tool.id);
            }}
            title="删除"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
              <path d="M7 7l10 10M17 7L7 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
            </svg>
          </button>
        </div>
      ) : null}

      {isActive ? (
        <>
          <div
            className="absolute bottom-1 rounded border border-blue-400/40 bg-blue-600/80 px-2 py-0.5 text-[10px] text-white shadow"
            style={{ left: clampX(Number(effective.ax)), transform: "translateX(-50%)", pointerEvents: "none" }}
          >
            {formatUnixSecondsMdHm(tool.anchors.a.time)}
          </div>
          <div
            className="absolute bottom-1 rounded border border-blue-400/40 bg-blue-600/80 px-2 py-0.5 text-[10px] text-white shadow"
            style={{ left: clampX(Number(effective.bx)), transform: "translateX(-50%)", pointerEvents: "none" }}
          >
            {formatUnixSecondsMdHm(tool.anchors.b.time)}
          </div>
        </>
      ) : null}

      {/* Baseline */}
      <div
        className="absolute"
        style={{
          left: effective.ax,
          top: effective.ay,
          width: Math.max(1, baseLen),
          height: 0,
          borderTop: `${lineWidth}px dashed rgba(148, 163, 184, 0.65)`,
          transform: `rotate(${angleDeg}deg)`,
          transformOrigin: "0 0",
          pointerEvents: interactive ? "auto" : "none",
          opacity
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onPointerDown={(e) => startDrag("move", e)}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(tool.id);
        }}
      />

      {/* Bands */}
      {bandCoords.map(({ key, top, height, color }) => {
        return (
          <div
            key={key}
            className="absolute"
            style={{
              left,
              top,
              width,
              height,
              backgroundColor: color,
              pointerEvents: interactive ? "auto" : "none",
              opacity: (isActive || isHovered) ? 1 : 0.6
            }}
            onMouseEnter={() => setIsHovered(true)}
            onMouseLeave={() => setIsHovered(false)}
            onPointerDown={(e) => startDrag("move", e)}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(tool.id);
            }}
          />
        );
      })}

      {levelCoords.map(({ ratio, price, y }) => {
        if (!Number.isFinite(y)) return null;
        const isGolden = approx(ratio, 0.618);
        const color = isGolden ? "rgba(168, 85, 247, 0.95)" : "rgba(148, 163, 184, 0.75)";
        const borderWidth = isGolden ? goldenLineWidth : lineWidth;
        const label = `${formatRatio(ratio)} · ${formatPrice(price)}`;

        return (
          <div key={String(ratio)}>
            <div
              className="absolute"
              style={{
                left,
                top: y,
                width,
                height: 0,
                borderTop: `${borderWidth}px solid ${color}`,
                pointerEvents: interactive ? "auto" : "none",
                opacity: (isActive || isHovered) ? 1 : 0.6
              }}
              onMouseEnter={() => setIsHovered(true)}
              onMouseLeave={() => setIsHovered(false)}
              onPointerDown={(e) => startDrag("move", e)}
              onClick={(e) => {
                e.stopPropagation();
                onSelect(tool.id);
              }}
            />
            {showLabels ? (
              <div
                className="absolute rounded bg-black/70 px-1 py-0.5 text-[10px] text-white/90"
                style={{ left: left + 4, top: y - 10, pointerEvents: "none" }}
              >
                {label}
              </div>
            ) : null}
          </div>
        );
      })}

      {/* Anchor Handles */}
      {isActive && interactive ? (
        <>
          <div
            className="absolute h-3 w-3 cursor-move rounded-full border border-purple-500 bg-white shadow"
            style={{ left: effective.ax - 6, top: effective.ay - 6, pointerEvents: "auto" }}
            onPointerDown={(e) => startDrag("a", e)}
          />
          <div
            className="absolute h-3 w-3 cursor-move rounded-full border border-purple-500 bg-white shadow"
            style={{ left: effective.bx - 6, top: effective.by - 6, pointerEvents: "auto" }}
            onPointerDown={(e) => startDrag("b", e)}
          />
        </>
      ) : null}
    </div>
  );
}
