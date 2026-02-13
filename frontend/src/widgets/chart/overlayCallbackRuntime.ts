import { LineSeries, type IChartApi, type ISeriesApi, type SeriesMarker, type Time } from "lightweight-charts";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import { fetchFactorSlices } from "./api";
import {
  buildAnchorSwitchMarkersFromOverlay,
  buildOverlayPolylinesFromOverlay,
  buildPenPointsFromOverlay,
  buildPivotMarkersFromOverlay,
  resolveCandleTimeRange
} from "./overlayRuntimeCore";
import { derivePenAnchorStateFromSlices, type PenLinePoint, type PenSegment } from "./penAnchorRuntime";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  WorldStateV1
} from "./types";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

type OverlayRuntimeBaseArgs = {
  candlesRef: MutableRefObject<Candle[]>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  effectiveVisible: (key: string) => boolean;
};

export function rebuildPivotMarkersFromOverlayRuntime(args: OverlayRuntimeBaseArgs): Array<SeriesMarker<Time>> {
  const { minTime, maxTime } = resolveCandleTimeRange(args.candlesRef.current);
  return buildPivotMarkersFromOverlay({
    overlayActiveIds: args.overlayActiveIdsRef.current,
    overlayCatalog: args.overlayCatalogRef.current,
    minTime,
    maxTime,
    showPivotMajor: args.effectiveVisible("pivot.major"),
    showPivotMinor: args.effectiveVisible("pivot.minor")
  });
}

export function rebuildAnchorSwitchMarkersFromOverlayRuntime(args: OverlayRuntimeBaseArgs): Array<SeriesMarker<Time>> {
  const { minTime, maxTime } = resolveCandleTimeRange(args.candlesRef.current);
  return buildAnchorSwitchMarkersFromOverlay({
    overlayActiveIds: args.overlayActiveIdsRef.current,
    overlayCatalog: args.overlayCatalogRef.current,
    minTime,
    maxTime,
    showAnchorSwitch: args.effectiveVisible("anchor.switch")
  });
}

export function rebuildPenPointsFromOverlayRuntime(args: {
  candlesRef: MutableRefObject<Candle[]>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
}): PenLinePoint[] {
  const { minTime, maxTime } = resolveCandleTimeRange(args.candlesRef.current);
  return buildPenPointsFromOverlay({
    overlayActiveIds: args.overlayActiveIdsRef.current,
    overlayCatalog: args.overlayCatalogRef.current,
    minTime,
    maxTime
  });
}

