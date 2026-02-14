import { LineStyle, type IChartApi, type ISeriesApi, type Time, type UTCTimestamp } from "lightweight-charts";
import { normalizeTimeToSec } from "./draw_tools/chartCoord";
import type { OverlayInstructionPatchItemV1 } from "./types";

export type PenLinePoint = { time: UTCTimestamp; value: number };
export type OverlayPath = {
  id: string;
  feature: string;
  points: PenLinePoint[];
  color: string;
  lineWidth: number;
  lineStyle: LineStyle;
};
export type OverlayCanvasPath = OverlayPath;

type AnchorStyle = { color: string; lineWidth: number; lineStyle: LineStyle; haloWidth: number };
type Edge = { startTime: number; endTime: number; value: number };
type RectSeed = { feature: string; top?: Edge; bottom?: Edge; entryDirection?: number };

const resolveAnchorTopLayerStyle = (path: OverlayPath): AnchorStyle => {
  const baseWidth = Math.max(1, Number(path.lineWidth) || 1);
  if (path.feature === "anchor.current") {
    const lineWidth = Math.max(3, baseWidth + 1);
    return { color: "#f59e0b", lineWidth, lineStyle: path.lineStyle, haloWidth: lineWidth + 1 };
  }
  const lineWidth = Math.max(2.5, baseWidth + 0.5);
  if (path.feature === "anchor.history") return { color: "#3b82f6", lineWidth, lineStyle: path.lineStyle, haloWidth: lineWidth + 0.8 };
  return { color: path.color, lineWidth, lineStyle: path.lineStyle, haloWidth: lineWidth + 0.8 };
};

export function ensureCanvas(canvas: HTMLCanvasElement | null, container: HTMLElement, zIndex: number): HTMLCanvasElement {
  const zLayer = String(Math.max(0, Math.floor(zIndex)));
  if (!canvas) {
    const next = document.createElement("canvas");
    next.className = "pointer-events-none absolute inset-0";
    next.style.zIndex = zLayer;
    container.appendChild(next);
    return next;
  }
  canvas.style.zIndex = zLayer;
  if (canvas.parentElement !== container) container.appendChild(canvas);
  return canvas;
}

