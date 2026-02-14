import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { estimateTimeStep, getBarSpacingPx, resolveTimeFromX, timeToCoordinateContinuous } from "./chartCoord";
import type { PositionInst } from "./types";
import { useToolRepaintSync } from "./useToolRepaintSync";

type DragMode = "entry" | "tp" | "sl" | "move" | "width" | null;
type ToolCoords = { x0: number; x1: number; entryY: number; tpY: number; slY: number };
type DragSnapshot = {
  startMouseX: number; startMouseY: number; startMouseTime: number; startMousePrice: number;
  startEntryTime: number; startSpanSeconds: number; startEntryPrice: number; startTpPrice: number; startSlPrice: number;
};
type PositionToolProps = {
  chartRef: React.MutableRefObject<IChartApi | null>; seriesRef: React.MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: React.RefObject<HTMLDivElement | null>; candleTimesSec: number[]; tool: PositionInst;
  isActive: boolean; interactive: boolean; onUpdate: (id: string, updates: Partial<PositionInst>) => void;
  onRemove: (id: string) => void; onSelect: (id: string | null) => void; onInteractionLockChange?: (locked: boolean) => void;
};

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));
const formatPrice = (price: number) => {
  const p = Number(price);
  if (!Number.isFinite(p)) return "--";
  const abs = Math.abs(p);
  return p.toFixed(abs >= 1000 ? 2 : abs >= 1 ? 4 : 6);
};