export function rebuildOverlayPolylinesFromOverlayRuntime(args: {
  chart: IChartApi | null;
  candlesRef: MutableRefObject<Candle[]>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  effectiveVisible: (key: string) => boolean;
  enableAnchorTopLayer: boolean;
  overlayPolylineSeriesByIdRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorTopLayerPathsRef: MutableRefObject<OverlayCanvasPath[]>;
  setAnchorTopLayerPathCount: (value: number) => void;
  setZhongshuCount: (value: number) => void;
  setAnchorCount: (value: number) => void;
  setOverlayPaintEpoch: Dispatch<SetStateAction<number>>;
}) {
  const chart = args.chart;
  if (!chart) return;

  const { minTime, maxTime } = resolveCandleTimeRange(args.candlesRef.current);
  const { polylineById, anchorTopLayerPaths, zhongshuCount, anchorCount } = buildOverlayPolylinesFromOverlay({
    overlayActiveIds: args.overlayActiveIdsRef.current,
    overlayCatalog: args.overlayCatalogRef.current,
    minTime,
    maxTime,
    effectiveVisible: args.effectiveVisible,
    enableAnchorTopLayer: args.enableAnchorTopLayer
  });

  for (const [id, series] of args.overlayPolylineSeriesByIdRef.current.entries()) {
    if (polylineById.has(id)) continue;
    chart.removeSeries(series);
    args.overlayPolylineSeriesByIdRef.current.delete(id);
  }

  for (const [id, item] of polylineById.entries()) {
    let series = args.overlayPolylineSeriesByIdRef.current.get(id);
    if (!series) {
      series = chart.addSeries(LineSeries, {
        color: item.color,
        lineWidth: item.lineWidth,
        lineStyle: item.lineStyle,
        priceLineVisible: false,
        lastValueVisible: false
      });
      args.overlayPolylineSeriesByIdRef.current.set(id, series);
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

  args.anchorTopLayerPathsRef.current = anchorTopLayerPaths;
  args.setAnchorTopLayerPathCount(anchorTopLayerPaths.length);
  args.setZhongshuCount(zhongshuCount);
  args.setAnchorCount(anchorCount);
  args.setOverlayPaintEpoch((value) => value + 1);
}

export function applyPenAndAnchorFromFactorSlicesRuntime(args: {
  slices: GetFactorSlicesResponseV1;
  candlesRef: MutableRefObject<Candle[]>;
  replayEnabled: boolean;
  enablePenSegmentColor: boolean;
  segmentRenderLimit: number;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
}) {
  const { minTime, maxTime } = resolveCandleTimeRange(args.candlesRef.current);
  const next = derivePenAnchorStateFromSlices({
    slices: args.slices,
    minTime,
    maxTime,
    replayEnabled: args.replayEnabled,
    enablePenSegmentColor: args.enablePenSegmentColor,
    segmentRenderLimit: args.segmentRenderLimit
  });

  args.penSegmentsRef.current = next.penSegments;
  if (args.replayEnabled) args.penPointsRef.current = next.replayPenPoints;
  args.replayPenPreviewPointsRef.current["pen.extending"] = next.replayPenPreviewPoints["pen.extending"];
  args.replayPenPreviewPointsRef.current["pen.candidate"] = next.replayPenPreviewPoints["pen.candidate"];
  args.anchorPenPointsRef.current = next.anchorHighlightPoints;
  args.anchorPenIsDashedRef.current = next.anchorHighlightDashed;
  args.setAnchorHighlightEpoch((value) => value + 1);
}

export async function fetchAndApplyAnchorHighlightAtTimeRuntime(args: {
  time: number;
  seriesId: string;
  windowCandles: number;
  replayEnabled: boolean;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  factorPullInFlightRef: MutableRefObject<boolean>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  applyPenAndAnchorFromFactorSlices: (slices: GetFactorSlicesResponseV1) => void;
  setReplaySlices: (slices: GetFactorSlicesResponseV1) => void;
}) {
  const at = Math.max(0, Math.floor(args.time));
  if (at <= 0) return;

  args.factorPullPendingTimeRef.current = at;
  if (args.factorPullInFlightRef.current) return;
  args.factorPullInFlightRef.current = true;

  try {
    while (args.factorPullPendingTimeRef.current != null) {
      const next = args.factorPullPendingTimeRef.current;
      args.factorPullPendingTimeRef.current = null;
      if (args.lastFactorAtTimeRef.current === next) continue;
      const slices = await fetchFactorSlices({ seriesId: args.seriesId, atTime: next, windowCandles: args.windowCandles });
      args.lastFactorAtTimeRef.current = next;
      args.applyPenAndAnchorFromFactorSlices(slices);
      if (args.replayEnabled) args.setReplaySlices(slices);
    }
  } catch {
    // ignore (best-effort)
  } finally {
    args.factorPullInFlightRef.current = false;
  }
}

export function applyWorldFrameRuntime(args: {
  frame: WorldStateV1;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  applyOverlayDelta: (delta: OverlayLikeDeltaV1) => void;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  syncMarkers: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  enablePenSegmentColor: boolean;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  setPenPointCount: (value: number) => void;
  effectiveVisible: (key: string) => boolean;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  applyPenAndAnchorFromFactorSlices: (slices: GetFactorSlicesResponseV1) => void;
}) {
  args.overlayCatalogRef.current.clear();
  args.overlayActiveIdsRef.current.clear();
  args.overlayCursorVersionRef.current = 0;

  const draw = args.frame.draw_state;
  args.applyOverlayDelta({
    active_ids: draw.active_ids ?? [],
    instruction_catalog_patch: draw.instruction_catalog_patch ?? [],
    next_cursor: { version_id: draw.next_cursor?.version_id ?? 0 }
  });

  args.rebuildPivotMarkersFromOverlay();
  args.rebuildAnchorSwitchMarkersFromOverlay();
  args.syncMarkers();
  args.rebuildPenPointsFromOverlay();
  args.rebuildOverlayPolylinesFromOverlay();
  args.setPenPointCount(args.enablePenSegmentColor ? args.penSegmentsRef.current.length * 2 : args.penPointsRef.current.length);
  if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
    args.penSeriesRef.current.setData(args.penPointsRef.current);
  }

  args.applyPenAndAnchorFromFactorSlices(args.frame.factor_slices);
}
