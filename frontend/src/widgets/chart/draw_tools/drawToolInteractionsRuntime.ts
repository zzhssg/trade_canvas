import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { IChartApi, ISeriesApi } from "lightweight-charts";

import { estimateTimeStep, normalizeTimeToSec, resolvePointFromClient } from "./chartCoord";
import type { FibInst, PositionInst, PriceTimePoint } from "./types";
import type { DrawMeasureState } from "./useDrawToolState";

type BindMeasurePointerMoveArgs = {
  enabled: boolean;
  activeChartTool: string;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  candleTimesSecRef: MutableRefObject<number[]>;
  interactionLockRef: MutableRefObject<{ dragging: boolean }>;
  measureStateRef: MutableRefObject<DrawMeasureState>;
  setMeasureState: Dispatch<SetStateAction<DrawMeasureState>>;
};

export function bindMeasurePointerMove(args: BindMeasurePointerMoveArgs): () => void {
  if (!args.enabled) return () => {};
  if (args.activeChartTool !== "measure") return () => {};
  const container = args.containerRef.current;
  const chart = args.chartRef.current;
  const series = args.seriesRef.current;
  if (!container || !chart || !series) return () => {};

  const onMove = (event: PointerEvent) => {
    if (args.interactionLockRef.current.dragging) return;
    const state = args.measureStateRef.current;
    if (!state.start || state.locked) return;
    const point = resolvePointFromClient({
      chart,
      series,
      container,
      clientX: event.clientX,
      clientY: event.clientY,
      candleTimesSec: args.candleTimesSecRef.current
    });
    if (!point) return;
    args.setMeasureState((prev) => (prev.start ? { ...prev, current: point } : prev));
  };

  container.addEventListener("pointermove", onMove, { passive: true });
  return () => container.removeEventListener("pointermove", onMove as EventListener);
}

type BindDrawToolHotkeysArgs = {
  enabled: boolean;
  setActiveChartTool: (tool: "cursor" | "measure") => void;
  activeChartToolRef: MutableRefObject<string>;
  activeToolIdRef: MutableRefObject<string | null>;
  fibAnchorARef: MutableRefObject<PriceTimePoint | null>;
  measureStateRef: MutableRefObject<DrawMeasureState>;
  setFibAnchorA: (value: PriceTimePoint | null) => void;
  setMeasureState: Dispatch<SetStateAction<DrawMeasureState>>;
  setActiveToolId: (value: string | null | ((cur: string | null) => string | null)) => void;
};

export function bindDrawToolHotkeys(args: BindDrawToolHotkeysArgs): () => void {
  if (!args.enabled) return () => {};

  const onKeyDown = (event: KeyboardEvent) => {
    if (event.metaKey || event.ctrlKey || event.altKey) return;
    const target = event.target as HTMLElement | null;
    if (target) {
      const tag = target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
    }

    if (event.key === "Escape") {
      event.preventDefault();
      const tool = args.activeChartToolRef.current;
      const hasSelected = args.activeToolIdRef.current != null;
      const hasFibAnchor = args.fibAnchorARef.current != null;
      const measureState = args.measureStateRef.current;

      if (tool === "fib" && hasFibAnchor) {
        args.setFibAnchorA(null);
        args.setActiveChartTool("cursor");
        return;
      }
      if (tool === "position_long" || tool === "position_short") {
        args.setActiveChartTool("cursor");
        return;
      }
      if (tool === "measure" || measureState.start || measureState.current || measureState.locked) {
        args.setMeasureState({ start: null, current: null, locked: false });
        args.setActiveChartTool("cursor");
        return;
      }
      if (hasSelected) {
        args.setActiveToolId(null);
      }
      return;
    }

    if (event.key === "r" || event.key === "R") {
      event.preventDefault();
      const current = args.activeChartToolRef.current;
      const next = current === "measure" ? "cursor" : "measure";
      args.setActiveChartTool(next);
      args.setMeasureState({ start: null, current: null, locked: false });
    }
  };

  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}

type BindDrawToolChartClickArgs = {
  enabled: boolean;
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  interactionLockRef: MutableRefObject<{ dragging: boolean }>;
  replayEnabled: boolean;
  activeChartToolRef: MutableRefObject<string>;
  findReplayIndexByTime: (timeSec: number) => number | null;
  setReplayIndexAndFocus: (index: number, options?: { pause?: boolean }) => void;
  candleTimesSecRef: MutableRefObject<number[]>;
  genId: () => string;
  setPositionTools: Dispatch<SetStateAction<PositionInst[]>>;
  selectTool: (id: string | null) => void;
  setActiveChartTool: (tool: "cursor") => void;
  setFibAnchorA: (value: PriceTimePoint | null) => void;
  fibAnchorARef: MutableRefObject<PriceTimePoint | null>;
  setFibTools: Dispatch<SetStateAction<FibInst[]>>;
  measureStateRef: MutableRefObject<DrawMeasureState>;
  setMeasureState: Dispatch<SetStateAction<DrawMeasureState>>;
  suppressDeselectUntilRef: MutableRefObject<number>;
  setActiveToolId: (value: string | null) => void;
};

