import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { resolveTimeFromX, timeToCoordinateContinuous } from "./chartCoord";
import { computeFibLevelPrices, pairFibLevels } from "./fib";
import type { FibInst } from "./types";
import { formatUnixSecondsMdHm } from "../timeFormat";
import { useToolRepaintSync } from "./useToolRepaintSync";

type DragMode = "a" | "b" | "move" | null;
type DragSnapshot = { startMouseTime: number; startMousePrice: number; startA: { time: number; price: number }; startB: { time: number; price: number } };
type LevelCoord = { ratio: number; price: number; y: number };
type Coords = { ax: number; ay: number; bx: number; by: number; containerWidth: number; containerHeight: number; levelCoords: LevelCoord[] };
type FibToolProps = {
  chartRef: React.MutableRefObject<IChartApi | null>; seriesRef: React.MutableRefObject<ISeriesApi<"Candlestick"> | null>; containerRef: React.RefObject<HTMLDivElement | null>;
  candleTimesSec: number[]; tool: FibInst; isActive: boolean; interactive: boolean; onUpdate: (id: string, updates: Partial<FibInst>) => void;
  onRemove: (id: string) => void; onSelect: (id: string | null) => void; onInteractionLockChange?: (locked: boolean) => void;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const approx = (a: number, b: number, eps = 1e-6) => Math.abs(a - b) <= eps;
const formatRatio = (ratio: number) => (Number.isFinite(Number(ratio)) ? Number(ratio).toFixed(3).replace(/0+$/, "").replace(/\.$/, "") : "--");
const formatPrice = (price: number) => {
  const p = Number(price);
  if (!Number.isFinite(p)) return "--";
  const abs = Math.abs(p);
  return p.toFixed(abs >= 1000 ? 2 : abs >= 1 ? 4 : 6);
};

export function FibTool({ chartRef, seriesRef, containerRef, candleTimesSec, tool, isActive, interactive, onUpdate, onRemove, onSelect, onInteractionLockChange }: FibToolProps) {
  const [dragMode, setDragMode] = useState<DragMode>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);
  const [lastGoodCoords, setLastGoodCoords] = useState<Coords | null>(null);
  const dragStartRef = useRef<DragSnapshot | null>(null);

  const resolveTime = useCallback((x: number) => {
    const chart = chartRef.current;
    return chart ? resolveTimeFromX({ chart, x, candleTimesSec }) : null;
  }, [candleTimesSec, chartRef]);

  const levelPrices = useMemo(() => computeFibLevelPrices({ priceA: tool.anchors.a.price, priceB: tool.anchors.b.price, levels: tool.settings.levels }), [tool.anchors.a.price, tool.anchors.b.price, tool.settings.levels]);
  const bandPairs = useMemo(() => pairFibLevels(levelPrices), [levelPrices]);
  const showLabels = tool.settings.showLabels ?? true;

  const getCoordinates = useCallback((): Coords | null => {
    const chart = chartRef.current, series = seriesRef.current, container = containerRef.current;
    if (!chart || !series || !container) return null;
    const timeScale = chart.timeScale();
    const ax = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: tool.anchors.a.time });
    const bx = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: tool.anchors.b.time });
    const ay = series.priceToCoordinate(Number(tool.anchors.a.price)), by = series.priceToCoordinate(Number(tool.anchors.b.price));
    if (ax == null || bx == null || ay == null || by == null) return null;
    const rect = container.getBoundingClientRect();
    const levelCoords = levelPrices.map((lvl) => {
      const y = series.priceToCoordinate(Number(lvl.price));
      return y == null ? null : { ratio: Number(lvl.ratio), price: Number(lvl.price), y: Number(y) };
    }).filter((v): v is LevelCoord => Boolean(v));
    return { ax: Number(ax), ay: Number(ay), bx: Number(bx), by: Number(by), containerWidth: Math.max(1, Number(rect.width)), containerHeight: Math.max(1, Number(rect.height)), levelCoords };
  }, [candleTimesSec, chartRef, containerRef, levelPrices, seriesRef, tool.anchors.a, tool.anchors.b]);

  const repaintTick = useToolRepaintSync({ chartRef, containerRef, candleTimesSec });

  useLayoutEffect(() => {
    const id = window.requestAnimationFrame(() => {
      const next = getCoordinates();
      setCoords(next);
      if (next) setLastGoodCoords(next);
    });
    return () => window.cancelAnimationFrame(id);
  }, [getCoordinates, repaintTick]);

  const lineWidth = useMemo(() => {
    const raw = Number(tool.settings.lineWidth);
    return clamp(Math.round(Number.isFinite(raw) && raw > 0 ? raw : 2), 1, 6);
  }, [tool.settings.lineWidth]);
  const goldenLineWidth = Math.min(6, lineWidth + 1);

  const startDrag = useCallback((mode: Exclude<DragMode, null>, e: React.PointerEvent) => {
    if (!interactive) return;
    const container = containerRef.current, series = seriesRef.current;
    if (!container || !series) return;
    const rect = container.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top;
    const price = series.coordinateToPrice(y), time = resolveTime(x);
    if (price == null || time == null) return;
    dragStartRef.current = {
      startMouseTime: Number(time), startMousePrice: Number(price),
      startA: { time: tool.anchors.a.time, price: tool.anchors.a.price }, startB: { time: tool.anchors.b.time, price: tool.anchors.b.price }
    };
    setDragMode(mode);
    onInteractionLockChange?.(true);
    onSelect(tool.id);
    try { (e.target as HTMLElement | null)?.setPointerCapture?.(e.pointerId); } catch {}
    e.preventDefault();
    e.stopPropagation();
  }, [containerRef, interactive, onInteractionLockChange, onSelect, resolveTime, seriesRef, tool.anchors.a, tool.anchors.b, tool.id]);

  useEffect(() => {
    if (!dragMode) return;
    const handleMove = (e: PointerEvent) => {
      const container = containerRef.current, chart = chartRef.current, series = seriesRef.current;
      if (!container || !chart || !series) return;
      const rect = container.getBoundingClientRect(), x = e.clientX - rect.left, y = e.clientY - rect.top;
      const price = series.coordinateToPrice(y), time = resolveTime(x);
      if (price == null || time == null) return;
      const nextPrice = Number(price), nextTime = Number(time);
      try { chart.setCrosshairPosition(nextPrice, nextTime as never, series); } catch {}
      if (dragMode === "a") return onUpdate(tool.id, { anchors: { ...tool.anchors, a: { time: nextTime, price: nextPrice } } });
      if (dragMode === "b") return onUpdate(tool.id, { anchors: { ...tool.anchors, b: { time: nextTime, price: nextPrice } } });
      const base = dragStartRef.current;
      if (!base) return;
      const dt = nextTime - Number(base.startMouseTime), dp = nextPrice - Number(base.startMousePrice);
      if (!Number.isFinite(dt) || !Number.isFinite(dp)) return;
      onUpdate(tool.id, {
        anchors: {
          a: { time: Math.round(Number(base.startA.time) + dt), price: Number(base.startA.price) + dp },
          b: { time: Math.round(Number(base.startB.time) + dt), price: Number(base.startB.price) + dp }
        }
      });
    };
    const handleUp = () => { setDragMode(null); dragStartRef.current = null; onInteractionLockChange?.(false); };
    window.addEventListener("pointermove", handleMove);
    window.addEventListener("pointerup", handleUp);
    return () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleUp);
    };
  }, [chartRef, containerRef, dragMode, onInteractionLockChange, onUpdate, resolveTime, seriesRef, tool.anchors, tool.id]);

  useEffect(() => {
    if (!interactive || isActive || isHovered || dragMode) return;
    onInteractionLockChange?.(false);
  }, [interactive, isActive, isHovered, dragMode, onInteractionLockChange]);

  const effective = coords ?? lastGoodCoords;
  if (!effective) return null;

  const left = Math.min(effective.ax, effective.bx), width = Math.max(1, Math.abs(effective.bx - effective.ax));
  const dx = Number(effective.bx) - Number(effective.ax), dy = Number(effective.by) - Number(effective.ay);
  const angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI, baseLen = Math.hypot(dx, dy);
  const clampX = (x: number) => (Number.isFinite(effective.containerWidth) && effective.containerWidth > 0 ? clamp(x, 0, effective.containerWidth) : x);
  const clampY = (y: number) => (Number.isFinite(effective.containerHeight) && effective.containerHeight > 0 ? clamp(y, 0, effective.containerHeight) : y);
  const opacity = isActive || isHovered ? 1 : 0.7;

  const bandColors = ["rgba(220, 38, 38, 0.20)", "rgba(249, 115, 22, 0.18)", "rgba(234, 179, 8, 0.16)", "rgba(34, 197, 94, 0.16)", "rgba(14, 165, 233, 0.16)", "rgba(37, 99, 235, 0.16)", "rgba(99, 102, 241, 0.16)"];
  const yByRatio = new Map((effective.levelCoords ?? []).map((x) => [x.ratio, x.y] as const));
  const bandCoords = bandPairs.flatMap(({ from, to }, idx) => {
    const yFrom = yByRatio.get(from.ratio), yTo = yByRatio.get(to.ratio);
    if (yFrom == null || yTo == null) return [];
    return [{ key: `${from.ratio}:${to.ratio}`, top: Math.min(yFrom, yTo), height: Math.max(1, Math.abs(yTo - yFrom)), color: bandColors[idx % bandColors.length]! }];
  });

  const hoverProps = {
    onMouseEnter: () => setIsHovered(true),
    onMouseLeave: () => setIsHovered(false),
    onPointerDown: (e: React.PointerEvent) => startDrag("move", e),
    onClick: (e: React.MouseEvent | React.PointerEvent) => { e.stopPropagation(); onSelect(tool.id); }
  };

  return (
    <div className="absolute inset-0 z-30" style={{ pointerEvents: "none" }}>
      {isActive && interactive ? (
        <div className="absolute flex items-center gap-1 rounded border border-white/10 bg-black/60 px-2 py-1 shadow" style={{ left: clampX(left + width - 10), top: clampY(Math.min(effective.ay, effective.by) - 36), transform: "translateX(-100%)", pointerEvents: "auto" }} onClick={(e) => e.stopPropagation()} onPointerDown={(e) => e.stopPropagation()}>
          {[1, 2, 3, 4].map((w) => (
            <button key={w} type="button" className={["rounded border px-1.5 py-0.5 text-[10px] transition-colors", lineWidth === w ? "border-indigo-400/50 bg-indigo-500/20 text-indigo-200" : "border-white/10 text-white/70 hover:bg-white/10"].join(" ")} onClick={(e) => { e.stopPropagation(); onUpdate(tool.id, { settings: { ...tool.settings, lineWidth: w } }); }} title="线宽">{w}px</button>
          ))}
          <button type="button" className="ml-1 grid h-6 w-6 place-items-center rounded border border-white/10 text-white/70 hover:bg-red-500/20 hover:text-red-200" onClick={(e) => { e.stopPropagation(); onRemove(tool.id); }} title="删除">
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
        </div>
      ) : null}

      {isActive ? ([{ key: "a", x: effective.ax, text: formatUnixSecondsMdHm(tool.anchors.a.time) }, { key: "b", x: effective.bx, text: formatUnixSecondsMdHm(tool.anchors.b.time) }] as const).map((item) => (
        <div key={item.key} className="absolute bottom-1 rounded border border-blue-400/40 bg-blue-600/80 px-2 py-0.5 text-[10px] text-white shadow" style={{ left: clampX(Number(item.x)), transform: "translateX(-50%)", pointerEvents: "none" }}>{item.text}</div>
      )) : null}

      <div className="absolute" style={{ left: effective.ax, top: effective.ay, width: Math.max(1, baseLen), height: 0, borderTop: `${lineWidth}px dashed rgba(148, 163, 184, 0.65)`, transform: `rotate(${angleDeg}deg)`, transformOrigin: "0 0", pointerEvents: interactive ? "auto" : "none", opacity }} {...hoverProps} />

      {bandCoords.map(({ key, top, height, color }) => <div key={key} className="absolute" style={{ left, top, width, height, backgroundColor: color, pointerEvents: interactive ? "auto" : "none", opacity: isActive || isHovered ? 1 : 0.6 }} {...hoverProps} />)}

      {(effective.levelCoords ?? []).map(({ ratio, price, y }) => {
        if (!Number.isFinite(y)) return null;
        const isGolden = approx(ratio, 0.618), color = isGolden ? "rgba(168, 85, 247, 0.95)" : "rgba(148, 163, 184, 0.75)";
        return (
          <div key={String(ratio)}>
            <div className="absolute" style={{ left, top: y, width, height: 0, borderTop: `${isGolden ? goldenLineWidth : lineWidth}px solid ${color}`, pointerEvents: interactive ? "auto" : "none", opacity: isActive || isHovered ? 1 : 0.6 }} {...hoverProps} />
            {showLabels ? <div className="absolute rounded bg-black/70 px-1 py-0.5 text-[10px] text-white/90" style={{ left: left + 4, top: y - 10, pointerEvents: "none" }}>{`${formatRatio(ratio)} · ${formatPrice(price)}`}</div> : null}
          </div>
        );
      })}

      {isActive && interactive ? ([{ key: "a", x: effective.ax, y: effective.ay, mode: "a" as const }, { key: "b", x: effective.bx, y: effective.by, mode: "b" as const }] as const).map((anchor) => (
        <div key={anchor.key} className="absolute h-3 w-3 cursor-move rounded-full border border-purple-500 bg-white shadow" style={{ left: anchor.x - 6, top: anchor.y - 6, pointerEvents: "auto" }} onPointerDown={(e) => startDrag(anchor.mode, e)} />
      )) : null}
    </div>
  );
}