export function resizeCanvas(canvas: HTMLCanvasElement, container: HTMLElement): CanvasRenderingContext2D | null {
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

export function subscribeChartRedraw(chart: IChartApi, container: HTMLElement, draw: () => void): () => void {
  let rafId: number | null = null;
  const schedule = () => {
    if (rafId != null) return;
    rafId = window.requestAnimationFrame(() => {
      rafId = null;
      draw();
    });
  };
  const ro = new ResizeObserver(schedule);
  const timeScale = chart.timeScale();
  ro.observe(container);
  timeScale.subscribeVisibleTimeRangeChange(schedule);
  timeScale.subscribeVisibleLogicalRangeChange(schedule);
  schedule();
  return () => {
    ro.disconnect();
    timeScale.unsubscribeVisibleTimeRangeChange(schedule);
    timeScale.unsubscribeVisibleLogicalRangeChange(schedule);
    if (rafId != null) window.cancelAnimationFrame(rafId);
  };
}

function makeClampTimeCoord(chart: IChartApi) {
  const timeScale = chart.timeScale();
  const visible = timeScale.getVisibleRange();
  const from = visible ? normalizeTimeToSec(visible.from as Time) : null;
  const to = visible ? normalizeTimeToSec(visible.to as Time) : null;
  const fromX = from != null ? timeScale.timeToCoordinate(from as UTCTimestamp) : null;
  const toX = to != null ? timeScale.timeToCoordinate(to as UTCTimestamp) : null;
  return (t: number): number | null => {
    const x = timeScale.timeToCoordinate(t as UTCTimestamp);
    if (x != null && Number.isFinite(x)) return x;
    if (from == null || to == null) return null;
    if (t < from && fromX != null && Number.isFinite(fromX)) return fromX;
    if (t > to && toX != null && Number.isFinite(toX)) return toX;
    return null;
  };
}

function zhongshuPalette(isAlive: boolean, isUpEntry: boolean) {
  if (isAlive) return isUpEntry ? { fill: "rgba(22, 163, 74, 0.2)", border: "rgba(22, 163, 74, 0.72)" } : { fill: "rgba(220, 38, 38, 0.18)", border: "rgba(220, 38, 38, 0.72)" };
  return isUpEntry ? { fill: "rgba(74, 222, 128, 0.12)", border: "rgba(74, 222, 128, 0.58)" } : { fill: "rgba(248, 113, 113, 0.1)", border: "rgba(248, 113, 113, 0.58)" };
}

export function drawZhongshuRects(
  ctx: CanvasRenderingContext2D,
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  activeIds: Set<string>,
  catalog: Map<string, OverlayInstructionPatchItemV1>,
  effectiveVisible: (key: string) => boolean
) {
  const clampTimeCoord = makeClampTimeCoord(chart);
  const rectMap = new Map<string, RectSeed>();
  for (const instructionId of activeIds) {
    const item = catalog.get(instructionId);
    if (!item || item.kind !== "polyline") continue;
    const def = item.definition && typeof item.definition === "object" ? (item.definition as Record<string, unknown>) : {};
    const feature = String(def.feature ?? "");
    if (!(feature === "zhongshu.alive" || feature === "zhongshu.dead") || !effectiveVisible(feature)) continue;
    const isTop = instructionId.endsWith(":top");
    const isBottom = instructionId.endsWith(":bottom");
    const pointsRaw = def.points;
    if ((!isTop && !isBottom) || !Array.isArray(pointsRaw) || pointsRaw.length < 2) continue;
    const p0 = pointsRaw[0] as Record<string, unknown> | undefined;
    const p1 = pointsRaw[pointsRaw.length - 1] as Record<string, unknown> | undefined;
    const t0 = Number(p0?.time);
    const t1 = Number(p1?.time);
    const y0 = Number(p0?.value);
    if (!Number.isFinite(t0) || !Number.isFinite(t1) || !Number.isFinite(y0)) continue;
    const key = isTop ? instructionId.slice(0, -4) : instructionId.slice(0, -7);
    const seed = rectMap.get(key) ?? { feature };
    const edge = { startTime: Math.min(Math.floor(t0), Math.floor(t1)), endTime: Math.max(Math.floor(t0), Math.floor(t1)), value: y0 };
    if (isTop) seed.top = edge;
    if (isBottom) seed.bottom = edge;
    const entryDirection = Number(def.entryDirection);
    if (Number.isFinite(entryDirection) && entryDirection !== 0) seed.entryDirection = entryDirection > 0 ? 1 : -1;
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
    const top = Math.min(yTop, yBottom);
    const w = Math.max(0, Math.abs(x1 - x0));
    const h = Math.max(0, Math.abs(yBottom - yTop));
    if (w <= 0 || h <= 0) continue;
    const isAlive = seed.feature === "zhongshu.alive";
    const palette = zhongshuPalette(isAlive, (seed.entryDirection ?? (isAlive ? 1 : -1)) >= 0);
    ctx.save();
    ctx.beginPath();
    ctx.rect(left, top, w, h);
    ctx.fillStyle = palette.fill;
    ctx.fill();
    ctx.strokeStyle = palette.border;
    ctx.lineWidth = 1;
    ctx.setLineDash([]);
    ctx.stroke();
    ctx.restore();
  }
}

export function drawAnchorTopLayer(
  ctx: CanvasRenderingContext2D,
  chart: IChartApi,
  series: ISeriesApi<"Candlestick">,
  paths: OverlayPath[],
  highlightPoints: PenLinePoint[] | null,
  highlightDashed: boolean,
  effectiveVisible: (key: string) => boolean
) {
  if (!paths.length && !highlightPoints?.length) return;
  const clampTimeCoord = makeClampTimeCoord(chart);
  const drawPath = (points: PenLinePoint[], style: AnchorStyle) => {
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
    if (effectiveVisible(item.feature)) drawPath(item.points, resolveAnchorTopLayerStyle(item));
  }
  if (!effectiveVisible("anchor.current") || !highlightPoints || highlightPoints.length < 2) return;
  drawPath(highlightPoints, {
    color: "#f59e0b",
    lineWidth: highlightDashed ? 3 : 4,
    lineStyle: highlightDashed ? LineStyle.Dashed : LineStyle.Solid,
    haloWidth: highlightDashed ? 4 : 5
  });
}
