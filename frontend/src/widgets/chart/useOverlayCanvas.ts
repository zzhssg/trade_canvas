/**
 * Overlay canvas 渲染 hook — 管理 zhongshu 矩形和 anchor 顶层线条的 canvas 绘制。
 *
 * 从 ChartView 提取，封装 2 个独立 canvas 层:
 * 1. zhongshu 矩形层 (z-index 5) — 绘制 alive/dead 中枢的半透明填充矩形
 * 2. anchor 顶层线条层 (z-index 8) — 绘制 anchor.current/history 的高亮线条 + halo
 *
 * 两层均通过 RAF 调度绘制，订阅 chart timeScale 变化自动重绘。
 */
import { LineStyle, type IChartApi, type ISeriesApi, type UTCTimestamp, type Time } from "lightweight-charts";
import { useEffect, useRef, type MutableRefObject } from "react";

import { normalizeTimeToSec } from "./draw_tools/chartCoord";
import type { OverlayInstructionPatchItemV1 } from "./types";

type PenLinePoint = { time: UTCTimestamp; value: number };

export type { OverlayPath as OverlayCanvasPath };

type OverlayPath = {
  id: string;
  feature: string;
  points: PenLinePoint[];
  color: string;
  lineWidth: number;
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

/** 创建 canvas 并挂载到 container，若已存在则复用 */
function ensureCanvas(ref: MutableRefObject<HTMLCanvasElement | null>, container: HTMLElement, zIndex: number): HTMLCanvasElement {
  let canvas = ref.current;
  if (!canvas) {
    canvas = document.createElement("canvas");
    canvas.className = `pointer-events-none absolute inset-0 z-[${zIndex}]`;
    container.appendChild(canvas);
    ref.current = canvas;
  } else if (canvas.parentElement !== container) {
    container.appendChild(canvas);
  }
  return canvas;
}

/** 调整 canvas 尺寸并返回 2d context (已应用 DPR 缩放) */
function resizeCanvas(canvas: HTMLCanvasElement, container: HTMLElement): CanvasRenderingContext2D | null {
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
}

/** 订阅 chart timeScale 变化 + ResizeObserver，返回清理函数 */
function subscribeChartRedraw(chart: IChartApi, container: HTMLElement, draw: () => void): () => void {
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
  const handler = () => scheduleDraw();
  timeScale.subscribeVisibleTimeRangeChange(handler);
  timeScale.subscribeVisibleLogicalRangeChange(handler);
  scheduleDraw();

  return () => {
    ro.disconnect();
    timeScale.unsubscribeVisibleTimeRangeChange(handler);
    timeScale.unsubscribeVisibleLogicalRangeChange(handler);
    if (rafId != null) window.cancelAnimationFrame(rafId);
  };
}

export type UseOverlayCanvasParams = {
  chartRef: MutableRefObject<IChartApi | null>;
  seriesRef: MutableRefObject<ISeriesApi<"Candlestick"> | null>;
  containerRef: MutableRefObject<HTMLDivElement | null>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  anchorTopLayerPathsRef: MutableRefObject<OverlayPath[]>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  effectiveVisible: (key: string) => boolean;
  chartEpoch: number;
  overlayPaintEpoch: number;
  anchorHighlightEpoch: number;
  enableAnchorTopLayer: boolean;
};

/**
 * 管理 zhongshu 矩形 canvas 和 anchor 顶层线条 canvas 的渲染。
 * 返回 cleanup 函数供 chart onCleanup 回调使用。
 */
export function useOverlayCanvas(params: UseOverlayCanvasParams) {
  const {
    chartRef, seriesRef, containerRef,
    overlayActiveIdsRef, overlayCatalogRef,
    anchorTopLayerPathsRef, anchorPenPointsRef, anchorPenIsDashedRef,
    effectiveVisible,
    chartEpoch, overlayPaintEpoch, anchorHighlightEpoch,
    enableAnchorTopLayer,
  } = params;

  const zhongshuCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const anchorCanvasRef = useRef<HTMLCanvasElement | null>(null);

  // --- Zhongshu rect canvas ---
  useEffect(() => {
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const draw = () => {
      const canvas = ensureCanvas(zhongshuCanvasRef, container, 5);
      const ctx = resizeCanvas(canvas, container);
      if (!ctx) return;
      ctx.clearRect(0, 0, container.clientWidth, container.clientHeight);
      drawZhongshuRects(ctx, chart, series, container, overlayActiveIdsRef.current, overlayCatalogRef.current, effectiveVisible);
    };

    return subscribeChartRedraw(chart, container, draw);
  }, [chartEpoch, chartRef, effectiveVisible, overlayPaintEpoch, seriesRef, containerRef, overlayActiveIdsRef, overlayCatalogRef]);

  // --- Anchor top layer canvas ---
  useEffect(() => {
    if (!enableAnchorTopLayer) return;
    const chart = chartRef.current;
    const series = seriesRef.current;
    const container = containerRef.current;
    if (!chart || !series || !container) return;

    const draw = () => {
      const canvas = ensureCanvas(anchorCanvasRef, container, 8);
      const ctx = resizeCanvas(canvas, container);
      if (!ctx) return;
      ctx.clearRect(0, 0, container.clientWidth, container.clientHeight);
      drawAnchorTopLayer(ctx, chart, series, container, anchorTopLayerPathsRef.current, anchorPenPointsRef.current, anchorPenIsDashedRef.current, effectiveVisible);
    };

    return subscribeChartRedraw(chart, container, draw);
  }, [anchorHighlightEpoch, chartEpoch, chartRef, effectiveVisible, overlayPaintEpoch, seriesRef, containerRef, enableAnchorTopLayer, anchorTopLayerPathsRef, anchorPenPointsRef, anchorPenIsDashedRef]);

  /** 清理 canvas DOM 节点 (供 chart onCleanup 调用) */
  const cleanupCanvases = () => {
    for (const ref of [zhongshuCanvasRef, anchorCanvasRef]) {
      const canvas = ref.current;
      if (canvas?.parentElement) canvas.parentElement.removeChild(canvas);
      ref.current = null;
    }
  };

  return { cleanupCanvases };
}

// --- Pure drawing functions ---

function makeClampTimeCoord(chart: IChartApi) {
  const timeScale = chart.timeScale();
  const visible = timeScale.getVisibleRange();
  const visibleFrom = visible ? normalizeTimeToSec(visible.from as Time) : null;
  const visibleTo = visible ? normalizeTimeToSec(visible.to as Time) : null;
  const visibleFromX = visibleFrom != null ? timeScale.timeToCoordinate(visibleFrom as UTCTimestamp) : null;
  const visibleToX = visibleTo != null ? timeScale.timeToCoordinate(visibleTo as UTCTimestamp) : null;

  return (t: number): number | null => {
    const x = timeScale.timeToCoordinate(t as UTCTimestamp);
    if (x != null && Number.isFinite(x)) return x;
    if (visibleFrom == null || visibleTo == null) return null;
    if (t < visibleFrom && visibleFromX != null && Number.isFinite(visibleFromX)) return visibleFromX;
    if (t > visibleTo && visibleToX != null && Number.isFinite(visibleToX)) return visibleToX;
    return null;
  };
}

function drawZhongshuRects(
  ctx: CanvasRenderingContext2D,
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  container: HTMLElement,
  activeIds: Set<string>,
  catalog: Map<string, OverlayInstructionPatchItemV1>,
  effectiveVisible: (key: string) => boolean,
) {
  const clampTimeCoord = makeClampTimeCoord(chart);

  type Edge = { startTime: number; endTime: number; value: number };
  type RectSeed = { feature: string; top?: Edge; bottom?: Edge; entryDirection?: number };
  const rectMap = new Map<string, RectSeed>();

  for (const instructionId of activeIds) {
    const item = catalog.get(instructionId);
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
    const edge: Edge = { startTime: Math.min(Math.floor(t0), Math.floor(t1)), endTime: Math.max(Math.floor(t0), Math.floor(t1)), value: y0 };
    const key = isTop ? instructionId.slice(0, -4) : instructionId.slice(0, -7);
    const seed = rectMap.get(key) ?? { feature };
    if (isTop) seed.top = edge;
    else seed.bottom = edge;
    if (entryDirection !== 0) seed.entryDirection = entryDirection;
    rectMap.set(key, seed);
  }

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
    const w = Math.max(0, right - left);
    const h = Math.max(0, bottom - top);
    if (w <= 0 || h <= 0) continue;

    const isAlive = seed.feature === "zhongshu.alive";
    const ed = seed.entryDirection ?? (isAlive ? 1 : -1);
    const isUpEntry = ed >= 0;
    const fillColor = isAlive
      ? isUpEntry ? "rgba(22, 163, 74, 0.2)" : "rgba(220, 38, 38, 0.18)"
      : isUpEntry ? "rgba(74, 222, 128, 0.12)" : "rgba(248, 113, 113, 0.1)";
    const borderColor = isAlive
      ? isUpEntry ? "rgba(22, 163, 74, 0.72)" : "rgba(220, 38, 38, 0.72)"
      : isUpEntry ? "rgba(74, 222, 128, 0.58)" : "rgba(248, 113, 113, 0.58)";

    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, w, h);
    ctx.fillStyle = fillColor;
    ctx.fill();
    ctx.strokeStyle = borderColor;
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.stroke();
    ctx.restore();
  }
}

function drawAnchorTopLayer(
  ctx: CanvasRenderingContext2D,
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  _container: HTMLElement,
  paths: OverlayPath[],
  highlightPoints: PenLinePoint[] | null,
  highlightDashed: boolean,
  effectiveVisible: (key: string) => boolean,
) {
  if (!paths.length && !highlightPoints?.length) return;

  const clampTimeCoord = makeClampTimeCoord(chart);

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
      if (!hasPoint) { ctx.moveTo(x, y); hasPoint = true; }
      else ctx.lineTo(x, y);
    }
    if (!hasPoint) { ctx.restore(); return; }
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
    drawPath(item.points, resolveAnchorTopLayerStyle(item));
  }

  if (effectiveVisible("anchor.current") && highlightPoints && highlightPoints.length >= 2) {
    drawPath(highlightPoints, {
      color: "#f59e0b",
      lineWidth: highlightDashed ? 3 : 4,
      lineStyle: highlightDashed ? LineStyle.Dashed : LineStyle.Solid,
      haloWidth: highlightDashed ? 4 : 5,
    });
  }
}
