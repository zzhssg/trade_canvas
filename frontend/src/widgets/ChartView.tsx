import {
  LineSeries,
  LineStyle,
  type IChartApi,
  type ISeriesApi,
  type LineWidth,
  type SeriesMarker,
  type Time,
  type UTCTimestamp
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useResizeObserver from "use-resize-observer";

import { logDebugEvent } from "../debug/debug";
import { CENTER_SCROLL_SELECTOR, chartWheelZoomRatio, normalizeWheelDeltaY } from "../lib/wheelContract";
import { getFactorParentsBySubKey, useFactorCatalog } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";
import { useUiStore } from "../state/uiStore";

import { FibTool } from "./chart/draw_tools/FibTool";
import { MeasureTool } from "./chart/draw_tools/MeasureTool";
import { PositionTool } from "./chart/draw_tools/PositionTool";
import { estimateTimeStep, normalizeTimeToSec, resolvePointFromClient, sortAndDeduplicateTimes } from "./chart/draw_tools/chartCoord";
import type { FibInst, PositionInst, PriceTimePoint } from "./chart/draw_tools/types";
import { useFibPreview } from "./chart/draw_tools/useFibPreview";

import {
  fetchCandles,
  fetchDrawDelta,
  fetchFactorSlices,
  fetchWorldFrameAtTime,
  fetchWorldFrameLive,
  pollWorldDelta
} from "./chart/api";
import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./chart/barSpacing";
import { mergeCandlesWindow, mergeCandleWindow, toChartCandle } from "./chart/candles";
import { buildSmaLineData, computeSmaAtIndex, isSmaKey } from "./chart/sma";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayHistoryEventV1,
  ReplayKlineBarV1,
  ReplayWindowV1,
  WorldStateV1
} from "./chart/types";
import { timeframeToSeconds } from "./chart/timeframe";
import { useLightweightChart } from "./chart/useLightweightChart";
import { useReplayBindings } from "./chart/useReplayBindings";
import { useReplayController } from "./chart/useReplayController";
import { useReplayPackage } from "./chart/useReplayPackage";
import { useReplayPackageWindowSync } from "./chart/useReplayPackageWindowSync";
import { useWsSync } from "./chart/useWsSync";

const INITIAL_TAIL_LIMIT = 2000;
const ENABLE_REPLAY_V1 = String(import.meta.env.VITE_ENABLE_REPLAY_V1 ?? "1") === "1";
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
const ENABLE_ANCHOR_TOP_LAYER = String(import.meta.env.VITE_ENABLE_ANCHOR_TOP_LAYER ?? "1") === "1";
// Default to enabled (unless explicitly disabled) to avoid "delta + slices" double-fetch loops in live mode.
const ENABLE_WORLD_FRAME = String(import.meta.env.VITE_ENABLE_WORLD_FRAME ?? "1") === "1";
const PEN_SEGMENT_RENDER_LIMIT = 200;
const ENABLE_DRAW_TOOLS = String(import.meta.env.VITE_ENABLE_DRAW_TOOLS ?? "1") === "1";
const REPLAY_WINDOW_CANDLES = 2000;
const REPLAY_WINDOW_SIZE = 500;
const REPLAY_SNAPSHOT_INTERVAL = 25;
type PenLinePoint = { time: UTCTimestamp; value: number };
type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";
type OverlayPath = {
  id: string;
  feature: string;
  points: PenLinePoint[];
  color: string;
  lineWidth: LineWidth;
  lineStyle: LineStyle;
};

function resolveAnchorTopLayerStyle(path: OverlayPath): { color: string; lineWidth: number; lineStyle: LineStyle; haloWidth: number } {
  const baseWidth = Math.max(1, Number(path.lineWidth) || 1);
  if (path.feature === "anchor.current") {
    const lineWidth = Math.max(3, baseWidth + 1);
    return { color: "#f59e0b", lineWidth, lineStyle: path.lineStyle, haloWidth: lineWidth + 1 };
  }
  if (path.feature === "anchor.history") {
    const lineWidth = Math.max(2.5, baseWidth + 0.5);
    return { color: "#3b82f6", lineWidth, lineStyle: LineStyle.Solid, haloWidth: lineWidth + 0.8 };
  }
  const lineWidth = Math.max(2.5, baseWidth + 0.5);
  return { color: path.color, lineWidth, lineStyle: path.lineStyle, haloWidth: lineWidth + 0.8 };
}