export function PositionTool({ chartRef, seriesRef, containerRef, candleTimesSec, tool, isActive, interactive, onUpdate, onRemove, onSelect, onInteractionLockChange }: PositionToolProps) {
  const [isDragging, setIsDragging] = useState<DragMode>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [coords, setCoords] = useState<ToolCoords | null>(null);
  const [lastGoodCoords, setLastGoodCoords] = useState<ToolCoords | null>(null);
  const dragStartRef = useRef<DragSnapshot | null>(null);
  const { entry, stopLoss, takeProfit } = tool.coordinates;
  const { riskAmount, quantity } = tool.settings;
  const { profitColor = "rgba(8, 153, 129, 0.20)", lossColor = "rgba(242, 54, 69, 0.20)" } = tool.settings.colorSettings || {};

  const stepSec = useMemo(() => estimateTimeStep(candleTimesSec), [candleTimesSec]);
  const timeSpanSeconds = useMemo(() => {
    const sec = tool.settings.timeSpanSeconds;
    return typeof sec === "number" && Number.isFinite(sec) && sec > 0 ? sec : 20 * stepSec;
  }, [stepSec, tool.settings.timeSpanSeconds]);

  const metrics = useMemo(() => {
    const entryPrice = Number(entry.price), tpPrice = Number(takeProfit.price), slPrice = Number(stopLoss.price);
    const riskDiff = Math.abs(entryPrice - slPrice), rewardDiff = Math.abs(tpPrice - entryPrice);
    return {
      ratio: (riskDiff === 0 ? 0 : rewardDiff / riskDiff).toFixed(2),
      rewardPct: (entryPrice === 0 ? 0 : (rewardDiff / entryPrice) * 100).toFixed(2),
      riskPct: (entryPrice === 0 ? 0 : (riskDiff / entryPrice) * 100).toFixed(2),
      tpPrice: formatPrice(tpPrice),
      slPrice: formatPrice(slPrice),
      qty: quantity != null ? Number(quantity) : riskAmount && riskDiff > 0 ? Number(riskAmount) / riskDiff : 0
    };
  }, [entry.price, quantity, riskAmount, stopLoss.price, takeProfit.price]);

  const getCoordinates = useCallback((): ToolCoords | null => {
    const chart = chartRef.current, series = seriesRef.current;
    if (!chart || !series) return null;
    const timeScale = chart.timeScale();
    const entryTimeSec = Number(entry.time), endTimeSec = entryTimeSec + Number(timeSpanSeconds);
    const x0 = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: entryTimeSec });
    const x1FromTime = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: endTimeSec });
    const barSpacing = getBarSpacingPx(timeScale, candleTimesSec);
    const x1 = x1FromTime ?? (x0 != null && barSpacing != null ? x0 + barSpacing * (Number(timeSpanSeconds) / Math.max(1e-9, stepSec)) : x0 != null ? x0 + 250 : null);
    const entryY = series.priceToCoordinate(Number(entry.price));
    const tpY = series.priceToCoordinate(Number(takeProfit.price));
    const slY = series.priceToCoordinate(Number(stopLoss.price));
    if (x0 == null || x1 == null || entryY == null || tpY == null || slY == null) return null;
    return { x0: Number(x0), x1: Number(x1), entryY: Number(entryY), tpY: Number(tpY), slY: Number(slY) };
  }, [candleTimesSec, chartRef, entry.price, entry.time, seriesRef, stepSec, stopLoss.price, takeProfit.price, timeSpanSeconds]);

  const repaintTick = useToolRepaintSync({ chartRef, containerRef, candleTimesSec });

  useLayoutEffect(() => {
    const id = window.requestAnimationFrame(() => {
      const next = getCoordinates();
      setCoords(next);
      if (next) setLastGoodCoords(next);
    });
    return () => window.cancelAnimationFrame(id);
  }, [getCoordinates, repaintTick]);

  const beginDrag = (e: React.MouseEvent, mode: Exclude<DragMode, null>) => {
    if (!interactive) return;
    e.stopPropagation(); e.preventDefault(); setIsHovered(true); setIsDragging(mode); onInteractionLockChange?.(true);
    const rect = containerRef.current?.getBoundingClientRect(), chart = chartRef.current, series = seriesRef.current;
    let startMouseTime = Number(entry.time), startMousePrice = Number(entry.price);
    if (rect && chart && series) {
      const x = e.clientX - rect.left, y = e.clientY - rect.top;
      const t = resolveTimeFromX({ chart, x, candleTimesSec });
      if (t != null && Number.isFinite(t)) startMouseTime = Number(t);
      const p = series.coordinateToPrice(y);
      if (p != null && Number.isFinite(Number(p))) startMousePrice = Number(p);
    }
    dragStartRef.current = {
      startMouseX: e.clientX, startMouseY: e.clientY, startMouseTime, startMousePrice,
      startEntryTime: Number(entry.time), startSpanSeconds: Number(timeSpanSeconds), startEntryPrice: Number(entry.price),
      startTpPrice: Number(takeProfit.price), startSlPrice: Number(stopLoss.price)
    };
    onSelect(tool.id);
  };

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isDragging) return;
    const chart = chartRef.current, series = seriesRef.current, rect = containerRef.current?.getBoundingClientRect();
    if (!chart || !series || !rect) return;
    const x = e.clientX - rect.left, y = e.clientY - rect.top;
    const rawPrice = series.coordinateToPrice(y), timeTs = resolveTimeFromX({ chart, x, candleTimesSec });
    if (rawPrice === null || timeTs == null) return;
    const nextPrice = Number(rawPrice), nextTime = Number(timeTs);
    try { chart.setCrosshairPosition(nextPrice, nextTime as never, series); } catch {}
    if (isDragging === "tp") return onUpdate(tool.id, { coordinates: { ...tool.coordinates, takeProfit: { price: nextPrice } } });
    if (isDragging === "sl") return onUpdate(tool.id, { coordinates: { ...tool.coordinates, stopLoss: { price: nextPrice } } });
    if (isDragging === "width") {
      const startTime = dragStartRef.current?.startEntryTime ?? Number(entry.time);
      const spanSec = Math.max(stepSec, Math.round(nextTime - Number(startTime)));
      if (Number.isFinite(spanSec) && spanSec > 0 && spanSec !== Math.round(Number(timeSpanSeconds))) onUpdate(tool.id, { settings: { ...tool.settings, timeSpanSeconds: spanSec } });
      return;
    }
    const base = dragStartRef.current;
    if (!base) return;
    if (isDragging === "entry") {
      const shouldUpdateTime = Math.abs(e.clientX - base.startMouseX) > 3;
      const shouldUpdatePrice = Math.abs(e.clientY - base.startMouseY) > 3;
      const baseEndTime = Number(base.startEntryTime) + Number(base.startSpanSeconds);
      const clampedTime = shouldUpdateTime ? Math.min(Math.round(nextTime), Math.round(baseEndTime - stepSec)) : Number(base.startEntryTime);
      const nextSpanSeconds = shouldUpdateTime ? Math.max(stepSec, Math.round(baseEndTime - clampedTime)) : Number(base.startSpanSeconds);
      return onUpdate(tool.id, {
        coordinates: { ...tool.coordinates, entry: { ...entry, price: shouldUpdatePrice ? nextPrice : Number(base.startEntryPrice), time: clampedTime } },
        ...(shouldUpdateTime ? { settings: { ...tool.settings, timeSpanSeconds: nextSpanSeconds } } : {})
      });
    }
    const dt = nextTime - Number(base.startMouseTime), dp = nextPrice - Number(base.startMousePrice);
    if (!Number.isFinite(dt) || !Number.isFinite(dp)) return;
    onUpdate(tool.id, {
      coordinates: {
        ...tool.coordinates,
        entry: { price: Number(base.startEntryPrice) + dp, time: Math.round(Number(base.startEntryTime) + dt) },
        takeProfit: { price: Number(base.startTpPrice) + dp },
        stopLoss: { price: Number(base.startSlPrice) + dp }
      }
    });
  }, [candleTimesSec, chartRef, containerRef, entry, isDragging, onUpdate, seriesRef, stepSec, timeSpanSeconds, tool.coordinates, tool.id, tool.settings]);

  const handleMouseUp = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(null);
    dragStartRef.current = null;
    onInteractionLockChange?.(false);
  }, [isDragging, onInteractionLockChange]);

  useEffect(() => {
    if (!isDragging) return;
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp, isDragging]);

  useEffect(() => {
    if (!interactive || isActive || isHovered || isDragging) return;
    onInteractionLockChange?.(false);
  }, [interactive, isActive, isHovered, isDragging, onInteractionLockChange]);

  const effectiveCoords = coords ?? lastGoodCoords;
  if (!effectiveCoords) return null;
  const left = Math.min(effectiveCoords.x0, effectiveCoords.x1), toolWidth = Math.max(1, Math.abs(effectiveCoords.x1 - effectiveCoords.x0));
  const labelEntryY = effectiveCoords.entryY, labelTpY = effectiveCoords.tpY, labelSlY = effectiveCoords.slY;
  const tpDelta = Math.abs(Number(takeProfit.price) - Number(entry.price)), slDelta = Math.abs(Number(entry.price) - Number(stopLoss.price));
  const opacity = clamp(Number(tool.settings.colorSettings?.opacity ?? 1), 0.05, 1), zoneOpacity = isActive || isHovered ? 1 : 0.65;

  const zones = [
    { key: "profit", top: Math.min(labelTpY, labelEntryY), height: Math.abs(labelTpY - labelEntryY), color: profitColor, border: "1px solid rgba(8, 153, 129, 0.40)" },
    { key: "loss", top: Math.min(labelSlY, labelEntryY), height: Math.abs(labelSlY - labelEntryY), color: lossColor, border: "1px solid rgba(242, 54, 69, 0.40)" }
  ] as const;
  const pointHandles = [{ mode: "tp" as const, top: labelTpY - 6 }, { mode: "entry" as const, top: labelEntryY - 6 }, { mode: "sl" as const, top: labelSlY - 6 }];
  const infoTags = [
    { key: "tp", top: labelTpY < labelEntryY ? labelTpY - 34 : labelTpY + 10, color: "rgba(0, 150, 136, 1)", text: `Target: ${tpDelta.toFixed(2)} (${metrics.rewardPct}%) ${metrics.tpPrice}` },
    { key: "sl", top: labelSlY > labelEntryY ? labelSlY + 10 : labelSlY - 34, color: "rgba(242, 54, 69, 1)", text: `Stop: ${slDelta.toFixed(2)} (${metrics.riskPct}%) ${metrics.slPrice}` }
  ];

  return (
    <div className="absolute z-30" style={{ left, top: 0, width: toolWidth, height: "100%", pointerEvents: "none" }}>
      {zones.map((zone) => (
        <div
          key={zone.key}
          className="absolute transition-opacity duration-75"
          style={{ top: zone.top, height: zone.height, width: "100%", backgroundColor: zone.color, border: zone.border, pointerEvents: interactive ? "auto" : "none", opacity: zoneOpacity * opacity }}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          onClick={(e) => { e.stopPropagation(); onSelect(tool.id); }}
          onMouseDown={(e) => beginDrag(e, "move")}
        />
      ))}
      {isActive ? <div className="absolute w-full border-t border-dashed border-white/70" style={{ top: labelEntryY, height: 0 }} /> : null}
      {isActive && interactive ? (
        <>
          {pointHandles.map((handle) => (
            <div key={handle.mode} className="absolute -left-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110" style={{ top: handle.top, pointerEvents: "auto", cursor: "ns-resize" }} onMouseDown={(e) => beginDrag(e, handle.mode)} />
          ))}
          <div className="absolute -right-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110" style={{ top: labelEntryY - 6, pointerEvents: "auto", cursor: "ew-resize" }} onMouseDown={(e) => beginDrag(e, "width")} />
          <button
            type="button"
            className="absolute -right-3 -top-3 grid h-6 w-6 place-items-center rounded-full border border-white/15 bg-black/60 text-white/80 shadow hover:bg-red-600/60"
            style={{ pointerEvents: "auto" }}
            onClick={(e) => { e.stopPropagation(); onRemove(tool.id); }}
            title="删除"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 7l10 10M17 7L7 17" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>
          </button>
          {isActive || isDragging !== null ? (
            <>
              {infoTags.map((tag) => <div key={tag.key} className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded px-3 py-1 text-[12px] text-white" style={{ top: tag.top, backgroundColor: tag.color, pointerEvents: "none" }}>{tag.text}</div>)}
              <div className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-white/80 px-4 py-2 text-[12px] text-white" style={{ top: labelEntryY + 10, backgroundColor: tool.type === "long" ? "rgba(0, 150, 136, 0.85)" : "rgba(242, 54, 69, 0.85)", pointerEvents: "none" }}>
                <div className="text-center leading-4">ROI: {metrics.ratio}</div>
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
