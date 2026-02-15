import { LineStyle, type LineWidth, type SeriesMarker, type Time, type UTCTimestamp } from "lightweight-charts";

import type { Candle, OverlayInstructionPatchItemV1, OverlayLikeDeltaV1 } from "./types";

type OverlayDef = Record<string, unknown>;
type MarkerPosition = "aboveBar" | "belowBar";
type MarkerShape = "circle" | "square" | "arrowUp" | "arrowDown";

export type PenLinePoint = { time: UTCTimestamp; value: number };

export type OverlayPolylineStyle = {
  points: PenLinePoint[];
  color: string;
  lineWidth: LineWidth;
  lineStyle: LineStyle;
};

export type OverlayPath = {
  id: string;
  feature: string;
  points: PenLinePoint[];
  color: string;
  lineWidth: LineWidth;
  lineStyle: LineStyle;
};

export type OverlayMarkerBuildResult = {
  markers: Array<SeriesMarker<Time>>;
  pivotCount: number;
  anchorSwitchCount: number;
};

export function applyOverlayDeltaToCatalog(
  delta: OverlayLikeDeltaV1,
  overlayCatalog: Map<string, OverlayInstructionPatchItemV1>
): { activeIds: Set<string>; nextCursorVersion: number | null } {
  const patch = Array.isArray(delta.instruction_catalog_patch) ? delta.instruction_catalog_patch : [];
  for (const item of patch) {
    if (!item || typeof item !== "object") continue;
    if (typeof item.instruction_id !== "string" || !item.instruction_id) continue;
    overlayCatalog.set(item.instruction_id, item);
  }
  const nextCursorVersion =
    delta.next_cursor && typeof delta.next_cursor.version_id === "number" && Number.isFinite(delta.next_cursor.version_id)
      ? Math.max(0, Math.floor(delta.next_cursor.version_id))
      : null;
  return {
    activeIds: new Set(Array.isArray(delta.active_ids) ? delta.active_ids : []),
    nextCursorVersion
  };
}

export function resolveCandleTimeRange(candles: Candle[]): { minTime: number | null; maxTime: number | null } {
  if (candles.length === 0) return { minTime: null, maxTime: null };
  return {
    minTime: candles[0]!.time as number,
    maxTime: candles[candles.length - 1]!.time as number
  };
}

function normalizeMarkerPosition(value: unknown): MarkerPosition | null {
  if (value === "aboveBar" || value === "belowBar") return value;
  return null;
}

function normalizeMarkerShape(value: unknown): MarkerShape | null {
  if (value === "circle" || value === "square" || value === "arrowUp" || value === "arrowDown") return value;
  return null;
}

function toOverlayDef(value: unknown): OverlayDef {
  if (value && typeof value === "object") return value as OverlayDef;
  return {};
}

function isTimeInRange(time: number, minTime: number | null, maxTime: number | null): boolean {
  if (!Number.isFinite(time)) return false;
  if (minTime == null || maxTime == null) return false;
  return minTime <= time && time <= maxTime;
}

function extractPolylinePoints(params: {
  item: OverlayInstructionPatchItemV1;
  minTime: number | null;
  maxTime: number | null;
  allowOutOfRange: boolean;
}): PenLinePoint[] {
  const { item, minTime, maxTime, allowOutOfRange } = params;
  if (item.kind !== "polyline") return [];
  const def = toOverlayDef(item.definition);
  const pointsRaw = def["points"];
  if (!Array.isArray(pointsRaw) || pointsRaw.length === 0) return [];

  const allPoints: PenLinePoint[] = [];
  for (const point of pointsRaw) {
    if (!point || typeof point !== "object") continue;
    const rec = point as OverlayDef;
    const time = Number(rec["time"]);
    const value = Number(rec["value"]);
    if (!Number.isFinite(time) || !Number.isFinite(value)) continue;
    allPoints.push({ time: time as UTCTimestamp, value });
  }
  if (allPoints.length < 2) return [];
  if (allowOutOfRange || minTime == null || maxTime == null) return allPoints;

  const filtered = allPoints.filter((point) => {
    const time = Number(point.time);
    return Number.isFinite(time) && time >= minTime && time <= maxTime;
  });
  return filtered.length >= 2 ? filtered : [];
}

export function buildVisibleMarkersFromOverlay(params: {
  overlayActiveIds: Set<string>;
  overlayCatalog: Map<string, OverlayInstructionPatchItemV1>;
  minTime: number | null;
  maxTime: number | null;
  effectiveVisible: (feature: string) => boolean;
}): OverlayMarkerBuildResult {
  const { overlayActiveIds, overlayCatalog, minTime, maxTime, effectiveVisible } = params;
  if (minTime == null || maxTime == null) {
    return { markers: [], pivotCount: 0, anchorSwitchCount: 0 };
  }

  const markers: Array<SeriesMarker<Time>> = [];
  let pivotCount = 0;
  let anchorSwitchCount = 0;

  for (const id of overlayActiveIds) {
    const item = overlayCatalog.get(id);
    if (!item || item.kind !== "marker") continue;
    const def = toOverlayDef(item.definition);
    const feature = String(def["feature"] ?? "").trim();
    if (!feature || !effectiveVisible(feature)) continue;
    const time = Number(def["time"]);
    if (!isTimeInRange(time, minTime, maxTime)) continue;

    const position = normalizeMarkerPosition(def["position"]);
    const shape = normalizeMarkerShape(def["shape"]);
    const color = typeof def["color"] === "string" && def["color"] ? def["color"] : null;
    if (!position || !shape || !color) continue;

    const text = typeof def["text"] === "string" ? def["text"] : "";
    const sizeRaw = Number(def["size"]);
    const size = Number.isFinite(sizeRaw) && sizeRaw > 0 ? sizeRaw : 1.0;
    markers.push({ time: time as UTCTimestamp, position, color, shape, text, size });

    if (feature.startsWith("pivot.")) pivotCount += 1;
    if (feature === "anchor.switch") anchorSwitchCount += 1;
  }

  markers.sort((a, b) => Number(a.time) - Number(b.time));
  return { markers, pivotCount, anchorSwitchCount };
}

