import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { MutableRefObject } from "react";

import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./barSpacing";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import type { Candle, OverlayInstructionPatchItemV1 } from "./types";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

export function applyChartLifecycleCreated(args: {
  chart: IChartApi;
  candleSeries: ISeriesApi<"Candlestick">;
  candlesRef: MutableRefObject<Candle[]>;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
}) {
  const existing = args.candlesRef.current;
  if (existing.length === 0) return;

  args.candleSeries.setData(existing);
  args.chart.timeScale().fitContent();
  const current = args.chart.timeScale().options().barSpacing;
  const next = clampBarSpacing(current, MAX_BAR_SPACING_ON_FIT_CONTENT);
  if (next !== current) args.chart.applyOptions({ timeScale: { barSpacing: next } });

  const last = existing[existing.length - 1]!;
  args.appliedRef.current = { len: existing.length, lastTime: last.time as number };
}

export function applyChartLifecycleCleanup(args: {
  chartRef: MutableRefObject<IChartApi | null>;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryMarkersRef: MutableRefObject<Array<{ time: unknown }>>;
  pivotMarkersRef: MutableRefObject<Array<{ time: unknown }>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  overlayPullInFlightRef: MutableRefObject<boolean>;
  factorPullInFlightRef: MutableRefObject<boolean>;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  entryEnabledRef: MutableRefObject<boolean>;
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  anchorTopLayerPathsRef: MutableRefObject<OverlayCanvasPath[]>;
}) {
  args.lineSeriesByKeyRef.current.clear();
  args.entryMarkersRef.current = [];
  args.pivotMarkersRef.current = [];
  args.overlayCatalogRef.current.clear();
  args.overlayActiveIdsRef.current.clear();
  args.overlayCursorVersionRef.current = 0;
  args.penPointsRef.current = [];
  args.penSeriesRef.current = null;
  args.anchorPenPointsRef.current = null;
  args.anchorPenIsDashedRef.current = false;
  args.anchorPenSeriesRef.current = null;

  for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
    const series = args.replayPenPreviewSeriesByFeatureRef.current[feature];
    if (series) args.chartRef.current?.removeSeries(series);
    args.replayPenPreviewSeriesByFeatureRef.current[feature] = null;
    args.replayPenPreviewPointsRef.current[feature] = [];
  }

  for (const series of args.penSegmentSeriesByKeyRef.current.values()) args.chartRef.current?.removeSeries(series);
  args.penSegmentSeriesByKeyRef.current.clear();
  args.penSegmentsRef.current = [];
  args.overlayPullInFlightRef.current = false;
  args.factorPullInFlightRef.current = false;
  args.factorPullPendingTimeRef.current = null;
  args.lastFactorAtTimeRef.current = null;
  args.entryEnabledRef.current = false;
  args.appliedRef.current = { len: 0, lastTime: null };
  args.anchorTopLayerPathsRef.current = [];
}
