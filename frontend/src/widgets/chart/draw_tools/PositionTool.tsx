import type { IChartApi, ISeriesApi } from "lightweight-charts";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { estimateTimeStep, getBarSpacingPx, resolveTimeFromX, timeToCoordinateContinuous } from "./chartCoord";
import type { PositionInst } from "./types";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function formatPrice(price: number): string {
  const p = Number(price);
  if (!Number.isFinite(p)) return "--";
  const abs = Math.abs(p);
  const dp = abs >= 1000 ? 2 : abs >= 1 ? 4 : 6;
  return p.toFixed(dp);
}

export function PositionTool({
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
  tool: PositionInst;
  isActive: boolean;
  interactive: boolean;
  onUpdate: (id: string, updates: Partial<PositionInst>) => void;
  onRemove: (id: string) => void;
  onSelect: (id: string | null) => void;
  onInteractionLockChange?: (locked: boolean) => void;
}) {
  const [isDragging, setIsDragging] = useState<"entry" | "tp" | "sl" | "move" | "width" | null>(null);
  const [isHovered, setIsHovered] = useState(false);
  const [updater, setUpdater] = useState(0);
  const rafUpdateIdRef = useRef<number | null>(null);
  const dragStartRef = useRef<{
    startMouseX: number;
    startMouseY: number;
    startMouseTime: number;
    startMousePrice: number;
    startEntryTime: number;
    startSpanSeconds: number;
    startEntryPrice: number;
    startTpPrice: number;
    startSlPrice: number;
  } | null>(null);

  type ToolCoords = { x0: number; x1: number; entryY: number; tpY: number; slY: number };
  const [coords, setCoords] = useState<ToolCoords | null>(null);
  const [lastGoodCoords, setLastGoodCoords] = useState<ToolCoords | null>(null);

  const { entry, stopLoss, takeProfit } = tool.coordinates;
  const { profitColor = "rgba(8, 153, 129, 0.20)", lossColor = "rgba(242, 54, 69, 0.20)" } =
    tool.settings.colorSettings || {};
  const { riskAmount, quantity } = tool.settings;

  const stepSec = useMemo(() => estimateTimeStep(candleTimesSec), [candleTimesSec]);

  const timeSpanSeconds = useMemo(() => {
    const sec = tool.settings.timeSpanSeconds;
    if (typeof sec === "number" && Number.isFinite(sec) && sec > 0) return sec;
    return 20 * stepSec;
  }, [stepSec, tool.settings.timeSpanSeconds]);

  const metrics = useMemo(() => {
    const entryPrice = Number(entry.price);
    const tpPrice = Number(takeProfit.price);
    const slPrice = Number(stopLoss.price);

    const riskDiff = Math.abs(entryPrice - slPrice);
    const rewardDiff = Math.abs(tpPrice - entryPrice);
    const ratio = riskDiff === 0 ? 0 : rewardDiff / riskDiff;

    const qty =
      quantity != null ? Number(quantity) : riskAmount && riskDiff > 0 ? Number(riskAmount) / riskDiff : 0;
    const profitAmount = qty * rewardDiff;
    const lossAmount = qty * riskDiff;
    const rewardPct = entryPrice === 0 ? 0 : (rewardDiff / entryPrice) * 100;
    const riskPct = entryPrice === 0 ? 0 : (riskDiff / entryPrice) * 100;

    return {
      ratio: ratio.toFixed(2),
      qty: qty.toFixed(4),
      profitAmount: profitAmount.toFixed(2),
      lossAmount: lossAmount.toFixed(2),
      rewardPct: rewardPct.toFixed(2),
      riskPct: riskPct.toFixed(2),
      tpPrice: formatPrice(tpPrice),
      slPrice: formatPrice(slPrice),
      entryPrice: formatPrice(entryPrice)
    };
  }, [entry.price, quantity, riskAmount, stopLoss.price, takeProfit.price]);

  const getCoordinates = useCallback((): ToolCoords | null => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return null;

    const timeScale = chart.timeScale();
    const entryTimeSec = Number(entry.time);
    const endTimeSec = entryTimeSec + Number(timeSpanSeconds);

    const x0 = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: entryTimeSec });
    const x1FromTime = timeToCoordinateContinuous({ timeScale, candleTimesSec, timeSec: endTimeSec });

    const barSpacing = getBarSpacingPx(timeScale, candleTimesSec);
    const x1 =
      x1FromTime ??
      (x0 != null && barSpacing != null ? x0 + barSpacing * (Number(timeSpanSeconds) / Math.max(1e-9, stepSec)) : x0 != null ? x0 + 250 : null);

    const entryY = series.priceToCoordinate(Number(entry.price));
    const tpY = series.priceToCoordinate(Number(takeProfit.price));
    const slY = series.priceToCoordinate(Number(stopLoss.price));

    if (x0 == null || x1 == null || entryY == null || tpY == null || slY == null) return null;
    return { x0: Number(x0), x1: Number(x1), entryY: Number(entryY), tpY: Number(tpY), slY: Number(slY) };
  }, [
    candleTimesSec,
    chartRef,
    containerRef,
    entry.price,
    entry.time,
    seriesRef,
    stepSec,
    stopLoss.price,
    takeProfit.price,
    timeSpanSeconds
  ]);

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

  const effectiveCoords = coords ?? lastGoodCoords;
  const isLong = tool.type === "long";
  const showInfo = isActive || isDragging !== null;

  const handleMouseDown = (e: React.MouseEvent, mode: "entry" | "tp" | "sl" | "move") => {
    if (!interactive) return;
    e.stopPropagation();
    e.preventDefault();
    setIsHovered(true);
    setIsDragging(mode);
    onInteractionLockChange?.(true);

    const rect = containerRef.current?.getBoundingClientRect();
    const chart = chartRef.current;
    const series = seriesRef.current;
    let startMouseTime = Number(entry.time);
    let startMousePrice = Number(entry.price);
    if (rect && chart && series) {
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const t = resolveTimeFromX({ chart, x, candleTimesSec });
      if (t != null && Number.isFinite(t)) startMouseTime = Number(t);
      const p = series.coordinateToPrice(y);
      if (p != null && Number.isFinite(Number(p))) startMousePrice = Number(p);
    }

    dragStartRef.current = {
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startMouseTime,
      startMousePrice,
      startEntryTime: Number(entry.time),
      startSpanSeconds: Number(timeSpanSeconds),
      startEntryPrice: Number(entry.price),
      startTpPrice: Number(takeProfit.price),
      startSlPrice: Number(stopLoss.price)
    };
    onSelect(tool.id);
  };

  const handleWidthMouseDown = (e: React.MouseEvent) => {
    if (!interactive) return;
    e.stopPropagation();
    e.preventDefault();
    setIsHovered(true);
    setIsDragging("width");
    onInteractionLockChange?.(true);

    const rect = containerRef.current?.getBoundingClientRect();
    const chart = chartRef.current;
    const series = seriesRef.current;
    let startMouseTime = Number(entry.time);
    let startMousePrice = Number(entry.price);
    if (rect && chart && series) {
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const t = resolveTimeFromX({ chart, x, candleTimesSec });
      if (t != null && Number.isFinite(t)) startMouseTime = Number(t);
      const p = series.coordinateToPrice(y);
      if (p != null && Number.isFinite(Number(p))) startMousePrice = Number(p);
    }

    dragStartRef.current = {
      startMouseX: e.clientX,
      startMouseY: e.clientY,
      startMouseTime,
      startMousePrice,
      startEntryTime: Number(entry.time),
      startSpanSeconds: Number(timeSpanSeconds),
      startEntryPrice: Number(entry.price),
      startTpPrice: Number(takeProfit.price),
      startSlPrice: Number(stopLoss.price)
    };
    onSelect(tool.id);
  };

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging) return;
      const chart = chartRef.current;
      const series = seriesRef.current;
      const rect = containerRef.current?.getBoundingClientRect();
      if (!chart || !series || !rect) return;

      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      const rawPrice = series.coordinateToPrice(y);
      if (rawPrice === null) return;
      const timeTs = resolveTimeFromX({ chart, x, candleTimesSec });
      if (timeTs == null) return;

      try {
        chart.setCrosshairPosition(Number(rawPrice), Number(timeTs) as any, series);
      } catch {
        // ignore
      }

      if (isDragging === "tp") {
        onUpdate(tool.id, { coordinates: { ...tool.coordinates, takeProfit: { price: Number(rawPrice) } } });
        return;
      }
      if (isDragging === "sl") {
        onUpdate(tool.id, { coordinates: { ...tool.coordinates, stopLoss: { price: Number(rawPrice) } } });
        return;
      }
      if (isDragging === "entry") {
        const base = dragStartRef.current;
        const DRAG_THRESHOLD_PX = 3;
        const shouldUpdateTime = base ? Math.abs(e.clientX - base.startMouseX) > DRAG_THRESHOLD_PX : true;
        const shouldUpdatePrice = base ? Math.abs(e.clientY - base.startMouseY) > DRAG_THRESHOLD_PX : true;

        const baseStartTime = base?.startEntryTime ?? Number(entry.time);
        const baseSpanSec = base?.startSpanSeconds ?? Number(timeSpanSeconds);
        const baseEndTime = baseStartTime + baseSpanSec;

        let nextTime = baseStartTime;
        let nextSpanSeconds = baseSpanSec;
        if (shouldUpdateTime) {
          const candidate = Math.round(Number(timeTs));
          const maxStart = Math.round(baseEndTime - stepSec);
          nextTime = Math.min(candidate, maxStart);
          nextSpanSeconds = Math.max(stepSec, Math.round(baseEndTime - nextTime));
        }
        const nextPrice = shouldUpdatePrice ? Number(rawPrice) : base?.startEntryPrice ?? Number(entry.price);

        onUpdate(tool.id, {
          coordinates: {
            ...tool.coordinates,
            entry: { ...entry, price: nextPrice, time: nextTime }
          },
          ...(shouldUpdateTime
            ? {
                settings: { ...tool.settings, timeSpanSeconds: nextSpanSeconds }
              }
            : {})
        });
        return;
      }
      if (isDragging === "move") {
        const base = dragStartRef.current;
        if (!base) return;
        const dt = Number(timeTs) - Number(base.startMouseTime);
        const dp = Number(rawPrice) - Number(base.startMousePrice);
        if (!Number.isFinite(dt) || !Number.isFinite(dp)) return;
        const nextEntryTime = Math.round(Number(base.startEntryTime) + dt);
        const nextEntryPrice = Number(base.startEntryPrice) + dp;
        onUpdate(tool.id, {
          coordinates: {
            ...tool.coordinates,
            entry: { price: nextEntryPrice, time: nextEntryTime },
            takeProfit: { price: Number(base.startTpPrice) + dp },
            stopLoss: { price: Number(base.startSlPrice) + dp }
          }
        });
        return;
      }
      if (isDragging === "width") {
        const base = dragStartRef.current;
        const startTime = base?.startEntryTime ?? Number(entry.time);
        const spanSecRaw = Number(timeTs) - Number(startTime);
        const spanSec = Math.max(stepSec, Math.round(spanSecRaw));
        if (!Number.isFinite(spanSec) || spanSec <= 0) return;
        if (spanSec === Math.round(Number(timeSpanSeconds))) return;
        onUpdate(tool.id, {
          settings: {
            ...tool.settings,
            timeSpanSeconds: spanSec
          }
        });
      }
    },
    [
      candleTimesSec,
      chartRef,
      containerRef,
      entry,
      isDragging,
      onUpdate,
      seriesRef,
      stepSec,
      timeSpanSeconds,
      tool.coordinates,
      tool.id,
      tool.settings
    ]
  );

  const handleMouseUp = useCallback(() => {
    if (!isDragging) return;
    setIsDragging(null);
    dragStartRef.current = null;
    onInteractionLockChange?.(false);
  }, [isDragging, onInteractionLockChange]);

  useEffect(() => {
    if (isDragging) {
      window.addEventListener("mousemove", handleMouseMove);
      window.addEventListener("mouseup", handleMouseUp);
    }
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp, isDragging]);

  useEffect(() => {
    if (!interactive) return;
    if (isActive || isHovered || isDragging) return;
    // best-effort unlock in case an interaction ended while the tool lost active state
    onInteractionLockChange?.(false);
  }, [interactive, isActive, isHovered, isDragging, onInteractionLockChange]);

  if (!effectiveCoords) return null;

  const left = Math.min(effectiveCoords.x0, effectiveCoords.x1);
  const toolWidth = Math.max(1, Math.abs(effectiveCoords.x1 - effectiveCoords.x0));

  const labelTpY = effectiveCoords.tpY;
  const labelSlY = effectiveCoords.slY;
  const labelEntryY = effectiveCoords.entryY;

  const tpLabelTop = labelTpY < labelEntryY ? labelTpY - 34 : labelTpY + 10;
  const slLabelTop = labelSlY > labelEntryY ? labelSlY + 10 : labelSlY - 34;
  const tpDelta = Math.abs(Number(takeProfit.price) - Number(entry.price));
  const slDelta = Math.abs(Number(entry.price) - Number(stopLoss.price));

  const opacity = clamp(Number(tool.settings.colorSettings?.opacity ?? 1), 0.05, 1);
  const zoneOpacity = (isActive || isHovered) ? 1 : 0.65;

  return (
    <div className="absolute z-30" style={{ left, top: 0, width: toolWidth, height: "100%", pointerEvents: "none" }}>
      {/* Profit Zone */}
      <div
        className="absolute transition-opacity duration-75"
        style={{
          top: Math.min(effectiveCoords.tpY, effectiveCoords.entryY),
          height: Math.abs(effectiveCoords.tpY - effectiveCoords.entryY),
          width: "100%",
          backgroundColor: profitColor,
          border: "1px solid rgba(8, 153, 129, 0.40)",
          pointerEvents: interactive ? "auto" : "none",
          opacity: zoneOpacity * opacity
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(tool.id);
        }}
        onMouseDown={(e) => handleMouseDown(e, "move")}
      />

      {/* Loss Zone */}
      <div
        className="absolute transition-opacity duration-75"
        style={{
          top: Math.min(effectiveCoords.slY, effectiveCoords.entryY),
          height: Math.abs(effectiveCoords.slY - effectiveCoords.entryY),
          width: "100%",
          backgroundColor: lossColor,
          border: "1px solid rgba(242, 54, 69, 0.40)",
          pointerEvents: interactive ? "auto" : "none",
          opacity: zoneOpacity * opacity
        }}
        onMouseEnter={() => setIsHovered(true)}
        onMouseLeave={() => setIsHovered(false)}
        onClick={(e) => {
          e.stopPropagation();
          onSelect(tool.id);
        }}
        onMouseDown={(e) => handleMouseDown(e, "move")}
      />

      {/* Entry Line (Active only, TV-like) */}
      {isActive ? (
        <div className="absolute w-full border-t border-dashed border-white/70" style={{ top: effectiveCoords.entryY, height: 0 }} />
      ) : null}

      {/* Handles + Labels */}
      {isActive && interactive ? (
        <>
          <div
            className="absolute -left-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110"
            style={{ top: labelTpY - 6, pointerEvents: "auto", cursor: "ns-resize" }}
            onMouseDown={(e) => handleMouseDown(e, "tp")}
          />
          <div
            className="absolute -left-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110"
            style={{ top: labelEntryY - 6, pointerEvents: "auto", cursor: "ns-resize" }}
            onMouseDown={(e) => handleMouseDown(e, "entry")}
          />
          <div
            className="absolute -left-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110"
            style={{ top: labelSlY - 6, pointerEvents: "auto", cursor: "ns-resize" }}
            onMouseDown={(e) => handleMouseDown(e, "sl")}
          />

          <div
            className="absolute -right-2 h-3 w-3 rounded-full border border-sky-400 bg-white shadow transition-transform hover:scale-110"
            style={{ top: labelEntryY - 6, pointerEvents: "auto", cursor: "ew-resize" }}
            onMouseDown={handleWidthMouseDown}
          />

          <button
            type="button"
            className="absolute -right-3 -top-3 grid h-6 w-6 place-items-center rounded-full border border-white/15 bg-black/60 text-white/80 shadow hover:bg-red-600/60"
            style={{ pointerEvents: "auto" }}
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

          {showInfo ? (
            <>
              <div
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded px-3 py-1 text-[12px] text-white"
                style={{ top: tpLabelTop, backgroundColor: "rgba(0, 150, 136, 1)", pointerEvents: "none" }}
              >
                Target: {tpDelta.toFixed(2)} ({metrics.rewardPct}%) {metrics.tpPrice}
              </div>
              <div
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded px-3 py-1 text-[12px] text-white"
                style={{ top: slLabelTop, backgroundColor: "rgba(242, 54, 69, 1)", pointerEvents: "none" }}
              >
                Stop: {slDelta.toFixed(2)} ({metrics.riskPct}%) {metrics.slPrice}
              </div>
              <div
                className="absolute left-1/2 -translate-x-1/2 whitespace-nowrap rounded-md border border-white/80 px-4 py-2 text-[12px] text-white"
                style={{
                  top: labelEntryY + 10,
                  backgroundColor: isLong ? "rgba(0, 150, 136, 0.85)" : "rgba(242, 54, 69, 0.85)",
                  pointerEvents: "none"
                }}
              >
                <div className="text-center leading-4">ROI: {metrics.ratio}</div>
              </div>
            </>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