export function bindDrawToolChartClick(args: BindDrawToolChartClickArgs): () => void {
  if (!args.enabled) return () => {};
  const chart = args.chartRef.current;
  const series = args.seriesRef.current;
  if (!chart || !series) return () => {};

  const handler = (param: { point?: { x: number; y: number }; time?: unknown } | undefined) => {
    if (args.interactionLockRef.current.dragging) return;
    if (!param?.point) return;

    const x = Number(param.point.x);
    const y = Number(param.point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    const price = series.coordinateToPrice(y);
    if (price == null) return;

    const tool = args.activeChartToolRef.current;

    if (args.replayEnabled && tool === "cursor") {
      const timeFromCoord = chart.timeScale().coordinateToTime(x);
      const timeSec =
        normalizeTimeToSec(param.time) ??
        (typeof param.time === "number" ? Number(param.time) : null) ??
        normalizeTimeToSec(timeFromCoord);
      if (timeSec != null && Number.isFinite(timeSec)) {
        const index = args.findReplayIndexByTime(Math.floor(Number(timeSec)));
        if (index != null) {
          args.setReplayIndexAndFocus(index, { pause: true });
          return;
        }
      }
      const logical = chart.timeScale().coordinateToLogical(x);
      if (logical != null && Number.isFinite(logical)) {
        const total = args.candleTimesSecRef.current.length;
        if (total > 0) {
          const index = Math.max(0, Math.min(total - 1, Math.round(Number(logical))));
          args.setReplayIndexAndFocus(index, { pause: true });
          return;
        }
      }
    }

    if (tool === "position_long" || tool === "position_short") {
      const timeSec = normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
      if (timeSec == null || !Number.isFinite(timeSec)) return;

      const entryPrice = Number(price);
      const dist = entryPrice * 0.01;
      const isLong = tool === "position_long";
      const slPrice = isLong ? entryPrice - dist : entryPrice + dist;
      const tpPrice = isLong ? entryPrice + dist * 2 : entryPrice - dist * 2;
      const riskDiff = Math.abs(entryPrice - slPrice);
      const qty = 100 / Math.max(1e-12, riskDiff);
      const stepSec = estimateTimeStep(args.candleTimesSecRef.current);

      const nextTool: PositionInst = {
        id: `pos_${args.genId()}`,
        type: isLong ? "long" : "short",
        coordinates: {
          entry: { price: entryPrice, time: Number(timeSec) },
          stopLoss: { price: slPrice },
          takeProfit: { price: tpPrice }
        },
        settings: {
          accountSize: 10000,
          riskAmount: 100,
          quantity: qty,
          timeSpanSeconds: 20 * stepSec
        }
      };

      args.setPositionTools((list) => [...list, nextTool]);
      args.selectTool(nextTool.id);
      args.setActiveChartTool("cursor");
      return;
    }

    if (tool === "fib") {
      const timeSec = normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
      if (timeSec == null || !Number.isFinite(timeSec)) return;

      const point: PriceTimePoint = { time: Number(timeSec), price: Number(price) };
      args.suppressDeselectUntilRef.current = Date.now() + 120;
      const anchor = args.fibAnchorARef.current;
      if (!anchor) {
        args.setFibAnchorA(point);
        return;
      }

      const nextTool: FibInst = {
        id: `fib_${args.genId()}`,
        type: "fib_retracement",
        anchors: { a: anchor, b: point },
        settings: { lineWidth: 2 }
      };
      args.setFibTools((list) => [...list, nextTool]);
      args.selectTool(nextTool.id);
      args.setFibAnchorA(null);
      args.setActiveChartTool("cursor");
      return;
    }

    if (tool === "measure") {
      const timeSec = normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
      if (timeSec == null || !Number.isFinite(timeSec)) return;

      const current = args.measureStateRef.current;
      const point = { time: Number(timeSec), price: Number(price), x, y };
      if (current.locked) {
        args.setMeasureState({ start: null, current: null, locked: false });
        args.setActiveChartTool("cursor");
        return;
      }
      if (!current.start) {
        args.setMeasureState({ start: point, current: point, locked: false });
        return;
      }
      args.setMeasureState({ start: current.start, current: point, locked: true });
      return;
    }

    if (Date.now() < args.suppressDeselectUntilRef.current) return;
    if (args.fibAnchorARef.current != null) return;
    const current = args.measureStateRef.current;
    if (current.start || current.current || current.locked) return;
    args.setActiveToolId(null);
  };

  chart.subscribeClick(handler);
  return () => chart.unsubscribeClick(handler);
}
