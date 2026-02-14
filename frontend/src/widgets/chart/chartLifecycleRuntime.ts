import type { IChartApi, ISeriesApi } from "lightweight-charts";
import type { MutableRefObject } from "react";

import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./barSpacing";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import type { Candle, OverlayInstructionPatchItemV1 } from "./types";
import type { ReplayPenPreviewFeature } from "./liveSessionRuntimeTypes";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

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
  appliedRef: MutableRefObject<{ len: number; lastTime: number | null }>;
  runtimeRefs: {
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
    anchorTopLayerPathsRef: MutableRefObject<OverlayCanvasPath[]>;
  };
}) {
  const refs = args.runtimeRefs;
  refs.lineSeriesByKeyRef.current.clear();
  refs.entryMarkersRef.current = [];
  refs.pivotMarkersRef.current = [];
  refs.overlayCatalogRef.current.clear();
  refs.overlayActiveIdsRef.current.clear();
  refs.overlayCursorVersionRef.current = 0;
  refs.penPointsRef.current = [];
  refs.penSeriesRef.current = null;
  refs.anchorPenPointsRef.current = null;
  refs.anchorPenIsDashedRef.current = false;
  refs.anchorPenSeriesRef.current = null;

  for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
    const series = refs.replayPenPreviewSeriesByFeatureRef.current[feature];
    if (series) args.chartRef.current?.removeSeries(series);
    refs.replayPenPreviewSeriesByFeatureRef.current[feature] = null;
    refs.replayPenPreviewPointsRef.current[feature] = [];
  }

  for (const series of refs.penSegmentSeriesByKeyRef.current.values()) args.chartRef.current?.removeSeries(series);
  refs.penSegmentSeriesByKeyRef.current.clear();
  refs.penSegmentsRef.current = [];
  refs.overlayPullInFlightRef.current = false;
  refs.factorPullInFlightRef.current = false;
  refs.factorPullPendingTimeRef.current = null;
  refs.lastFactorAtTimeRef.current = null;
  refs.entryEnabledRef.current = false;
  args.appliedRef.current = { len: 0, lastTime: null };
  refs.anchorTopLayerPathsRef.current = [];
}