export function ChartView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();
  const wheelGuardRef = useRef<HTMLDivElement | null>(null);

  const [candles, setCandles] = useState<Candle[]>([]);
  const [barSpacing, setBarSpacing] = useState<number | null>(null);
  const candlesRef = useRef<Candle[]>([]);
  const candleTimesSecRef = useRef<number[]>([]);
  const lastWsCandleTimeRef = useRef<number | null>(null);
  const [lastWsCandleTime, setLastWsCandleTime] = useState<number | null>(null);
  const appliedRef = useRef<{ len: number; lastTime: number | null }>({ len: 0, lastTime: null });
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const { exchange, market, symbol, timeframe, activeChartTool, setActiveChartTool } = useUiStore();
  const {
    replayMode,
    replayPlaying,
    replaySpeedMs,
    replayIndex,
    replayTotal,
    replayFocusTime,
    replayPrepareStatus,
    replayPreparedAlignedTime,
    setReplayPlaying,
    setReplayIndex,
    setReplayTotal,
    setReplayFocusTime,
    setReplayFrame,
    setReplayFrameLoading,
    setReplayFrameError,
    setReplayPrepareStatus,
    setReplayPrepareError,
    setReplayPreparedAlignedTime,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions,
    resetReplayData
  } = useReplayBindings();
  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);

  const { visibleFeatures } = useFactorStore();
  const factorCatalog = useFactorCatalog();
  const visibleFeaturesRef = useRef(visibleFeatures);
  const parentBySubKey = useMemo(() => getFactorParentsBySubKey(factorCatalog), [factorCatalog]);
  const lineSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    if (toastTimerRef.current != null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setToastMessage(null);
      toastTimerRef.current = null;
    }, 3200);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current != null) {
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
    };
  }, []);
  const entryMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const pivotMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const anchorSwitchMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const overlayCatalogRef = useRef<Map<string, OverlayInstructionPatchItemV1>>(new Map());
  const overlayActiveIdsRef = useRef<Set<string>>(new Set());
  const overlayCursorVersionRef = useRef<number>(0);
  const overlayPullInFlightRef = useRef(false);
  const overlayPolylineSeriesByIdRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const entryEnabledRef = useRef<boolean>(false);
  const worldFrameHealthyRef = useRef<boolean>(ENABLE_WORLD_FRAME);
  const [pivotCount, setPivotCount] = useState(0);
  const [zhongshuCount, setZhongshuCount] = useState(0);
  const [anchorCount, setAnchorCount] = useState(0);
  const [anchorSwitchCount, setAnchorSwitchCount] = useState(0);
  const replayEnabled = ENABLE_REPLAY_V1 && replayMode === "replay";
  const [replayMaskX, setReplayMaskX] = useState<number | null>(null);
  const replayAllCandlesRef = useRef<Array<Candle | null>>([]);
  const replayWindowIndexRef = useRef<number | null>(null);
  const replayPatchRef = useRef<OverlayInstructionPatchItemV1[]>([]);
  const replayPatchAppliedIdxRef = useRef<number>(0);
  const replayFramePullInFlightRef = useRef(false);
  const replayFramePendingTimeRef = useRef<number | null>(null);
  const replayFrameLatestTimeRef = useRef<number | null>(null);
  const followPendingTimeRef = useRef<number | null>(null);
  const followTimerIdRef = useRef<number | null>(null);

  const replayPackage = useReplayPackage({
    seriesId,
    enabled: replayEnabled && replayPrepareStatus === "ready",
    windowCandles: REPLAY_WINDOW_CANDLES,
    windowSize: REPLAY_WINDOW_SIZE,
    snapshotInterval: REPLAY_SNAPSHOT_INTERVAL
  });
  const replayPackageEnabled = replayEnabled && replayPrepareStatus === "ready" && replayPackage.enabled;
  const replayPackageStatus = replayPackage.status;
  const replayPackageMeta = replayPackage.metadata;
  const replayPackageHistory = replayPackage.historyEvents;
  const replayPackageWindows = replayPackage.windows;
  const replayEnsureWindowRange = replayPackage.ensureWindowRange;
  const { setReplayIndexAndFocus } = useReplayController({
    seriesId,
    replayEnabled,
    replayPlaying,
    replaySpeedMs,
    replayIndex,
    replayTotal,
    windowCandles: INITIAL_TAIL_LIMIT,
    resetReplayData,
    setReplayPlaying,
    setReplayIndex,
    setReplayPrepareStatus,
    setReplayPrepareError,
    setReplayPreparedAlignedTime
  });
  const { openMarketWs } = useWsSync({ seriesId });

  // --- Draw tools (pure in-memory, per ChartView instance) ---
  const [positionTools, setPositionTools] = useState<PositionInst[]>([]);
  const [fibTools, setFibTools] = useState<FibInst[]>([]);
  const [activeToolId, setActiveToolId] = useState<string | null>(null);
  const [fibAnchorA, setFibAnchorA] = useState<PriceTimePoint | null>(null);
  const [measureState, setMeasureState] = useState<{
    start: (PriceTimePoint & { x: number; y: number }) | null;
    current: (PriceTimePoint & { x: number; y: number }) | null;
    locked: boolean;
  }>({ start: null, current: null, locked: false });

  const activeChartToolRef = useRef(activeChartTool);
  const fibAnchorARef = useRef(fibAnchorA);
  const measureStateRef = useRef(measureState);
  const activeToolIdRef = useRef(activeToolId);
  const interactionLockRef = useRef<{ dragging: boolean }>({ dragging: false });
  const suppressDeselectUntilRef = useRef<number>(0);

  useEffect(() => {
    activeChartToolRef.current = activeChartTool;
  }, [activeChartTool]);
  useEffect(() => {
    fibAnchorARef.current = fibAnchorA;
  }, [fibAnchorA]);
  useEffect(() => {
    measureStateRef.current = measureState;
  }, [measureState]);
  useEffect(() => {
    activeToolIdRef.current = activeToolId;
  }, [activeToolId]);

  const findReplayIndexByTime = useCallback((timeSec: number) => {
    const all = candlesRef.current;
    if (all.length === 0) return null;
    let lo = 0;
    let hi = all.length - 1;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      const t = Number(all[mid]!.time);
      if (t === timeSec) return mid;
      if (t < timeSec) lo = mid + 1;
      else hi = mid - 1;
    }
    const idx = Math.max(0, Math.min(all.length - 1, hi));
    return idx;
  }, []);

  const genId = useCallback(() => Math.random().toString(36).substring(2, 9), []);

  const clearDrawTools = useCallback(() => {
    setPositionTools([]);
    setFibTools([]);
    setActiveToolId(null);
    setFibAnchorA(null);
    setMeasureState({ start: null, current: null, locked: false });
    suppressDeselectUntilRef.current = 0;
  }, []);

  useEffect(() => {
    // No persistence: switching symbol/timeframe resets drawings to avoid misleading overlays.
    if (!ENABLE_DRAW_TOOLS) return;
    clearDrawTools();
    setActiveChartTool("cursor");
  }, [clearDrawTools, seriesId, setActiveChartTool]);

  useEffect(() => {
    if (ENABLE_DRAW_TOOLS) return;
    if (activeChartTool !== "cursor") setActiveChartTool("cursor");
  }, [activeChartTool, setActiveChartTool]);

  const updatePositionTool = useCallback((id: string, updates: Partial<PositionInst>) => {
    setPositionTools((list) =>
      list.map((t) => {
        if (t.id !== id) return t;
        return {
          ...t,
          ...updates,
          coordinates: { ...t.coordinates, ...(updates.coordinates ?? {}) },
          settings: { ...t.settings, ...(updates.settings ?? {}) }
        };
      })
    );
  }, []);

  const removePositionTool = useCallback((id: string) => {
    setPositionTools((list) => list.filter((t) => t.id !== id));
    setActiveToolId((cur) => (cur === id ? null : cur));
  }, []);

  const updateFibTool = useCallback((id: string, updates: Partial<FibInst>) => {
    setFibTools((list) =>
      list.map((t) => {
        if (t.id !== id) return t;
        return {
          ...t,
          ...updates,
          anchors: { ...t.anchors, ...(updates.anchors ?? {}) },
          settings: { ...t.settings, ...(updates.settings ?? {}) }
        };
      })
    );
  }, []);

  const removeFibTool = useCallback((id: string) => {
    setFibTools((list) => list.filter((t) => t.id !== id));
    setActiveToolId((cur) => (cur === id ? null : cur));
  }, []);

  const selectTool = useCallback((id: string | null) => {
    if (id) suppressDeselectUntilRef.current = Date.now() + 120;
    setActiveToolId(id);
  }, []);

  const penSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const penPointsRef = useRef<PenLinePoint[]>([]);
  const [penPointCount, setPenPointCount] = useState(0);
  const [anchorHighlightEpoch, setAnchorHighlightEpoch] = useState(0);

  const penSegmentSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const penSegmentsRef = useRef<
    Array<{
      key: string;
      points: PenLinePoint[];
      highlighted: boolean;
    }>
  >([]);

  const anchorPenSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const anchorPenPointsRef = useRef<PenLinePoint[] | null>(null);
  const anchorPenIsDashedRef = useRef<boolean>(false);
  const replayPenPreviewSeriesByFeatureRef = useRef<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>({
    "pen.extending": null,
    "pen.candidate": null
  });
  const replayPenPreviewPointsRef = useRef<Record<ReplayPenPreviewFeature, PenLinePoint[]>>({
    "pen.extending": [],
    "pen.candidate": []
  });
  const factorPullInFlightRef = useRef(false);
  const factorPullPendingTimeRef = useRef<number | null>(null);
  const lastFactorAtTimeRef = useRef<number | null>(null);
  const zhongshuRectCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const anchorTopLayerCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const anchorTopLayerPathsRef = useRef<OverlayPath[]>([]);
  const [overlayPaintEpoch, setOverlayPaintEpoch] = useState(0);
  const [anchorTopLayerPathCount, setAnchorTopLayerPathCount] = useState(0);

  const { chartRef, candleSeriesRef: seriesRef, markersApiRef, chartEpoch } = useLightweightChart({
    containerRef,
    width,
    height,
    onCreated: ({ chart, candleSeries }) => {
      const existing = candlesRef.current;
      if (existing.length > 0) {
        candleSeries.setData(existing);
        chart.timeScale().fitContent();
        const cur = chart.timeScale().options().barSpacing;
        const next = clampBarSpacing(cur, MAX_BAR_SPACING_ON_FIT_CONTENT);
        if (next !== cur) chart.applyOptions({ timeScale: { barSpacing: next } });
        const last = existing[existing.length - 1]!;
        appliedRef.current = { len: existing.length, lastTime: last.time as number };
      }
    },
    onCleanup: () => {
      lineSeriesByKeyRef.current.clear();
      entryMarkersRef.current = [];
      pivotMarkersRef.current = [];
      overlayCatalogRef.current.clear();
      overlayActiveIdsRef.current.clear();
      overlayCursorVersionRef.current = 0;
      penPointsRef.current = [];
      penSeriesRef.current = null;
      anchorPenPointsRef.current = null;
      anchorPenIsDashedRef.current = false;
      anchorPenSeriesRef.current = null;
      for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
        const series = replayPenPreviewSeriesByFeatureRef.current[feature];
        if (series) chartRef.current?.removeSeries(series);
        replayPenPreviewSeriesByFeatureRef.current[feature] = null;
        replayPenPreviewPointsRef.current[feature] = [];
      }
      for (const s of penSegmentSeriesByKeyRef.current.values()) chartRef.current?.removeSeries(s);
      penSegmentSeriesByKeyRef.current.clear();
      penSegmentsRef.current = [];
      overlayPullInFlightRef.current = false;
      factorPullInFlightRef.current = false;
      factorPullPendingTimeRef.current = null;
      lastFactorAtTimeRef.current = null;
      entryEnabledRef.current = false;
      appliedRef.current = { len: 0, lastTime: null };
      const rectCanvas = zhongshuRectCanvasRef.current;
      if (rectCanvas && rectCanvas.parentElement) rectCanvas.parentElement.removeChild(rectCanvas);
      zhongshuRectCanvasRef.current = null;
      const anchorCanvas = anchorTopLayerCanvasRef.current;
      if (anchorCanvas && anchorCanvas.parentElement) anchorCanvas.parentElement.removeChild(anchorCanvas);
      anchorTopLayerCanvasRef.current = null;
      anchorTopLayerPathsRef.current = [];
    }
  });

  const fibPreviewTool = useFibPreview({
    enabled: ENABLE_DRAW_TOOLS && activeChartTool === "fib" && fibAnchorA != null,
    anchorA: fibAnchorA,
    chartRef,
    seriesRef,
    candleTimesSecRef,
    containerRef
  });

  useEffect(() => {
    candleTimesSecRef.current = sortAndDeduplicateTimes(candles.map((c) => Number(c.time)).filter((t) => Number.isFinite(t)));
  }, [candles]);

  // Measure live update: pointer move while enabled + started + not locked.
  useEffect(() => {
    if (!ENABLE_DRAW_TOOLS) return;
    if (activeChartTool !== "measure") return;
    const container = containerRef.current;
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!container || !chart || !series) return;

    const onMove = (e: PointerEvent) => {
      if (interactionLockRef.current.dragging) return;
      const st = measureStateRef.current;
      if (!st.start || st.locked) return;
      const point = resolvePointFromClient({
        chart,
        series,
        container,
        clientX: e.clientX,
        clientY: e.clientY,
        candleTimesSec: candleTimesSecRef.current
      });
      if (!point) return;
      setMeasureState((prev) => (prev.start ? { ...prev, current: point } : prev));
    };

    container.addEventListener("pointermove", onMove, { passive: true });
    return () => container.removeEventListener("pointermove", onMove as EventListener);
  }, [activeChartTool, chartEpoch, chartRef, seriesRef]);

  // ESC / R shortcuts
  useEffect(() => {
    if (!ENABLE_DRAW_TOOLS) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName;
        if (tag === "INPUT" || tag === "TEXTAREA" || target.isContentEditable) return;
      }

      if (e.key === "Escape") {
        e.preventDefault();
        const tool = activeChartToolRef.current;
        const hasSelected = activeToolIdRef.current != null;
        const hasFibAnchor = fibAnchorARef.current != null;
        const ms = measureStateRef.current;

        if (tool === "fib" && hasFibAnchor) {
          setFibAnchorA(null);
          setActiveChartTool("cursor");
          return;
        }
        if (tool === "position_long" || tool === "position_short") {
          setActiveChartTool("cursor");
          return;
        }
        if (tool === "measure" || ms.start || ms.current || ms.locked) {
          setMeasureState({ start: null, current: null, locked: false });
          setActiveChartTool("cursor");
          return;
        }
        if (hasSelected) {
          setActiveToolId(null);
        }
        return;
      }

      if (e.key === "r" || e.key === "R") {
        e.preventDefault();
        const cur = activeChartToolRef.current;
        const next = cur === "measure" ? "cursor" : "measure";
        setActiveChartTool(next);
        setMeasureState({ start: null, current: null, locked: false });
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [setActiveChartTool]);

  // Chart click handler for creation + measure click flow + deselect.
  useEffect(() => {
    if (!ENABLE_DRAW_TOOLS) return;
    const chart = chartRef.current;
    const series = seriesRef.current;
    if (!chart || !series) return;

    const handler = (param: any) => {
      if (interactionLockRef.current.dragging) return;
      if (!param?.point) return;

      const x = Number(param.point.x);
      const y = Number(param.point.y);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return;

      const price = series.coordinateToPrice(y);
      if (price == null) return;

      const tool = activeChartToolRef.current;

      if (replayEnabled && tool === "cursor") {
        const timeSec =
          normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
        if (timeSec != null && Number.isFinite(timeSec)) {
          const idx = findReplayIndexByTime(Math.floor(Number(timeSec)));
          if (idx != null) {
            setReplayIndexAndFocus(idx, { pause: true });
            return;
          }
        }
      }

      if (tool === "position_long" || tool === "position_short") {
        const timeSec =
          normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
        if (timeSec == null || !Number.isFinite(timeSec)) return;

        const entryPrice = Number(price);
        const dist = entryPrice * 0.01;
        const isLong = tool === "position_long";
        const slPrice = isLong ? entryPrice - dist : entryPrice + dist;
        const tpPrice = isLong ? entryPrice + dist * 2 : entryPrice - dist * 2;
        const riskDiff = Math.abs(entryPrice - slPrice);
        const qty = 100 / Math.max(1e-12, riskDiff);
        const stepSec = estimateTimeStep(candleTimesSecRef.current);

        const newTool: PositionInst = {
          id: `pos_${genId()}`,
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

        setPositionTools((list) => [...list, newTool]);
        selectTool(newTool.id);
        setActiveChartTool("cursor");
        return;
      }

      if (tool === "fib") {
        const timeSec =
          normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
        if (timeSec == null || !Number.isFinite(timeSec)) return;

        const point: PriceTimePoint = { time: Number(timeSec), price: Number(price) };
        suppressDeselectUntilRef.current = Date.now() + 120;
        const a = fibAnchorARef.current;
        if (!a) {
          setFibAnchorA(point);
          return;
        }
        const newTool: FibInst = {
          id: `fib_${genId()}`,
          type: "fib_retracement",
          anchors: { a, b: point },
          settings: { lineWidth: 2 }
        };
        setFibTools((list) => [...list, newTool]);
        selectTool(newTool.id);
        setFibAnchorA(null);
        setActiveChartTool("cursor");
        return;
      }

      if (tool === "measure") {
        const timeSec =
          normalizeTimeToSec(param.time) ?? (typeof param.time === "number" ? Number(param.time) : null);
        if (timeSec == null || !Number.isFinite(timeSec)) return;

        const ms = measureStateRef.current;
        const p = { time: Number(timeSec), price: Number(price), x, y };
        if (ms.locked) {
          setMeasureState({ start: null, current: null, locked: false });
          setActiveChartTool("cursor");
          return;
        }
        if (!ms.start) {
          setMeasureState({ start: p, current: p, locked: false });
          return;
        }
        setMeasureState({ start: ms.start, current: p, locked: true });
        return;
      }

      // Deselect active tool when clicking on empty chart area (TradingView-like).
      if (Date.now() < suppressDeselectUntilRef.current) return;
      if (fibAnchorARef.current != null) return;
      const ms = measureStateRef.current;
      if (ms.start || ms.current || ms.locked) return;
      setActiveToolId(null);
    };

    chart.subscribeClick(handler);
    return () => chart.unsubscribeClick(handler);
  }, [chartEpoch, chartRef, findReplayIndexByTime, genId, replayEnabled, selectTool, seriesRef, setActiveChartTool, setReplayIndexAndFocus]);

  useEffect(() => {
    const el = wheelGuardRef.current;
    if (!el) return;
    let rafId: number | null = null;
    const onWheel = (event: WheelEvent) => {
      const chart = chartRef.current;
      if (!chart) return;
      if (event.deltaY === 0) return;

      const center = el.closest(CENTER_SCROLL_SELECTOR) as HTMLElement | null;
      if (center) {
        const oy = window.getComputedStyle(center).overflowY;
        if (oy !== "hidden") {
          // When the middle scroll container is unlocked, keep the wheel scroll native and
          // stop the event before Lightweight Charts handles zoom.
          event.stopPropagation();
          return;
        }
      }

      // When the middle scroll container is locked (chart hovered), prevent the page from scrolling.
      // Let Lightweight Charts handle the actual wheel zoom natively (smoother than our custom applyOptions loop).
      event.preventDefault();
      const ratio = chartWheelZoomRatio(normalizeWheelDeltaY(event));
      if (!ratio) return;
      const timeScale = chart.timeScale();
      const before = timeScale.options().barSpacing;
      if (rafId != null) window.cancelAnimationFrame(rafId);
      rafId = window.requestAnimationFrame(() => {
        const after = timeScale.options().barSpacing;
        if (after !== before) {
          setBarSpacing((prev) => (prev === after ? prev : after));
          return;
        }
        const next = Math.max(0.5, before * ratio);
        if (!Number.isFinite(next) || next === before) return;
        chart.applyOptions({ timeScale: { barSpacing: next } });
        setBarSpacing((prev) => (prev === next ? prev : next));
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false, capture: true });
    return () => {
      if (rafId != null) window.cancelAnimationFrame(rafId);
      el.removeEventListener("wheel", onWheel as EventListener, { capture: true });
    };
  }, [chartEpoch]);

  useEffect(() => {
    visibleFeaturesRef.current = visibleFeatures;
  }, [visibleFeatures]);

  const effectiveVisible = useCallback(
    (key: string): boolean => {
      const features = visibleFeaturesRef.current;
      const direct = features[key];
      const visible = direct === undefined ? true : direct;
      const parentKey = parentBySubKey[key];
      if (!parentKey) return visible;
      const parentVisible = features[parentKey];
      return (parentVisible === undefined ? true : parentVisible) && visible;
    },
    [parentBySubKey]
  );

  const updateReplayMask = useCallback(() => {
    if (!replayEnabled || replayFocusTime == null) {
      setReplayMaskX(null);
      return;
    }
    const chart = chartRef.current;
    if (!chart) return;
    const coord = chart.timeScale().timeToCoordinate(replayFocusTime as UTCTimestamp);
    if (coord == null || Number.isNaN(coord)) {
      setReplayMaskX(null);
      return;
    }
    const widthPx = containerRef.current?.clientWidth ?? null;
    const clamped = widthPx != null ? Math.max(0, Math.min(coord, widthPx)) : coord;
    setReplayMaskX(clamped);
  }, [replayEnabled, replayFocusTime]);

  useEffect(() => {
    updateReplayMask();
  }, [height, replayEnabled, replayFocusTime, updateReplayMask, width]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const timeScale = chart.timeScale();

    const update = () => {
      const spacing = timeScale.options().barSpacing;
      setBarSpacing((prev) => (prev === spacing ? prev : spacing));
      updateReplayMask();
    };

    update();
    const handler = () => update();
    timeScale.subscribeVisibleLogicalRangeChange(handler);
    return () => timeScale.unsubscribeVisibleLogicalRangeChange(handler);
  }, [chartEpoch, updateReplayMask]);

  const syncMarkers = useCallback(() => {
    const markers = [...pivotMarkersRef.current, ...anchorSwitchMarkersRef.current, ...entryMarkersRef.current];
    markersApiRef.current?.setMarkers(markers);
    setPivotCount(pivotMarkersRef.current.length);
  }, []);

  const applyOverlayDelta = useCallback((delta: OverlayLikeDeltaV1) => {
    const patch = Array.isArray(delta.instruction_catalog_patch) ? delta.instruction_catalog_patch : [];
    for (const p of patch) {
      if (!p || typeof p !== "object") continue;
      if (typeof p.instruction_id !== "string" || !p.instruction_id) continue;
      overlayCatalogRef.current.set(p.instruction_id, p);
    }
    overlayActiveIdsRef.current = new Set(Array.isArray(delta.active_ids) ? delta.active_ids : []);

    const nextVersion =
      delta.next_cursor && typeof delta.next_cursor.version_id === "number" && Number.isFinite(delta.next_cursor.version_id)
        ? Math.max(0, Math.floor(delta.next_cursor.version_id))
        : null;
    if (nextVersion != null) overlayCursorVersionRef.current = nextVersion;
  }, []);

  const fetchOverlayLikeDelta = useCallback(
    async (params: { seriesId: string; cursorVersionId: number; windowCandles: number }): Promise<OverlayLikeDeltaV1> => {
      const delta = await fetchDrawDelta(params);
      return {
        active_ids: Array.isArray(delta.active_ids) ? delta.active_ids : [],
        instruction_catalog_patch: Array.isArray(delta.instruction_catalog_patch) ? delta.instruction_catalog_patch : [],
        next_cursor: { version_id: delta.next_cursor?.version_id ?? 0 }
      };
    },
    []
  );

  const rebuildPivotMarkersFromOverlay = useCallback(() => {
    const showPivotMajor = effectiveVisible("pivot.major");
    const showPivotMinor = effectiveVisible("pivot.minor");
    const want = new Set<string>();
    if (showPivotMajor) want.add("pivot.major");
    if (showPivotMinor) want.add("pivot.minor");

    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const next: Array<SeriesMarker<Time>> = [];
    if (minTime != null && maxTime != null && want.size > 0) {
      const ids = Array.from(overlayActiveIdsRef.current);
      for (const id of ids) {
        const item = overlayCatalogRef.current.get(id);
        if (!item || item.kind !== "marker") continue;

        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const feature = String(def["feature"] ?? "");
        if (!want.has(feature)) continue;

        const t = Number(def["time"]);
        if (!Number.isFinite(t)) continue;
        if (t < minTime || t > maxTime) continue;

        const position = def["position"] === "aboveBar" || def["position"] === "belowBar" ? def["position"] : null;
        const rawShape =
          def["shape"] === "circle" ||
          def["shape"] === "square" ||
          def["shape"] === "arrowUp" ||
          def["shape"] === "arrowDown"
            ? def["shape"]
            : null;
        const color = typeof def["color"] === "string" ? def["color"] : null;
        const rawText = typeof def["text"] === "string" ? def["text"] : "";
        const sizeRaw = Number(def["size"]);

        // Pivot marker style normalization (backward compatible with legacy overlay defs).
        // - major: never show "P" label
        // - minor: always render as a smaller circle dot than major
        const isPivotMajor = feature === "pivot.major";
        const isPivotMinor = feature === "pivot.minor";
        const text = isPivotMajor || isPivotMinor ? "" : rawText;
        const shape = isPivotMinor ? "circle" : rawShape;
        const sizeDefault = isPivotMinor ? 0.5 : 1.0;
        const size =
          isPivotMinor
            ? 0.5
            : Number.isFinite(sizeRaw) && sizeRaw > 0
              ? sizeRaw
              : sizeDefault;

        if (!position || !shape || !color) continue;

        next.push({ time: t as UTCTimestamp, position, color, shape, text, size });
      }
    }

    next.sort((a, b) => Number(a.time) - Number(b.time));
    pivotMarkersRef.current = next;
  }, [effectiveVisible]);

  const rebuildAnchorSwitchMarkersFromOverlay = useCallback(() => {
    const showAnchorSwitch = effectiveVisible("anchor.switch");
    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const next: Array<SeriesMarker<Time>> = [];
    if (showAnchorSwitch && minTime != null && maxTime != null) {
      const ids = Array.from(overlayActiveIdsRef.current);
      for (const id of ids) {
        const item = overlayCatalogRef.current.get(id);
        if (!item || item.kind !== "marker") continue;

        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const feature = String(def["feature"] ?? "");
        if (feature !== "anchor.switch") continue;

        const t = Number(def["time"]);
        if (!Number.isFinite(t)) continue;
        if (t < minTime || t > maxTime) continue;

        const position = def["position"] === "aboveBar" || def["position"] === "belowBar" ? def["position"] : null;
        const shape =
          def["shape"] === "circle" ||
          def["shape"] === "square" ||
          def["shape"] === "arrowUp" ||
          def["shape"] === "arrowDown"
            ? def["shape"]
            : null;
        const color = typeof def["color"] === "string" ? def["color"] : null;
        const text = typeof def["text"] === "string" ? def["text"] : "";
        const sizeRaw = Number(def["size"]);
        const size = Number.isFinite(sizeRaw) && sizeRaw > 0 ? sizeRaw : 1.0;
        if (!position || !shape || !color) continue;

        next.push({ time: t as UTCTimestamp, position, color, shape, text, size });
      }
    }

    next.sort((a, b) => Number(a.time) - Number(b.time));
    anchorSwitchMarkersRef.current = next;
    setAnchorSwitchCount(next.length);
  }, [effectiveVisible]);

  const rebuildPenPointsFromOverlay = useCallback(() => {
    if (!overlayActiveIdsRef.current.has("pen.confirmed")) {
      penPointsRef.current = [];
      return;
    }
    const item = overlayCatalogRef.current.get("pen.confirmed");
    if (!item || item.kind !== "polyline") {
      penPointsRef.current = [];
      return;
    }

    const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
    const points = def["points"];
    if (!Array.isArray(points) || points.length === 0) {
      penPointsRef.current = [];
      return;
    }

    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const out: Array<{ time: UTCTimestamp; value: number }> = [];
    for (const p of points) {
      if (!p || typeof p !== "object") continue;
      const rec = p as Record<string, unknown>;
      const t = Number(rec["time"]);
      const v = Number(rec["value"]);
      if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
      if (minTime != null && maxTime != null && (t < minTime || t > maxTime)) continue;
      out.push({ time: t as UTCTimestamp, value: v });
    }
    penPointsRef.current = out;
  }, []);

  const rebuildOverlayPolylinesFromOverlay = useCallback(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const range = candlesRef.current;
    const minTime = range.length > 0 ? (range[0]!.time as number) : null;
    const maxTime = range.length > 0 ? (range[range.length - 1]!.time as number) : null;

    const want = new Map<
      string,
      { points: Array<{ time: UTCTimestamp; value: number }>; color: string; lineWidth: LineWidth; lineStyle: LineStyle }
    >();
    const anchorTopLayerPaths: OverlayPath[] = [];
    let nextZhongshu = 0;
    let nextAnchor = 0;

    for (const id of overlayActiveIdsRef.current) {
      if (id === "pen.confirmed") continue;
      const item = overlayCatalogRef.current.get(id);
      if (!item || item.kind !== "polyline") continue;
      const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
      const feature = String(def["feature"] ?? "");
      if (!feature || !effectiveVisible(feature)) continue;

      const pointsRaw = def["points"];
      if (!Array.isArray(pointsRaw) || pointsRaw.length === 0) continue;
      const points: Array<{ time: UTCTimestamp; value: number }> = [];
      for (const p of pointsRaw) {
        if (!p || typeof p !== "object") continue;
        const rec = p as Record<string, unknown>;
        const t = Number(rec["time"]);
        const v = Number(rec["value"]);
        if (!Number.isFinite(t) || !Number.isFinite(v)) continue;
        if (minTime != null && maxTime != null && (t < minTime || t > maxTime)) continue;
        points.push({ time: t as UTCTimestamp, value: v });
      }
      if (points.length < 2) continue;

      const color = typeof def["color"] === "string" && def["color"] ? (def["color"] as string) : "#f59e0b";
      const lineWidthRaw = Number(def["lineWidth"]);
      const lineWidthBase = Number.isFinite(lineWidthRaw) && lineWidthRaw > 0 ? lineWidthRaw : 2;
      const lineWidth = Math.min(4, Math.max(1, Math.round(lineWidthBase))) as LineWidth;
      const lineStyleRaw = String(def["lineStyle"] ?? "");
      const lineStyle = lineStyleRaw === "dashed" ? LineStyle.Dashed : LineStyle.Solid;

      if (ENABLE_ANCHOR_TOP_LAYER && feature.startsWith("anchor.")) {
        anchorTopLayerPaths.push({
          id,
          feature,
          points,
          color,
          lineWidth,
          lineStyle
        });
      } else {
        want.set(id, { points, color, lineWidth, lineStyle });
      }
      if (feature.startsWith("zhongshu.")) nextZhongshu += 1;
      if (feature.startsWith("anchor.")) nextAnchor += 1;
    }

    for (const [id, series] of overlayPolylineSeriesByIdRef.current.entries()) {
      if (want.has(id)) continue;
      chart.removeSeries(series);
      overlayPolylineSeriesByIdRef.current.delete(id);
    }

    for (const [id, item] of want.entries()) {
      let series = overlayPolylineSeriesByIdRef.current.get(id);
      if (!series) {
        series = chart.addSeries(LineSeries, {
          color: item.color,
          lineWidth: item.lineWidth,
          lineStyle: item.lineStyle,
          priceLineVisible: false,
          lastValueVisible: false
        });
        overlayPolylineSeriesByIdRef.current.set(id, series);
      } else {
        series.applyOptions({
          color: item.color,
          lineWidth: item.lineWidth,
          lineStyle: item.lineStyle,
          priceLineVisible: false,
          lastValueVisible: false
        });
      }
      series.setData(item.points);
    }

    anchorTopLayerPathsRef.current = anchorTopLayerPaths;
    setAnchorTopLayerPathCount(anchorTopLayerPaths.length);
    setZhongshuCount(nextZhongshu);
    setAnchorCount(nextAnchor);
    setOverlayPaintEpoch((v) => v + 1);
  }, [chartEpoch, effectiveVisible]);

  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const ensureCanvas = () => {
      let canvas = zhongshuRectCanvasRef.current;
      if (!canvas) {
        canvas = document.createElement("canvas");
        canvas.className = "pointer-events-none absolute inset-0 z-[5]";
        container.appendChild(canvas);
        zhongshuRectCanvasRef.current = canvas;
      } else if (canvas.parentElement !== container) {
        container.appendChild(canvas);
      }
      return canvas;
    };

    const resizeCanvas = (canvas: HTMLCanvasElement) => {
      const dpr = window.devicePixelRatio || 1;
      const widthPx = Math.max(1, Math.floor(container.clientWidth));
      const heightPx = Math.max(1, Math.floor(container.clientHeight));
      const nextWidth = Math.floor(widthPx * dpr);
      const nextHeight = Math.floor(heightPx * dpr);
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      canvas.style.width = `${widthPx}px`;
      canvas.style.height = `${heightPx}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return ctx;
    };

    const draw = () => {
      const canvas = ensureCanvas();
      const ctx = resizeCanvas(canvas);
      if (!ctx) return;
      ctx.clearRect(0, 0, container.clientWidth, container.clientHeight);

      const timeScale = chart.timeScale();
      const visible = timeScale.getVisibleRange();
      const visibleFrom = visible ? normalizeTimeToSec(visible.from as Time) : null;
      const visibleTo = visible ? normalizeTimeToSec(visible.to as Time) : null;
      const visibleFromX = visibleFrom != null ? timeScale.timeToCoordinate(visibleFrom as UTCTimestamp) : null;
      const visibleToX = visibleTo != null ? timeScale.timeToCoordinate(visibleTo as UTCTimestamp) : null;

      type Edge = { startTime: number; endTime: number; value: number };
      type RectSeed = {
        feature: string;
        top?: Edge;
        bottom?: Edge;
        entryDirection?: number;
      };
      const rectMap = new Map<string, RectSeed>();
      for (const instructionId of overlayActiveIdsRef.current) {
        const item = overlayCatalogRef.current.get(instructionId);
        if (!item || item.kind !== "polyline") continue;
        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const feature = String(def["feature"] ?? "");
        if (!(feature === "zhongshu.alive" || feature === "zhongshu.dead")) continue;
        if (!effectiveVisible(feature)) continue;
        const rawEntryDirection = Number(def["entryDirection"]);
        const entryDirection = Number.isFinite(rawEntryDirection) && rawEntryDirection !== 0 ? (rawEntryDirection > 0 ? 1 : -1) : 0;
        const isTop = instructionId.endsWith(":top");
        const isBottom = instructionId.endsWith(":bottom");
        if (!isTop && !isBottom) continue;
        const pointsRaw = def["points"];
        if (!Array.isArray(pointsRaw) || pointsRaw.length < 2) continue;
        const p0 = pointsRaw[0];
        const p1 = pointsRaw[pointsRaw.length - 1];
        if (!p0 || typeof p0 !== "object" || !p1 || typeof p1 !== "object") continue;
        const r0 = p0 as Record<string, unknown>;
        const r1 = p1 as Record<string, unknown>;
        const t0 = Number(r0["time"]);
        const t1 = Number(r1["time"]);
        const y0 = Number(r0["value"]);
        if (!Number.isFinite(t0) || !Number.isFinite(t1) || !Number.isFinite(y0)) continue;
        const edge: Edge = {
          startTime: Math.min(Math.floor(t0), Math.floor(t1)),
          endTime: Math.max(Math.floor(t0), Math.floor(t1)),
          value: y0
        };
        const key = isTop ? instructionId.slice(0, -4) : instructionId.slice(0, -7);
        const seed = rectMap.get(key) ?? { feature };
        if (isTop) seed.top = edge;
        else seed.bottom = edge;
        if (entryDirection !== 0) seed.entryDirection = entryDirection;
        rectMap.set(key, seed);
      }

      const clampTimeCoord = (t: number) => {
        let x = timeScale.timeToCoordinate(t as UTCTimestamp);
        if (x != null && Number.isFinite(x)) return x;
        if (visibleFrom == null || visibleTo == null) return null;
        if (t < visibleFrom && visibleFromX != null && Number.isFinite(visibleFromX)) return visibleFromX;
        if (t > visibleTo && visibleToX != null && Number.isFinite(visibleToX)) return visibleToX;
        return null;
      };

      for (const seed of rectMap.values()) {
        if (!seed.top || !seed.bottom) continue;
        const x0 = clampTimeCoord(Math.min(seed.top.startTime, seed.bottom.startTime));
        const x1 = clampTimeCoord(Math.max(seed.top.endTime, seed.bottom.endTime));
        const yTop = series.priceToCoordinate(seed.top.value);
        const yBottom = series.priceToCoordinate(seed.bottom.value);
        if (x0 == null || x1 == null || yTop == null || yBottom == null) continue;
        const left = Math.min(x0, x1);
        const right = Math.max(x0, x1);
        const top = Math.min(yTop, yBottom);
        const bottom = Math.max(yTop, yBottom);
        const width = Math.max(0, right - left);
        const height = Math.max(0, bottom - top);
        if (width <= 0 || height <= 0) continue;

        const isAlive = seed.feature === "zhongshu.alive";
        const entryDirection = seed.entryDirection ?? (isAlive ? 1 : -1);
        const isUpEntry = entryDirection >= 0;
        const fillColor = isAlive
          ? isUpEntry
            ? "rgba(22, 163, 74, 0.2)"
            : "rgba(220, 38, 38, 0.18)"
          : isUpEntry
            ? "rgba(74, 222, 128, 0.12)"
            : "rgba(248, 113, 113, 0.1)";
        const borderColor = isAlive
          ? isUpEntry
            ? "rgba(22, 163, 74, 0.72)"
            : "rgba(220, 38, 38, 0.72)"
          : isUpEntry
            ? "rgba(74, 222, 128, 0.58)"
            : "rgba(248, 113, 113, 0.58)";

        ctx.save();
        ctx.beginPath();
        ctx.rect(left, top, width, height);
        ctx.fillStyle = fillColor;
        ctx.fill();
        ctx.strokeStyle = borderColor;
        ctx.lineWidth = 1;
        ctx.setLineDash([]);
        ctx.stroke();
        ctx.restore();
      }
    };

    let rafId: number | null = null;
    const scheduleDraw = () => {
      if (rafId != null) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        draw();
      });
    };

    const ro = new ResizeObserver(() => scheduleDraw());
    ro.observe(container);
    const timeScale = chart.timeScale();
    const onRangeChange = () => scheduleDraw();
    const onLogicalRangeChange = () => scheduleDraw();
    timeScale.subscribeVisibleTimeRangeChange(onRangeChange);
    timeScale.subscribeVisibleLogicalRangeChange(onLogicalRangeChange);
    scheduleDraw();

    return () => {
      ro.disconnect();
      timeScale.unsubscribeVisibleTimeRangeChange(onRangeChange);
      timeScale.unsubscribeVisibleLogicalRangeChange(onLogicalRangeChange);
      if (rafId != null) window.cancelAnimationFrame(rafId);
    };
  }, [chartEpoch, chartRef, effectiveVisible, overlayPaintEpoch, seriesRef]);

  useEffect(() => {
    if (!ENABLE_ANCHOR_TOP_LAYER) return;

    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const ensureCanvas = () => {
      let canvas = anchorTopLayerCanvasRef.current;
      if (!canvas) {
        canvas = document.createElement("canvas");
        canvas.className = "pointer-events-none absolute inset-0 z-[8]";
        container.appendChild(canvas);
        anchorTopLayerCanvasRef.current = canvas;
      } else if (canvas.parentElement !== container) {
        container.appendChild(canvas);
      }
      return canvas;
    };

    const resizeCanvas = (canvas: HTMLCanvasElement) => {
      const dpr = window.devicePixelRatio || 1;
      const widthPx = Math.max(1, Math.floor(container.clientWidth));
      const heightPx = Math.max(1, Math.floor(container.clientHeight));
      const nextWidth = Math.floor(widthPx * dpr);
      const nextHeight = Math.floor(heightPx * dpr);
      if (canvas.width !== nextWidth || canvas.height !== nextHeight) {
        canvas.width = nextWidth;
        canvas.height = nextHeight;
      }
      canvas.style.width = `${widthPx}px`;
      canvas.style.height = `${heightPx}px`;
      const ctx = canvas.getContext("2d");
      if (!ctx) return null;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      return ctx;
    };

    const draw = () => {
      const canvas = ensureCanvas();
      const ctx = resizeCanvas(canvas);
      if (!ctx) return;
      ctx.clearRect(0, 0, container.clientWidth, container.clientHeight);

      const paths = anchorTopLayerPathsRef.current;
      if (!paths.length) return;

      const timeScale = chart.timeScale();
      const visible = timeScale.getVisibleRange();
      const visibleFrom = visible ? normalizeTimeToSec(visible.from as Time) : null;
      const visibleTo = visible ? normalizeTimeToSec(visible.to as Time) : null;
      const visibleFromX = visibleFrom != null ? timeScale.timeToCoordinate(visibleFrom as UTCTimestamp) : null;
      const visibleToX = visibleTo != null ? timeScale.timeToCoordinate(visibleTo as UTCTimestamp) : null;

      const clampTimeCoord = (t: number) => {
        let x = timeScale.timeToCoordinate(t as UTCTimestamp);
        if (x != null && Number.isFinite(x)) return x;
        if (visibleFrom == null || visibleTo == null) return null;
        if (t < visibleFrom && visibleFromX != null && Number.isFinite(visibleFromX)) return visibleFromX;
        if (t > visibleTo && visibleToX != null && Number.isFinite(visibleToX)) return visibleToX;
        return null;
      };

      const drawPath = (points: PenLinePoint[], style: { color: string; lineWidth: number; lineStyle: LineStyle; haloWidth: number }) => {
        if (points.length < 2) return;
        ctx.save();
        ctx.beginPath();
        let hasPoint = false;
        for (const point of points) {
          const x = clampTimeCoord(Number(point.time));
          const y = series.priceToCoordinate(point.value);
          if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) {
            hasPoint = false;
            continue;
          }
          if (!hasPoint) {
            ctx.moveTo(x, y);
            hasPoint = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
        if (!hasPoint) {
          ctx.restore();
          return;
        }
        const dashed = style.lineStyle === LineStyle.Dashed;
        ctx.lineJoin = "round";
        ctx.lineCap = "round";
        ctx.strokeStyle = "rgba(255,255,255,0.35)";
        ctx.lineWidth = style.haloWidth;
        ctx.setLineDash(dashed ? [6, 6] : []);
        ctx.stroke();
        ctx.strokeStyle = style.color;
        ctx.lineWidth = style.lineWidth;
        ctx.setLineDash(dashed ? [6, 6] : []);
        ctx.stroke();
        ctx.restore();
      };

      for (const item of paths) {
        if (!effectiveVisible(item.feature)) continue;
        const style = resolveAnchorTopLayerStyle(item);
        drawPath(item.points, style);
      }

      if (effectiveVisible("anchor.current")) {
        const highlightPoints = anchorPenPointsRef.current;
        if (highlightPoints && highlightPoints.length >= 2) {
          drawPath(highlightPoints, {
            color: "#f59e0b",
            lineWidth: anchorPenIsDashedRef.current ? 3 : 4,
            lineStyle: anchorPenIsDashedRef.current ? LineStyle.Dashed : LineStyle.Solid,
            haloWidth: anchorPenIsDashedRef.current ? 4 : 5
          });
        }
      }
    };

    let rafId: number | null = null;
    const scheduleDraw = () => {
      if (rafId != null) return;
      rafId = window.requestAnimationFrame(() => {
        rafId = null;
        draw();
      });
    };

    const ro = new ResizeObserver(() => scheduleDraw());
    ro.observe(container);
    const timeScale = chart.timeScale();
    const onRangeChange = () => scheduleDraw();
    const onLogicalRangeChange = () => scheduleDraw();
    timeScale.subscribeVisibleTimeRangeChange(onRangeChange);
    timeScale.subscribeVisibleLogicalRangeChange(onLogicalRangeChange);
    scheduleDraw();

    return () => {
      ro.disconnect();
      timeScale.unsubscribeVisibleTimeRangeChange(onRangeChange);
      timeScale.unsubscribeVisibleLogicalRangeChange(onLogicalRangeChange);
      if (rafId != null) window.cancelAnimationFrame(rafId);
    };
  }, [anchorHighlightEpoch, chartEpoch, chartRef, effectiveVisible, overlayPaintEpoch, seriesRef]);

  const applyPenAndAnchorFromFactorSlices = useCallback(
    (slices: GetFactorSlicesResponseV1) => {
      const anchor = slices.snapshots?.["anchor"];
      const pen = slices.snapshots?.["pen"];
      const candlesRange = candlesRef.current;
      const minTime = candlesRange.length > 0 ? (candlesRange[0]!.time as number) : null;
      const maxTime = candlesRange.length > 0 ? (candlesRange[candlesRange.length - 1]!.time as number) : null;

      const head = (anchor?.head ?? {}) as Record<string, unknown>;
      const cur = head["current_anchor_ref"];

      const pickRef = (v: unknown) => {
        if (!v || typeof v !== "object") return null;
        const d = v as Record<string, unknown>;
        const kind = d["kind"] === "candidate" || d["kind"] === "confirmed" ? (d["kind"] as string) : null;
        const st = Number(d["start_time"]);
        const et = Number(d["end_time"]);
        const dir = Number(d["direction"]);
        if (!kind || !Number.isFinite(st) || !Number.isFinite(et) || !Number.isFinite(dir)) return null;
        return { kind, start_time: Math.floor(st), end_time: Math.floor(et), direction: Math.floor(dir) };
      };

      const pickHeadPen = (v: unknown): { start_time: number; end_time: number; direction: number; points: PenLinePoint[] } | null => {
        if (!v || typeof v !== "object") return null;
        const d = v as Record<string, unknown>;
        const st = Math.floor(Number(d["start_time"]));
        const et = Math.floor(Number(d["end_time"]));
        const sp = Number(d["start_price"]);
        const ep = Number(d["end_price"]);
        const dir = Math.floor(Number(d["direction"]));
        if (!Number.isFinite(st) || !Number.isFinite(et) || !Number.isFinite(sp) || !Number.isFinite(ep) || !Number.isFinite(dir))
          return null;
        if (st <= 0 || et <= 0 || st >= et) return null;
        if (minTime != null && maxTime != null && (st < minTime || et > maxTime)) return null;
        return {
          start_time: st,
          end_time: et,
          direction: dir,
          points: [
            { time: st as UTCTimestamp, value: sp },
            { time: et as UTCTimestamp, value: ep }
          ]
        };
      };

      const setHighlight = (pts: PenLinePoint[] | null, opts?: { dashed?: boolean }) => {
        anchorPenPointsRef.current = pts;
        anchorPenIsDashedRef.current = Boolean(opts?.dashed);
      };

      const curRef = pickRef(cur);

      // Segment coloring: highlight the stable confirmed anchor when available.
      const confirmedHighlightKey =
        curRef?.kind === "confirmed" ? `pen:${curRef.start_time}:${curRef.end_time}:${curRef.direction}` : null;

      const confirmedPensRaw = (pen?.history as Record<string, unknown> | undefined)?.["confirmed"];
      const confirmedPens = Array.isArray(confirmedPensRaw)
        ? confirmedPensRaw.slice().sort((a, b) => {
            const aa = a && typeof a === "object" ? (a as Record<string, unknown>) : {};
            const bb = b && typeof b === "object" ? (b as Record<string, unknown>) : {};
            const stA = Math.floor(Number(aa["start_time"]));
            const stB = Math.floor(Number(bb["start_time"]));
            if (stA !== stB) return stA - stB;
            return Math.floor(Number(aa["end_time"])) - Math.floor(Number(bb["end_time"]));
          })
        : [];

      const confirmedLinePoints: PenLinePoint[] = [];
      const allSegments: Array<{ key: string; points: PenLinePoint[]; highlighted: boolean }> = [];
      for (const item of confirmedPens) {
        if (!item || typeof item !== "object") continue;
        const p = item as Record<string, unknown>;
        const st = Math.floor(Number(p["start_time"]));
        const et = Math.floor(Number(p["end_time"]));
        const sp = Number(p["start_price"]);
        const ep = Number(p["end_price"]);
        const dir = Math.floor(Number(p["direction"]));
        if (!Number.isFinite(st) || !Number.isFinite(et) || !Number.isFinite(sp) || !Number.isFinite(ep) || !Number.isFinite(dir)) continue;
        if (st <= 0 || et <= 0 || st >= et) continue;
        if (minTime != null && maxTime != null && (st < minTime || et > maxTime)) continue;
        const startPt: PenLinePoint = { time: st as UTCTimestamp, value: sp };
        const endPt: PenLinePoint = { time: et as UTCTimestamp, value: ep };
        if (!confirmedLinePoints.length || Number(confirmedLinePoints[confirmedLinePoints.length - 1]!.time) !== st) {
          confirmedLinePoints.push(startPt);
        }
        confirmedLinePoints.push(endPt);
        const key = `pen:${st}:${et}:${dir}`;
        allSegments.push({
          key,
          points: [startPt, endPt],
          highlighted: confirmedHighlightKey != null && key === confirmedHighlightKey
        });
      }
      penSegmentsRef.current = allSegments.slice(Math.max(0, allSegments.length - PEN_SEGMENT_RENDER_LIMIT));
      if (replayEnabled) penPointsRef.current = confirmedLinePoints;

      const penHead = (pen?.head ?? {}) as Record<string, unknown>;
      const extendingPen = pickHeadPen(penHead["extending"]);
      const candidatePen = pickHeadPen(penHead["candidate"]);
      replayPenPreviewPointsRef.current["pen.extending"] = replayEnabled && extendingPen ? extendingPen.points : [];
      replayPenPreviewPointsRef.current["pen.candidate"] = replayEnabled && candidatePen ? candidatePen.points : [];

      if (curRef?.kind === "candidate" && candidatePen) {
        if (
          candidatePen.start_time === curRef.start_time &&
          candidatePen.end_time === curRef.end_time &&
          candidatePen.direction === curRef.direction
        ) {
          setHighlight(candidatePen.points, { dashed: true });
        } else {
          setHighlight(null);
        }
      } else {
        // Confirmed anchor highlight: only draw a separate segment when we're NOT doing segmented pen coloring.
        if (!ENABLE_PEN_SEGMENT_COLOR && confirmedHighlightKey) {
          const hit = allSegments.find((s) => s.key === confirmedHighlightKey);
          if (hit) setHighlight(hit.points, { dashed: false });
          else setHighlight(null);
        } else {
          setHighlight(null);
        }
      }

      setAnchorHighlightEpoch((v) => v + 1);
    },
    [replayEnabled, setAnchorHighlightEpoch]
  );

  const fetchAndApplyAnchorHighlightAtTime = useCallback(
    async (t: number) => {
      const at = Math.max(0, Math.floor(t));
      if (at <= 0) return;
      factorPullPendingTimeRef.current = at;
      if (factorPullInFlightRef.current) return;
      factorPullInFlightRef.current = true;
      try {
        while (factorPullPendingTimeRef.current != null) {
          const next = factorPullPendingTimeRef.current;
          factorPullPendingTimeRef.current = null;
          if (lastFactorAtTimeRef.current === next) continue;
          const slices = await fetchFactorSlices({ seriesId, atTime: next, windowCandles: INITIAL_TAIL_LIMIT });
          lastFactorAtTimeRef.current = next;
          applyPenAndAnchorFromFactorSlices(slices);
          if (replayEnabled) setReplaySlices(slices);
        }
      } catch {
        // ignore (best-effort)
      } finally {
        factorPullInFlightRef.current = false;
      }
    },
    [applyPenAndAnchorFromFactorSlices, replayEnabled, seriesId, setReplaySlices]
  );

  const applyWorldFrame = useCallback(
    (frame: WorldStateV1) => {
      overlayCatalogRef.current.clear();
      overlayActiveIdsRef.current.clear();
      overlayCursorVersionRef.current = 0;

      const draw = frame.draw_state;
      applyOverlayDelta({
        active_ids: draw.active_ids ?? [],
        instruction_catalog_patch: draw.instruction_catalog_patch ?? [],
        next_cursor: { version_id: draw.next_cursor?.version_id ?? 0 }
      });

      rebuildPivotMarkersFromOverlay();
      rebuildAnchorSwitchMarkersFromOverlay();
      syncMarkers();
      rebuildPenPointsFromOverlay();
      rebuildOverlayPolylinesFromOverlay();
      setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
      if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
        penSeriesRef.current.setData(penPointsRef.current);
      }

      applyPenAndAnchorFromFactorSlices(frame.factor_slices);
    },
    [
      applyOverlayDelta,
      applyPenAndAnchorFromFactorSlices,
      effectiveVisible,
      rebuildOverlayPolylinesFromOverlay,
      rebuildPenPointsFromOverlay,
      rebuildPivotMarkersFromOverlay,
      rebuildAnchorSwitchMarkersFromOverlay,
      syncMarkers
    ]
  );

  const recomputeActiveIdsFromCatalog = useCallback((params: { cutoffTime: number; toTime: number }): string[] => {
    const out: string[] = [];
    for (const [id, item] of overlayCatalogRef.current.entries()) {
      if (!item) continue;
      if (item.kind === "marker") {
        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const t = Number(def["time"]);
        if (!Number.isFinite(t)) continue;
        if (t < params.cutoffTime || t > params.toTime) continue;
        out.push(id);
        continue;
      }
      if (item.kind === "polyline") {
        const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
        const pts = def["points"];
        if (!Array.isArray(pts) || pts.length === 0) continue;
        let ok = false;
        for (const p of pts) {
          if (!p || typeof p !== "object") continue;
          const t = Number((p as Record<string, unknown>)["time"]);
          if (!Number.isFinite(t)) continue;
          if (params.cutoffTime <= t && t <= params.toTime) {
            ok = true;
            break;
          }
        }
        if (!ok) continue;
        out.push(id);
      }
    }
    out.sort();
    return out;
  }, []);

  const toReplayCandle = useCallback((bar: ReplayKlineBarV1): Candle => {
    return {
      time: bar.time as UTCTimestamp,
      open: bar.open,
      high: bar.high,
      low: bar.low,
      close: bar.close
    };
  }, []);

  const sliceHistoryEventsById = useCallback((events: ReplayHistoryEventV1[], toEventId: number) => {
    if (!events.length || toEventId <= 0) return [];
    let lo = 0;
    let hi = events.length - 1;
    let idx = -1;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      const v = events[mid]!.event_id;
      if (v <= toEventId) {
        idx = mid;
        lo = mid + 1;
      } else {
        hi = mid - 1;
      }
    }
    if (idx < 0) return [];
    return events.slice(0, idx + 1);
  }, []);

  const buildReplayFactorSlices = useCallback(
    (params: {
      atTime: number;
      toEventId: number;
      historyEvents: ReplayHistoryEventV1[];
      headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
    }): GetFactorSlicesResponseV1 => {
      const aligned = Math.max(0, Math.floor(params.atTime));
      const candleId = `${seriesId}:${aligned}`;
      const historySlice = sliceHistoryEventsById(params.historyEvents, params.toEventId);
      const headForTime = params.headByTime[aligned] ?? {};

      const pivotMajor: Record<string, unknown>[] = [];
      const pivotMinor: Record<string, unknown>[] = [];
      const penConfirmed: Record<string, unknown>[] = [];
      const zhongshuDead: Record<string, unknown>[] = [];
      const anchorSwitches: Record<string, unknown>[] = [];

      for (const ev of historySlice) {
        const payload = ev.payload && typeof ev.payload === "object" ? (ev.payload as Record<string, unknown>) : {};
        if (ev.factor_name === "pivot" && ev.kind === "pivot.major") {
          pivotMajor.push(payload);
        } else if (ev.factor_name === "pivot" && ev.kind === "pivot.minor") {
          pivotMinor.push(payload);
        } else if (ev.factor_name === "pen" && ev.kind === "pen.confirmed") {
          penConfirmed.push(payload);
        } else if (ev.factor_name === "zhongshu" && ev.kind === "zhongshu.dead") {
          zhongshuDead.push(payload);
        } else if (ev.factor_name === "anchor" && ev.kind === "anchor.switch") {
          anchorSwitches.push(payload);
        }
      }

      const makeMeta = (factorName: string) => ({
        series_id: seriesId,
        epoch: 0,
        at_time: aligned,
        candle_id: candleId,
        factor_name: factorName
      });

      const snapshots: Record<string, { schema_version: number; history: Record<string, unknown>; head: Record<string, unknown>; meta: any }> =
        {};
      const factors: string[] = [];

      const pivotHead = headForTime["pivot"]?.head ?? {};
      if (pivotMajor.length || pivotMinor.length || (pivotHead && Object.keys(pivotHead).length)) {
        snapshots["pivot"] = {
          schema_version: 1,
          history: { major: pivotMajor, minor: pivotMinor },
          head: pivotHead,
          meta: makeMeta("pivot")
        };
        factors.push("pivot");
      }

      const penHead = headForTime["pen"]?.head ?? {};
      if (penConfirmed.length || (penHead && Object.keys(penHead).length)) {
        snapshots["pen"] = {
          schema_version: 1,
          history: { confirmed: penConfirmed },
          head: penHead,
          meta: makeMeta("pen")
        };
        factors.push("pen");
      }

      const zhongshuHead = headForTime["zhongshu"]?.head ?? {};
      if (zhongshuDead.length || (zhongshuHead && Object.keys(zhongshuHead).length)) {
        snapshots["zhongshu"] = {
          schema_version: 1,
          history: { dead: zhongshuDead },
          head: zhongshuHead,
          meta: makeMeta("zhongshu")
        };
        factors.push("zhongshu");
      }

      const anchorHead = headForTime["anchor"]?.head ?? {};
      if (anchorSwitches.length || (anchorHead && Object.keys(anchorHead).length)) {
        snapshots["anchor"] = {
          schema_version: 1,
          history: { switches: anchorSwitches },
          head: anchorHead,
          meta: makeMeta("anchor")
        };
        factors.push("anchor");
      }

      return {
        schema_version: 1,
        series_id: seriesId,
        at_time: aligned,
        candle_id: candleId,
        factors,
        snapshots: snapshots as GetFactorSlicesResponseV1["snapshots"]
      };
    },
    [seriesId, sliceHistoryEventsById]
  );

  const resolveReplayActiveIds = useCallback((window: ReplayWindowV1, targetIdx: number): string[] => {
    const checkpoints = window.draw_active_checkpoints ?? [];
    const diffs = window.draw_active_diffs ?? [];
    let base: string[] = [];
    let baseIdx = window.start_idx;
    for (const cp of checkpoints) {
      if (cp.at_idx > targetIdx) break;
      base = Array.isArray(cp.active_ids) ? cp.active_ids.slice() : [];
      baseIdx = cp.at_idx;
    }
    const active = new Set(base);
    for (const df of diffs) {
      if (df.at_idx <= baseIdx) continue;
      if (df.at_idx > targetIdx) break;
      for (const id of df.add_ids ?? []) active.add(id);
      for (const id of df.remove_ids ?? []) active.delete(id);
    }
    return Array.from(active).sort();
  }, []);

  const applyReplayOverlayAtTime = useCallback(
    (toTime: number) => {
      const patch = replayPatchRef.current;
      if (patch.length === 0) return;
      const lastApplied = replayPatchAppliedIdxRef.current > 0 ? patch[replayPatchAppliedIdxRef.current - 1] : null;
      if (lastApplied && lastApplied.visible_time > toTime) {
        overlayCatalogRef.current.clear();
        replayPatchAppliedIdxRef.current = 0;
      }
      let i = replayPatchAppliedIdxRef.current;
      for (; i < patch.length; i++) {
        const p = patch[i]!;
        if (p.visible_time > toTime) break;
        overlayCatalogRef.current.set(p.instruction_id, p);
      }
      replayPatchAppliedIdxRef.current = i;

      const tfSeconds = timeframeToSeconds(timeframe);
      const cutoffTime = tfSeconds ? Math.max(0, Math.floor(toTime - INITIAL_TAIL_LIMIT * tfSeconds)) : 0;
      overlayActiveIdsRef.current = new Set(recomputeActiveIdsFromCatalog({ cutoffTime, toTime }));
      const activeInstructions = Array.from(overlayActiveIdsRef.current)
        .map((id) => overlayCatalogRef.current.get(id))
        .filter(Boolean) as OverlayInstructionPatchItemV1[];
      setReplayDrawInstructions(activeInstructions);

      rebuildPivotMarkersFromOverlay();
      rebuildAnchorSwitchMarkersFromOverlay();
      rebuildPenPointsFromOverlay();
      rebuildOverlayPolylinesFromOverlay();
      if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
        penSeriesRef.current.setData(penPointsRef.current);
      }
      setPenPointCount(penPointsRef.current.length);
      syncMarkers();
    },
    [
      effectiveVisible,
      recomputeActiveIdsFromCatalog,
      rebuildOverlayPolylinesFromOverlay,
      rebuildPenPointsFromOverlay,
      rebuildPivotMarkersFromOverlay,
      rebuildAnchorSwitchMarkersFromOverlay,
      setReplayDrawInstructions,
      syncMarkers,
      timeframe
    ]
  );

  const applyReplayPackageWindow = useCallback(
    (bundle: {
      window: ReplayWindowV1;
      headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
      historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
    }, targetIdx: number) => {
      const window = bundle.window;
      if (replayWindowIndexRef.current !== window.window_index) {
        overlayCatalogRef.current.clear();
        const catalog = [...(window.draw_catalog_base ?? []), ...(window.draw_catalog_patch ?? [])];
        catalog.sort((a, b) => (a.version_id - b.version_id !== 0 ? a.version_id - b.version_id : a.visible_time - b.visible_time));
        for (const item of catalog) {
          overlayCatalogRef.current.set(item.instruction_id, item);
        }
        replayWindowIndexRef.current = window.window_index;
      }

      const activeIds = resolveReplayActiveIds(window, targetIdx);
      overlayActiveIdsRef.current = new Set(activeIds);
      const activeInstructions = activeIds
        .map((id) => overlayCatalogRef.current.get(id))
        .filter(Boolean) as OverlayInstructionPatchItemV1[];
      setReplayDrawInstructions(activeInstructions);
      rebuildPivotMarkersFromOverlay();
      rebuildAnchorSwitchMarkersFromOverlay();
      rebuildPenPointsFromOverlay();
      rebuildOverlayPolylinesFromOverlay();
      if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
        penSeriesRef.current.setData(penPointsRef.current);
      }
      setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
      syncMarkers();
      return activeIds;
    },
    [
      effectiveVisible,
      rebuildOverlayPolylinesFromOverlay,
      rebuildPenPointsFromOverlay,
      rebuildPivotMarkersFromOverlay,
      rebuildAnchorSwitchMarkersFromOverlay,
      resolveReplayActiveIds,
      setReplayDrawInstructions,
      setPenPointCount,
      syncMarkers
    ]
  );

  const requestReplayFrameAtTime = useCallback(
    async (atTime: number) => {
      const aligned = Math.max(0, Math.floor(atTime));
      if (!replayEnabled || aligned <= 0) return;
      if (replayFrameLatestTimeRef.current === aligned) return;
      replayFramePendingTimeRef.current = aligned;
      if (replayFramePullInFlightRef.current) return;

      replayFramePullInFlightRef.current = true;
      setReplayFrameLoading(true);
      setReplayFrameError(null);
      try {
        while (replayFramePendingTimeRef.current != null) {
          const next = replayFramePendingTimeRef.current;
          replayFramePendingTimeRef.current = null;
          const frame = await fetchWorldFrameAtTime({ seriesId, atTime: next, windowCandles: INITIAL_TAIL_LIMIT });
          if (!replayEnabled) break;
          replayFrameLatestTimeRef.current = next;
          setReplayFrame(frame);
          applyPenAndAnchorFromFactorSlices(frame.factor_slices);
          setReplaySlices(frame.factor_slices);
          setReplayCandle({
            candleId: frame.time.candle_id,
            atTime: frame.time.aligned_time,
            activeIds: frame.draw_state?.active_ids ?? []
          });
          const patch = Array.isArray(frame.draw_state?.instruction_catalog_patch)
            ? frame.draw_state.instruction_catalog_patch
            : [];
          setReplayDrawInstructions(patch);
        }
      } catch (e: unknown) {
        if (!replayEnabled) return;
        setReplayFrameError(e instanceof Error ? e.message : "Failed to load replay frame");
      } finally {
        if (replayEnabled) setReplayFrameLoading(false);
        replayFramePullInFlightRef.current = false;
      }
    },
    [
      applyPenAndAnchorFromFactorSlices,
      replayEnabled,
      seriesId,
      setReplayCandle,
      setReplayDrawInstructions,
      setReplayFrame,
      setReplayFrameError,
      setReplayFrameLoading,
      setReplaySlices
    ]
  );

  useEffect(() => {
    const series = seriesRef.current;
    if (!series) return;
    if (candles.length === 0) return;
    const last = candles[candles.length - 1]!;
    const prev = appliedRef.current;

    const isAppendOne = prev.len === candles.length - 1 && (prev.lastTime == null || (last.time as number) >= prev.lastTime);
    const isUpdateLast = prev.len === candles.length && prev.lastTime != null && (last.time as number) === prev.lastTime;

    const syncAll = () => {
      series.setData(candles);
      for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
        const period = isSmaKey(key);
        if (period != null) s.setData(buildSmaLineData(candles, period));
      }
      syncMarkers();
    };

    if (prev.len === 0) {
      syncAll();
      chartRef.current?.timeScale().fitContent();
      const chart = chartRef.current;
      if (chart) {
        const cur = chart.timeScale().options().barSpacing;
        const next = clampBarSpacing(cur, MAX_BAR_SPACING_ON_FIT_CONTENT);
        if (next !== cur) chart.applyOptions({ timeScale: { barSpacing: next } });
      }
    } else if (isAppendOne || isUpdateLast) {
      series.update(last);
      // Incremental SMA update.
      const idx = candles.length - 1;
      for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
        const period = isSmaKey(key);
        if (period == null) continue;
        const v = computeSmaAtIndex(candles, idx, period);
        if (v == null) continue;
        s.update({ time: last.time, value: v });
      }
      // Incremental entry marker update (derived from SMA 5/20).
      if (entryEnabledRef.current) {
        const f0 = computeSmaAtIndex(candles, idx - 1, 5);
        const s0 = computeSmaAtIndex(candles, idx - 1, 20);
        const f1 = computeSmaAtIndex(candles, idx, 5);
        const s1 = computeSmaAtIndex(candles, idx, 20);
        if (f0 != null && s0 != null && f1 != null && s1 != null && f0 <= s0 && f1 > s1) {
          entryMarkersRef.current = [
            ...entryMarkersRef.current,
            { time: last.time, position: "belowBar", color: "#22c55e", shape: "arrowUp", text: "ENTRY" }
          ];
          syncMarkers();
        }
      }
    } else {
      syncAll();
    }

    appliedRef.current = { len: candles.length, lastTime: last.time as number };
  }, [candles, chartEpoch]);

  useEffect(() => {
    candlesRef.current = candles;
  }, [candles]);

  useEffect(() => {
    const chart = chartRef.current;
    const candleSeries = seriesRef.current;
    if (!chart || !candleSeries) return;

    // --- SMA line series (toggle -> create/remove) ---
    const visibleSmaKeys = Object.keys(visibleFeatures)
      .filter((k) => isSmaKey(k) != null)
      .filter((k) => effectiveVisible(k));

    const want = new Set(visibleSmaKeys);
    for (const [key, s] of lineSeriesByKeyRef.current.entries()) {
      if (!want.has(key)) {
        chart.removeSeries(s);
        lineSeriesByKeyRef.current.delete(key);
      }
    }

    for (const key of want) {
      const period = isSmaKey(key)!;
      let s = lineSeriesByKeyRef.current.get(key);
      if (!s) {
        const color = key === "sma_5" ? "#60a5fa" : key === "sma_20" ? "#f59e0b" : "#a78bfa";
        s = chart.addSeries(LineSeries, { color, lineWidth: 2 });
        lineSeriesByKeyRef.current.set(key, s);
      }
      if (candlesRef.current.length > 0) s.setData(buildSmaLineData(candlesRef.current, period));
    }

    // --- Entry markers (toggle -> recompute/clear) ---
    const showEntry = effectiveVisible("signal.entry");
    if (!showEntry) {
      entryEnabledRef.current = false;
      entryMarkersRef.current = [];
    } else {
      entryEnabledRef.current = true;
      const data = candlesRef.current;
      const nextMarkers: Array<SeriesMarker<Time>> = [];
      for (let i = 0; i < data.length; i++) {
        const f0 = computeSmaAtIndex(data, i - 1, 5);
        const s0 = computeSmaAtIndex(data, i - 1, 20);
        const f1 = computeSmaAtIndex(data, i, 5);
        const s1 = computeSmaAtIndex(data, i, 20);
        if (f0 == null || s0 == null || f1 == null || s1 == null) continue;
        if (f0 <= s0 && f1 > s1) {
          nextMarkers.push({
            time: data[i]!.time,
            position: "belowBar",
            color: "#22c55e",
            shape: "arrowUp",
            text: "ENTRY"
          });
        }
      }
      entryMarkersRef.current = nextMarkers;
    }

    rebuildPivotMarkersFromOverlay();
    rebuildAnchorSwitchMarkersFromOverlay();
    rebuildOverlayPolylinesFromOverlay();

    // --- Pen confirmed line (toggle -> create/remove) ---
    const showPenConfirmed = effectiveVisible("pen.confirmed");
    const penPointTotal =
      ENABLE_PEN_SEGMENT_COLOR && !replayEnabled ? penSegmentsRef.current.length * 2 : penPointsRef.current.length;
    const clearReplayPenPreviewSeries = () => {
      for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
        const s = replayPenPreviewSeriesByFeatureRef.current[feature];
        if (s) chart.removeSeries(s);
        replayPenPreviewSeriesByFeatureRef.current[feature] = null;
      }
    };
    if (!showPenConfirmed) {
      if (penSeriesRef.current) {
        chart.removeSeries(penSeriesRef.current);
        penSeriesRef.current = null;
      }
      for (const s of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(s);
      penSegmentSeriesByKeyRef.current.clear();
      if (anchorPenSeriesRef.current) {
        chart.removeSeries(anchorPenSeriesRef.current);
        anchorPenSeriesRef.current = null;
      }
      clearReplayPenPreviewSeries();
    } else {
      if (ENABLE_PEN_SEGMENT_COLOR && !replayEnabled) {
        if (penSeriesRef.current) {
          chart.removeSeries(penSeriesRef.current);
          penSeriesRef.current = null;
        }
        const segs = penSegmentsRef.current;
        const want = new Set(segs.map((s) => s.key));
        for (const [k, s] of penSegmentSeriesByKeyRef.current.entries()) {
          if (!want.has(k)) {
            chart.removeSeries(s);
            penSegmentSeriesByKeyRef.current.delete(k);
          }
        }
        for (const seg of segs) {
          const color = seg.highlighted ? "#f59e0b" : "#ffffff";
          const lineWidth = 2;
          let s = penSegmentSeriesByKeyRef.current.get(seg.key);
          if (!s) {
            s = chart.addSeries(LineSeries, {
              color,
              lineWidth,
              lineStyle: LineStyle.Solid,
              priceLineVisible: false,
              lastValueVisible: false
            });
            penSegmentSeriesByKeyRef.current.set(seg.key, s);
          } else {
            s.applyOptions({ color, lineWidth, lineStyle: LineStyle.Solid, priceLineVisible: false, lastValueVisible: false });
          }
          s.setData(seg.points);
        }
      } else {
        for (const s of penSegmentSeriesByKeyRef.current.values()) chart.removeSeries(s);
        penSegmentSeriesByKeyRef.current.clear();
        if (!penSeriesRef.current) {
          penSeriesRef.current = chart.addSeries(LineSeries, {
            color: "#ffffff",
            lineWidth: 2,
            lineStyle: LineStyle.Solid,
            priceLineVisible: false,
            lastValueVisible: false
          });
        }
        penSeriesRef.current.applyOptions({
          lineStyle: LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: false
        });
        penSeriesRef.current.setData(penPointsRef.current);
      }

      const anchorPts = anchorPenPointsRef.current;
      if (ENABLE_ANCHOR_TOP_LAYER) {
        if (anchorPenSeriesRef.current) {
          chart.removeSeries(anchorPenSeriesRef.current);
          anchorPenSeriesRef.current = null;
        }
      } else if (!anchorPts || anchorPts.length < 2) {
        if (anchorPenSeriesRef.current) {
          chart.removeSeries(anchorPenSeriesRef.current);
          anchorPenSeriesRef.current = null;
        }
      } else {
        const lineStyle = anchorPenIsDashedRef.current ? LineStyle.Dashed : LineStyle.Solid;
        if (!anchorPenSeriesRef.current) {
          anchorPenSeriesRef.current = chart.addSeries(LineSeries, {
            color: "#f59e0b",
            lineWidth: 2,
            lineStyle,
            priceLineVisible: false,
            lastValueVisible: false
          });
        } else {
          anchorPenSeriesRef.current.applyOptions({ color: "#f59e0b", lineWidth: 2, lineStyle });
        }
        anchorPenSeriesRef.current.setData(anchorPts);
      }

      const previewDefs: Array<{ feature: ReplayPenPreviewFeature; lineStyle: LineStyle }> = [
        { feature: "pen.extending", lineStyle: LineStyle.Dashed },
        { feature: "pen.candidate", lineStyle: LineStyle.Dashed }
      ];
      for (const item of previewDefs) {
        const points = replayPenPreviewPointsRef.current[item.feature];
        const shouldShow = replayEnabled && effectiveVisible(item.feature) && points.length >= 2;
        const existing = replayPenPreviewSeriesByFeatureRef.current[item.feature];
        if (!shouldShow) {
          if (existing) chart.removeSeries(existing);
          replayPenPreviewSeriesByFeatureRef.current[item.feature] = null;
          continue;
        }
        if (!existing) {
          replayPenPreviewSeriesByFeatureRef.current[item.feature] = chart.addSeries(LineSeries, {
            color: "#ffffff",
            lineWidth: 2,
            lineStyle: item.lineStyle,
            priceLineVisible: false,
            lastValueVisible: false
          });
        } else {
          existing.applyOptions({
            color: "#ffffff",
            lineWidth: 2,
            lineStyle: item.lineStyle,
            priceLineVisible: false,
            lastValueVisible: false
          });
        }
        replayPenPreviewSeriesByFeatureRef.current[item.feature]?.setData(points);
      }
    }

    setPenPointCount(penPointTotal);
    syncMarkers();
  }, [
    anchorHighlightEpoch,
    chartEpoch,
    effectiveVisible,
    replayEnabled,
    rebuildOverlayPolylinesFromOverlay,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    seriesId,
    syncMarkers,
    visibleFeatures
  ]);

  useEffect(() => {
    if (replayPackageEnabled) return;
    if (replayEnabled && replayPrepareStatus !== "ready") return;
    let isActive = true;
    let ws: WebSocket | null = null;

    async function run() {
      try {
        const chart = chartRef.current;
        setCandles([]);
        candlesRef.current = [];
        lastWsCandleTimeRef.current = null;
        setLastWsCandleTime(null);
        appliedRef.current = { len: 0, lastTime: null };
        pivotMarkersRef.current = [];
        anchorSwitchMarkersRef.current = [];
        overlayCatalogRef.current.clear();
        overlayActiveIdsRef.current.clear();
        overlayCursorVersionRef.current = 0;
        overlayPullInFlightRef.current = false;
        if (chart) {
          for (const series of overlayPolylineSeriesByIdRef.current.values()) chart.removeSeries(series);
          for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
            const series = replayPenPreviewSeriesByFeatureRef.current[feature];
            if (series) chart.removeSeries(series);
            replayPenPreviewSeriesByFeatureRef.current[feature] = null;
          }
        }
        overlayPolylineSeriesByIdRef.current.clear();
        setZhongshuCount(0);
        setAnchorCount(0);
        followPendingTimeRef.current = null;
        if (followTimerIdRef.current != null) {
          window.clearTimeout(followTimerIdRef.current);
          followTimerIdRef.current = null;
        }
        penSegmentsRef.current = [];
        anchorPenPointsRef.current = null;
        replayPenPreviewPointsRef.current["pen.extending"] = [];
        replayPenPreviewPointsRef.current["pen.candidate"] = [];
        factorPullPendingTimeRef.current = null;
        lastFactorAtTimeRef.current = null;
        setAnchorHighlightEpoch((v) => v + 1);
        setPivotCount(0);
        setAnchorSwitchCount(0);
        setPenPointCount(0);
        setError(null);
        worldFrameHealthyRef.current = ENABLE_WORLD_FRAME;
        let cursor = 0;

        // Initial: load tail (latest N).
        const initial = await fetchCandles({ seriesId, limit: INITIAL_TAIL_LIMIT });
        if (!isActive) return;
        logDebugEvent({
          pipe: "read",
          event: "read.http.market_candles_result",
          series_id: seriesId,
          level: "info",
          message: "initial candles loaded",
          data: { count: initial.candles.length }
        });
        if (initial.candles.length > 0) {
          if (replayEnabled) {
            logDebugEvent({
              pipe: "read",
              event: "read.replay.load_initial",
              series_id: seriesId,
              level: "info",
              message: "replay initial load",
              data: { count: initial.candles.length }
            });
            replayAllCandlesRef.current = initial.candles;
            replayPatchRef.current = [];
            replayPatchAppliedIdxRef.current = 0;
            overlayCatalogRef.current.clear();
            overlayActiveIdsRef.current.clear();
            overlayCursorVersionRef.current = 0;
            replayFrameLatestTimeRef.current = null;
            const endTime = replayPreparedAlignedTime ?? (initial.candles[initial.candles.length - 1]!.time as number);
            try {
              const draw = await fetchDrawDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT, atTime: endTime });
              if (!isActive) return;
              const raw = Array.isArray(draw.instruction_catalog_patch) ? draw.instruction_catalog_patch : [];
              replayPatchRef.current = raw
                .slice()
                .sort((a, b) => (a.visible_time - b.visible_time !== 0 ? a.visible_time - b.visible_time : a.version_id - b.version_id));
            } catch {
              replayPatchRef.current = [];
            }

            candlesRef.current = initial.candles;
            setCandles(initial.candles);
            setReplayTotal(initial.candles.length);
            setReplayPlaying(false);
            const lastIdx = Math.max(0, initial.candles.length - 1);
            setReplayIndex(lastIdx);
            return;
          }

          candlesRef.current = initial.candles;
          setCandles(initial.candles);
          cursor = initial.candles[initial.candles.length - 1]!.time as number;
        }

        // No HTTP catchup probe: WS subscribe catchup + gap handling covers the race window.

        const loadWorldFrameLive = async () => {
          const retryLimit = 6;
          const retryDelayMs = 200;
          let lastError: unknown = null;
          for (let attempt = 0; attempt <= retryLimit; attempt += 1) {
            try {
              return await fetchWorldFrameLive({ seriesId, windowCandles: INITIAL_TAIL_LIMIT });
            } catch (err) {
              lastError = err;
              const msg = err instanceof Error ? err.message : "";
              const status = msg.startsWith("HTTP ") ? Number(msg.replace("HTTP ", "")) : null;
              if (status !== 409) throw err;
              await new Promise((resolve) => window.setTimeout(resolve, retryDelayMs));
            }
          }
          if (lastError) throw lastError;
          return null;
        };

        const applyOverlayBaseline = async () => {
          const delta = await fetchOverlayLikeDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT });
          if (!isActive) return;
          applyOverlayDelta(delta);
          rebuildPivotMarkersFromOverlay();
          syncMarkers();
          rebuildPenPointsFromOverlay();
          setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
          if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
            penSeriesRef.current.setData(penPointsRef.current);
          }
          if (cursor > 0) {
            void fetchAndApplyAnchorHighlightAtTime(cursor);
          }
        };

        // Initial world frame (preferred) or overlay delta (legacy).
        try {
          if (ENABLE_WORLD_FRAME && !replayEnabled && worldFrameHealthyRef.current) {
            const frame = await loadWorldFrameLive();
            if (!isActive) return;
            if (frame) {
              applyWorldFrame(frame);
            } else {
              worldFrameHealthyRef.current = false;
              await applyOverlayBaseline();
            }
          } else {
            await applyOverlayBaseline();
          }
        } catch {
          worldFrameHealthyRef.current = false;
          try {
            await applyOverlayBaseline();
          } catch {
            // ignore overlay/frame errors (best-effort)
          }
        }

        const FOLLOW_DEBOUNCE_MS = 1000;

        function scheduleOverlayFollow(t: number) {
          followPendingTimeRef.current = Math.max(followPendingTimeRef.current ?? 0, t);
          if (!isActive) return;
          if (overlayPullInFlightRef.current) return;
          if (followTimerIdRef.current != null) return;
          followTimerIdRef.current = window.setTimeout(() => {
            followTimerIdRef.current = null;
            const next = followPendingTimeRef.current;
            followPendingTimeRef.current = null;
            if (next == null || !isActive) return;
            runOverlayFollowNow(next);
          }, FOLLOW_DEBOUNCE_MS);
        }

        function runOverlayFollowNow(t: number) {
          if (!isActive) return;
          if (overlayPullInFlightRef.current) {
            followPendingTimeRef.current = Math.max(followPendingTimeRef.current ?? 0, t);
            return;
          }
          overlayPullInFlightRef.current = true;

          if (ENABLE_WORLD_FRAME && !replayEnabled && worldFrameHealthyRef.current) {
            const afterId = overlayCursorVersionRef.current;
            void pollWorldDelta({ seriesId, afterId, windowCandles: INITIAL_TAIL_LIMIT })
              .then((resp) => {
                if (!isActive) return;
                const rec = resp.records?.[0];
                if (rec?.draw_delta) {
                  applyOverlayDelta({
                    active_ids: rec.draw_delta.active_ids ?? [],
                    instruction_catalog_patch: rec.draw_delta.instruction_catalog_patch ?? [],
                    next_cursor: { version_id: rec.draw_delta.next_cursor?.version_id ?? afterId }
                  });
                  rebuildPivotMarkersFromOverlay();
                  rebuildAnchorSwitchMarkersFromOverlay();
                  rebuildOverlayPolylinesFromOverlay();
                  syncMarkers();
                  rebuildPenPointsFromOverlay();
                  setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
                  if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                    penSeriesRef.current.setData(penPointsRef.current);
                  }
                }
                if (rec?.factor_slices) {
                  applyPenAndAnchorFromFactorSlices(rec.factor_slices);
                } else {
                  void fetchAndApplyAnchorHighlightAtTime(t);
                }
              })
              .catch(() => {
                worldFrameHealthyRef.current = false;
              })
              .finally(() => {
                overlayPullInFlightRef.current = false;
                const pending = followPendingTimeRef.current;
                followPendingTimeRef.current = null;
                if (pending != null && isActive) scheduleOverlayFollow(pending);
              });
            return;
          }

          const cur = overlayCursorVersionRef.current;
          void fetchOverlayLikeDelta({ seriesId, cursorVersionId: cur, windowCandles: INITIAL_TAIL_LIMIT })
            .then((delta) => {
              if (!isActive) return;
              applyOverlayDelta(delta);
              rebuildPivotMarkersFromOverlay();
              rebuildAnchorSwitchMarkersFromOverlay();
              rebuildOverlayPolylinesFromOverlay();
              syncMarkers();
              rebuildPenPointsFromOverlay();
              if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                penSeriesRef.current.setData(penPointsRef.current);
              }
              setPenPointCount(ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length);
            })
            .catch(() => {
              // ignore
            })
            .finally(() => {
              overlayPullInFlightRef.current = false;
              const pending = followPendingTimeRef.current;
              followPendingTimeRef.current = null;
              if (pending != null && isActive) scheduleOverlayFollow(pending);
            });

          void fetchAndApplyAnchorHighlightAtTime(t);
        }
        ws = openMarketWs({
          since: cursor > 0 ? cursor : null,
          isActive: () => isActive,
          onCandlesBatch: (msg) => {
            const last = msg.candles.length > 0 ? msg.candles[msg.candles.length - 1] : null;
            const t = last ? last.candle_time : null;
            if (t != null) {
              lastWsCandleTimeRef.current = t;
              setLastWsCandleTime(t);
            }

            setCandles((prev) => {
              const next = mergeCandlesWindow(prev, msg.candles.map(toChartCandle), INITIAL_TAIL_LIMIT);
              candlesRef.current = next;
              return next;
            });

            if (t != null) {
              logDebugEvent({
                pipe: "read",
                event: "read.ws.market_candles_batch",
                series_id: seriesId,
                level: "info",
                message: "ws candles batch",
                data: { count: msg.candles.length, last_time: t }
              });
            }

            if (t != null) scheduleOverlayFollow(t);
          },
          onSystem: (msg) => {
            if (msg.event !== "factor.rebuild") return;
            showToast(msg.message || "因子已自动重算");
            logDebugEvent({
              pipe: "read",
              event: "read.ws.system.factor_rebuild",
              series_id: seriesId,
              level: "warn",
              message: msg.message || "factor rebuild",
              data: msg.data
            });
          },
          onCandleForming: (msg) => {
            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandleWindow(candlesRef.current, next, INITIAL_TAIL_LIMIT);
            setCandles((prev) => mergeCandleWindow(prev, next, INITIAL_TAIL_LIMIT));
          },
          onCandleClosed: (msg) => {
            const t = msg.candle.candle_time;
            lastWsCandleTimeRef.current = t;
            setLastWsCandleTime(t);

            const next = toChartCandle(msg.candle);
            candlesRef.current = mergeCandleWindow(candlesRef.current, next, INITIAL_TAIL_LIMIT);
            setCandles((prev) => mergeCandleWindow(prev, next, INITIAL_TAIL_LIMIT));
            logDebugEvent({
              pipe: "read",
              event: "read.ws.market_candle_closed",
              series_id: seriesId,
              level: "info",
              message: "ws candle_closed",
              data: { candle_time: t }
            });
            scheduleOverlayFollow(t);
          },
          onGap: (msg) => {
            logDebugEvent({
              pipe: "read",
              event: "read.ws.market_gap",
              series_id: seriesId,
              level: "warn",
              message: "ws gap",
              data: {
                expected_next_time: msg.expected_next_time ?? null,
                actual_time: msg.actual_time ?? null
              }
            });
            const tfSeconds = timeframeToSeconds(timeframe);
            const expectedNextTime =
              typeof msg.expected_next_time === "number" && Number.isFinite(msg.expected_next_time)
                ? Math.max(0, Math.trunc(msg.expected_next_time))
                : null;
            const tfStep = tfSeconds != null ? Math.max(1, tfSeconds) : 60;
            const gapSince =
              expectedNextTime != null
                ? Math.max(0, expectedNextTime - tfStep)
                : null;
            const last = candlesRef.current[candlesRef.current.length - 1];
            const fallbackSince = last != null ? (last.time as number) : null;
            const since = gapSince ?? fallbackSince;
            const fetchParams = since != null ? ({ seriesId, since, limit: 5000 } as const) : ({ seriesId, limit: INITIAL_TAIL_LIMIT } as const);

            void fetchCandles(fetchParams).then(({ candles: chunk }) => {
              if (!isActive) return;
              if (chunk.length === 0) return;
              setCandles((prev) => {
                const next = mergeCandlesWindow(prev, chunk, INITIAL_TAIL_LIMIT);
                candlesRef.current = next;
                return next;
              });
            });

            overlayCatalogRef.current.clear();
            overlayActiveIdsRef.current.clear();
            overlayCursorVersionRef.current = 0;
            anchorPenPointsRef.current = null;
            replayPenPreviewPointsRef.current["pen.extending"] = [];
            replayPenPreviewPointsRef.current["pen.candidate"] = [];
            factorPullPendingTimeRef.current = null;
            setAnchorHighlightEpoch((v) => v + 1);
            lastFactorAtTimeRef.current = null;
            if (ENABLE_WORLD_FRAME && !replayEnabled && worldFrameHealthyRef.current) {
              void loadWorldFrameLive()
                .then((frame) => {
                  if (!isActive) return;
                  if (!frame) {
                    worldFrameHealthyRef.current = false;
                    return;
                  }
                  applyWorldFrame(frame);
                })
                .catch(() => {
                  worldFrameHealthyRef.current = false;
                });
            } else {
              void fetchOverlayLikeDelta({ seriesId, cursorVersionId: 0, windowCandles: INITIAL_TAIL_LIMIT })
                .then((delta) => {
                  if (!isActive) return;
                  applyOverlayDelta(delta);
                  rebuildPivotMarkersFromOverlay();
                  rebuildAnchorSwitchMarkersFromOverlay();
                  syncMarkers();
                  rebuildPenPointsFromOverlay();
                  if (effectiveVisible("pen.confirmed") && penSeriesRef.current) {
                    penSeriesRef.current.setData(penPointsRef.current);
                  }
                  setPenPointCount(
                    ENABLE_PEN_SEGMENT_COLOR ? penSegmentsRef.current.length * 2 : penPointsRef.current.length
                  );
                })
                .catch(() => {
                  // ignore
                });
              if (last && last.time != null) {
                void fetchAndApplyAnchorHighlightAtTime(last.time as number);
              }
            }
          },
          onSocketError: () => {
            if (!isActive) return;
            setError("WS error");
          }
        });
      } catch (e: unknown) {
        if (!isActive) return;
        setError(e instanceof Error ? e.message : "Failed to load market candles");
      }
    }

    void run();

    return () => {
      isActive = false;
      if (followTimerIdRef.current != null) {
        window.clearTimeout(followTimerIdRef.current);
        followTimerIdRef.current = null;
      }
      ws?.close();
      setCandles([]);
    };
  }, [
    applyOverlayDelta,
    applyReplayOverlayAtTime,
    applyWorldFrame,
    effectiveVisible,
    fetchAndApplyAnchorHighlightAtTime,
    fetchOverlayLikeDelta,
    fetchWorldFrameAtTime,
    fetchWorldFrameLive,
    openMarketWs,
    requestReplayFrameAtTime,
    rebuildOverlayPolylinesFromOverlay,
    rebuildPenPointsFromOverlay,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    replayEnabled,
    replayPrepareStatus,
    replayPreparedAlignedTime,
    replayPackageEnabled,
    seriesId,
    setReplayFocusTime,
    setReplayIndex,
    setReplayPlaying,
    setReplayTotal,
    syncMarkers
  ]);

  useEffect(() => {
    if (!replayPackageEnabled) return;
    setCandles([]);
    candlesRef.current = [];
    replayAllCandlesRef.current = [];
    replayWindowIndexRef.current = null;
    pivotMarkersRef.current = [];
    overlayCatalogRef.current.clear();
    overlayActiveIdsRef.current.clear();
    overlayCursorVersionRef.current = 0;
    overlayPullInFlightRef.current = false;
    penSegmentsRef.current = [];
    anchorPenPointsRef.current = null;
    replayPenPreviewPointsRef.current["pen.extending"] = [];
    replayPenPreviewPointsRef.current["pen.candidate"] = [];
    factorPullPendingTimeRef.current = null;
    lastFactorAtTimeRef.current = null;
    setAnchorHighlightEpoch((v) => v + 1);
    setPivotCount(0);
    setPenPointCount(0);
    setError(null);
    replayPatchRef.current = [];
    replayPatchAppliedIdxRef.current = 0;
    setReplayIndex(0);
    setReplayPlaying(false);
    setReplayTotal(0);
    setReplayFocusTime(null);
    setReplayFrame(null);
    setReplaySlices(null);
    setReplayCandle({ candleId: null, atTime: null, activeIds: [] });
    setReplayDrawInstructions([]);
  }, [
    replayPackageEnabled,
    seriesId,
    setReplayCandle,
    setReplayDrawInstructions,
    setReplayFocusTime,
    setReplayFrame,
    setReplayIndex,
    setReplayPlaying,
    setReplaySlices,
    setReplayTotal
  ]);

  useReplayPackageWindowSync({
    enabled: replayPackageEnabled,
    status: replayPackageStatus,
    metadata: replayPackageMeta,
    windows: replayPackageWindows,
    historyEvents: replayPackageHistory,
    ensureWindowRange: replayEnsureWindowRange,
    replayIndex,
    replayFocusTime,
    seriesId,
    replayAllCandlesRef,
    lastFactorAtTimeRef,
    candlesRef,
    toReplayCandle,
    applyReplayPackageWindow,
    buildReplayFactorSlices,
    applyPenAndAnchorFromFactorSlices,
    setReplayTotal,
    setReplayIndex,
    setReplayFocusTime,
    setReplaySlices,
    setReplayCandle,
    setCandles
  });

  useEffect(() => {
    if (!replayEnabled) return;
    if (replayPackageEnabled) return;
    const all = replayAllCandlesRef.current as Candle[];
    if (all.length === 0) return;
    const clamped = Math.max(0, Math.min(replayIndex, replayTotal - 1));
    if (clamped !== replayIndex) {
      setReplayIndex(clamped);
      return;
    }
    const time = all[clamped]!.time as number;
    setReplayFocusTime(time);
    applyReplayOverlayAtTime(time);
    void fetchAndApplyAnchorHighlightAtTime(time);
    void requestReplayFrameAtTime(time);
  }, [
    applyReplayOverlayAtTime,
    fetchAndApplyAnchorHighlightAtTime,
    replayEnabled,
    replayIndex,
    replayPackageEnabled,
    replayTotal,
    requestReplayFrameAtTime,
    setReplayFocusTime,
    setReplayIndex
  ]);

  return (
    <div
      ref={wheelGuardRef}
      data-testid="chart-view"
      data-series-id={seriesId}
      data-candles-len={String(candles.length)}
      data-last-time={candles.length ? String(candles[candles.length - 1]!.time) : ""}
      data-last-open={candles.length ? String(candles[candles.length - 1]!.open) : ""}
      data-last-high={candles.length ? String(candles[candles.length - 1]!.high) : ""}
      data-last-low={candles.length ? String(candles[candles.length - 1]!.low) : ""}
      data-last-close={candles.length ? String(candles[candles.length - 1]!.close) : ""}
      data-last-ws-candle-time={lastWsCandleTime != null ? String(lastWsCandleTime) : ""}
      data-chart-epoch={String(chartEpoch)}
      data-bar-spacing={barSpacing != null ? String(barSpacing) : ""}
      data-pivot-count={String(pivotCount)}
      data-pen-point-count={String(penPointCount)}
      data-zhongshu-count={String(zhongshuCount)}
      data-anchor-count={String(anchorCount)}
      data-anchor-switch-count={String(anchorSwitchCount)}
      data-anchor-on={anchorCount > 0 ? "1" : "0"}
      data-anchor-top-layer={ENABLE_ANCHOR_TOP_LAYER ? "1" : "0"}
      data-anchor-top-layer-path-count={String(anchorTopLayerPathCount)}
      data-replay-mode={replayEnabled ? "replay" : "live"}
      data-replay-index={String(replayIndex)}
      data-replay-total={String(replayTotal)}
      data-replay-focus-time={replayFocusTime != null ? String(replayFocusTime) : ""}
      data-replay-playing={replayPlaying ? "1" : "0"}
      className="relative h-full w-full"
      title={error ?? undefined}
    >
      <div
        ref={(el) => {
          containerRef.current = el;
          resizeRef(el);
        }}
        className="h-full w-full"
      />

      {replayEnabled && replayMaskX != null ? (
        <>
          <div
            data-testid="replay-mask"
            className="pointer-events-none absolute inset-y-0 right-0 z-10 bg-black/55"
            style={{ left: `${replayMaskX}px` }}
          />
          <div
            className="pointer-events-none absolute inset-y-0 z-20 w-px bg-amber-300/70"
            style={{ left: `${replayMaskX}px` }}
          />
        </>
      ) : null}

      {ENABLE_DRAW_TOOLS ? (
        <div className="pointer-events-none absolute inset-0 z-30">
          {/* Measure */}
          <MeasureTool
            enabled={activeChartTool === "measure"}
            containerRef={containerRef}
            candleTimesSec={candleTimesSecRef.current}
            startPoint={measureState.start}
            currentPoint={measureState.current}
            locked={measureState.locked}
          />

          {/* Positions */}
          {positionTools.map((tool) => (
            <PositionTool
              key={tool.id}
              chartRef={chartRef}
              seriesRef={seriesRef}
              containerRef={containerRef}
              candleTimesSec={candleTimesSecRef.current}
              tool={tool}
              isActive={activeToolId === tool.id}
              interactive={true}
              onUpdate={updatePositionTool}
              onRemove={removePositionTool}
              onSelect={selectTool}
              onInteractionLockChange={(locked) => {
                interactionLockRef.current.dragging = locked;
              }}
            />
          ))}

          {/* Fibs */}
          {fibTools.map((tool) => (
            <FibTool
              key={tool.id}
              chartRef={chartRef}
              seriesRef={seriesRef}
              containerRef={containerRef}
              candleTimesSec={candleTimesSecRef.current}
              tool={tool}
              isActive={activeToolId === tool.id}
              interactive={true}
              onUpdate={updateFibTool}
              onRemove={removeFibTool}
              onSelect={selectTool}
              onInteractionLockChange={(locked) => {
                interactionLockRef.current.dragging = locked;
              }}
            />
          ))}

          {/* Fib preview (creation second point) */}
          {fibPreviewTool ? (
            <FibTool
              key="__fib_preview__"
              chartRef={chartRef}
              seriesRef={seriesRef}
              containerRef={containerRef}
              candleTimesSec={candleTimesSecRef.current}
              tool={fibPreviewTool}
              isActive={false}
              interactive={false}
              onUpdate={() => {}}
              onRemove={() => {}}
              onSelect={() => {}}
            />
          ) : null}
        </div>
      ) : null}

      {error ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-red-500/30 bg-red-950/60 px-2 py-1 text-[11px] text-red-200">
          {error}
        </div>
      ) : candles.length === 0 ? (
        <div className="pointer-events-none absolute left-2 top-2 rounded border border-white/10 bg-black/40 px-2 py-1 text-[11px] text-white/70">
          Loading candles…
        </div>
      ) : null}

      {toastMessage ? (
        <div className="pointer-events-none absolute left-1/2 top-3 z-40 -translate-x-1/2 rounded-md border border-amber-300/35 bg-amber-500/15 px-3 py-1.5 text-[12px] text-amber-100 shadow-[0_6px_24px_rgba(0,0,0,0.35)]">
          {toastMessage}
        </div>
      ) : null}
    </div>
  );
}