export function buildPenPointsFromOverlay(params: {
  overlayActiveIds: Set<string>;
  overlayCatalog: Map<string, OverlayInstructionPatchItemV1>;
  minTime: number | null;
  maxTime: number | null;
}): PenLinePoint[] {
  const { overlayActiveIds, overlayCatalog, minTime, maxTime } = params;
  const points: PenLinePoint[] = [];
  for (const id of overlayActiveIds) {
    const item = overlayCatalog.get(id);
    if (!item) continue;
    const def = toOverlayDef(item.definition);
    if (String(def["feature"] ?? "") !== "pen.confirmed") continue;
    const next = extractPolylinePoints({ item, minTime, maxTime, allowOutOfRange: false });
    if (next.length === 0) continue;
    if (points.length === 0) {
      points.push(...next);
      continue;
    }
    const lastTime = Number(points[points.length - 1]!.time);
    const firstTime = Number(next[0]!.time);
    if (lastTime === firstTime) {
      points.push(...next.slice(1));
    } else {
      points.push(...next);
    }
  }
  return points;
}

export function buildOverlayPolylinesFromOverlay(params: {
  overlayActiveIds: Set<string>;
  overlayCatalog: Map<string, OverlayInstructionPatchItemV1>;
  minTime: number | null;
  maxTime: number | null;
  effectiveVisible: (feature: string) => boolean;
  enableAnchorTopLayer: boolean;
}): {
  polylineById: Map<string, OverlayPolylineStyle>;
  anchorTopLayerPaths: OverlayPath[];
  zhongshuCount: number;
  anchorCount: number;
} {
  const { overlayActiveIds, overlayCatalog, minTime, maxTime, effectiveVisible, enableAnchorTopLayer } = params;
  const polylineById = new Map<string, OverlayPolylineStyle>();
  const anchorTopLayerPaths: OverlayPath[] = [];
  let zhongshuCount = 0;
  let anchorCount = 0;

  for (const id of overlayActiveIds) {
    const item = overlayCatalog.get(id);
    if (!item || item.kind !== "polyline") continue;

    const def = toOverlayDef(item.definition);
    const feature = String(def["feature"] ?? "").trim();
    if (!feature || feature === "pen.confirmed" || !effectiveVisible(feature)) continue;

    const isAnchorFeature = feature.startsWith("anchor.");
    const points = extractPolylinePoints({
      item,
      minTime,
      maxTime,
      allowOutOfRange: isAnchorFeature
    });
    if (points.length < 2) continue;

    const color = typeof def["color"] === "string" && def["color"] ? (def["color"] as string) : "#f59e0b";
    const lineWidthRaw = Number(def["lineWidth"]);
    const lineWidthBase = Number.isFinite(lineWidthRaw) && lineWidthRaw > 0 ? lineWidthRaw : 2;
    const lineWidth = Math.min(4, Math.max(1, Math.round(lineWidthBase))) as LineWidth;
    const lineStyleRaw = String(def["lineStyle"] ?? "");
    const lineStyle = lineStyleRaw === "dashed" ? LineStyle.Dashed : LineStyle.Solid;
    const style = { points, color, lineWidth, lineStyle };

    if (enableAnchorTopLayer && isAnchorFeature) {
      anchorTopLayerPaths.push({ id, feature, ...style });
    } else {
      polylineById.set(id, style);
    }

    if (feature.startsWith("zhongshu.")) zhongshuCount += 1;
    if (isAnchorFeature) anchorCount += 1;
  }

  return { polylineById, anchorTopLayerPaths, zhongshuCount, anchorCount };
}

export function recomputeActiveIdsFromCatalog(params: {
  overlayCatalog: Map<string, OverlayInstructionPatchItemV1>;
  cutoffTime: number;
  toTime: number;
}): string[] {
  const { overlayCatalog, cutoffTime, toTime } = params;
  const out: string[] = [];
  for (const [id, item] of overlayCatalog.entries()) {
    if (!item) continue;
    if (item.kind === "marker") {
      const def = toOverlayDef(item.definition);
      const time = Number(def["time"]);
      if (!Number.isFinite(time)) continue;
      if (time < cutoffTime || time > toTime) continue;
      out.push(id);
      continue;
    }
    if (item.kind === "polyline") {
      const def = toOverlayDef(item.definition);
      const points = def["points"];
      if (!Array.isArray(points) || points.length === 0) continue;
      let hit = false;
      for (const point of points) {
        if (!point || typeof point !== "object") continue;
        const time = Number((point as OverlayDef)["time"]);
        if (!Number.isFinite(time)) continue;
        if (cutoffTime <= time && time <= toTime) {
          hit = true;
          break;
        }
      }
      if (!hit) continue;
      out.push(id);
    }
  }
  out.sort();
  return out;
}
