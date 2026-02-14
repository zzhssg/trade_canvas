import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import { useOverlayRenderCallbacks, usePenWorldCallbacks } from "./chartOverlayCallbacks";
import { useReplayFrameRequest, useReplayOverlayRuntime } from "./useReplayRuntimeCallbacks";
import type { Candle, GetFactorSlicesResponseV1, OverlayInstructionPatchItemV1 } from "./types";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";

type UseChartRuntimeCallbacksArgs = {
  seriesId: string;
  timeframe: string;
  replayEnabled: boolean;
  windowCandles: number;
  enablePenSegmentColor: boolean;
  enableAnchorTopLayer: boolean;
  segmentRenderLimit: number;
  chartRef: MutableRefObject<IChartApi | null>;
  markersApiRef: MutableRefObject<{ setMarkers: (markers: Array<SeriesMarker<Time>>) => void } | null>;
  candlesRef: MutableRefObject<Candle[]>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  overlayPolylineSeriesByIdRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorTopLayerPathsRef: MutableRefObject<OverlayCanvasPath[]>;
  pivotMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  anchorSwitchMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  setPivotCount: (value: number) => void;
  setAnchorSwitchCount: (value: number) => void;
  setAnchorTopLayerPathCount: (value: number) => void;
  setZhongshuCount: (value: number) => void;
  setAnchorCount: (value: number) => void;
  setOverlayPaintEpoch: Dispatch<SetStateAction<number>>;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  replayPenPreviewSeriesByFeatureRef: MutableRefObject<Record<ReplayPenPreviewFeature, ISeriesApi<"Line"> | null>>;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  factorPullInFlightRef: MutableRefObject<boolean>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  replayFrameLatestTimeRef: MutableRefObject<number | null>;
  replayFramePendingTimeRef: MutableRefObject<number | null>;
  replayFramePullInFlightRef: MutableRefObject<boolean>;
  effectiveVisible: (key: string) => boolean;
  setPenPointCount: (value: number) => void;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  setReplaySlices: (slices: GetFactorSlicesResponseV1) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  setReplayFrameLoading: (loading: boolean) => void;
  setReplayFrameError: (error: string | null) => void;
  setReplayFrame: Parameters<typeof useReplayFrameRequest>[0]["setReplayFrame"];
  setReplayCandle: (value: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
};

export function useChartRuntimeCallbacks(args: UseChartRuntimeCallbacksArgs) {
  const overlay = useOverlayRenderCallbacks({
    chartRef: args.chartRef,
    markersApiRef: args.markersApiRef,
    candlesRef: args.candlesRef,
    overlayActiveIdsRef: args.overlayActiveIdsRef,
    overlayCatalogRef: args.overlayCatalogRef,
    overlayCursorVersionRef: args.overlayCursorVersionRef,
    overlayPolylineSeriesByIdRef: args.overlayPolylineSeriesByIdRef,
    anchorTopLayerPathsRef: args.anchorTopLayerPathsRef,
    pivotMarkersRef: args.pivotMarkersRef,
    anchorSwitchMarkersRef: args.anchorSwitchMarkersRef,
    entryMarkersRef: args.entryMarkersRef,
    effectiveVisible: args.effectiveVisible,
    enableAnchorTopLayer: args.enableAnchorTopLayer,
    setPivotCount: args.setPivotCount,
    setAnchorSwitchCount: args.setAnchorSwitchCount,
    setAnchorTopLayerPathCount: args.setAnchorTopLayerPathCount,
    setZhongshuCount: args.setZhongshuCount,
    setAnchorCount: args.setAnchorCount,
    setOverlayPaintEpoch: args.setOverlayPaintEpoch,
    penPointsRef: args.penPointsRef
  });

  const penWorld = usePenWorldCallbacks({
    seriesId: args.seriesId,
    windowCandles: args.windowCandles,
    replayEnabled: args.replayEnabled,
    enablePenSegmentColor: args.enablePenSegmentColor,
    segmentRenderLimit: args.segmentRenderLimit,
    candlesRef: args.candlesRef,
    penSegmentsRef: args.penSegmentsRef,
    penPointsRef: args.penPointsRef,
    replayPenPreviewPointsRef: args.replayPenPreviewPointsRef,
    anchorPenPointsRef: args.anchorPenPointsRef,
    anchorPenIsDashedRef: args.anchorPenIsDashedRef,
    factorPullPendingTimeRef: args.factorPullPendingTimeRef,
    factorPullInFlightRef: args.factorPullInFlightRef,
    lastFactorAtTimeRef: args.lastFactorAtTimeRef,
    overlayCatalogRef: args.overlayCatalogRef,
    overlayActiveIdsRef: args.overlayActiveIdsRef,
    overlayCursorVersionRef: args.overlayCursorVersionRef,
    penSeriesRef: args.penSeriesRef,
    setAnchorHighlightEpoch: args.setAnchorHighlightEpoch,
    setReplaySlices: args.setReplaySlices,
    applyOverlayDelta: overlay.applyOverlayDelta,
    rebuildPivotMarkersFromOverlay: overlay.rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay: overlay.rebuildAnchorSwitchMarkersFromOverlay,
    syncMarkers: overlay.syncMarkers,
    rebuildPenPointsFromOverlay: overlay.rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay: overlay.rebuildOverlayPolylinesFromOverlay,
    setPenPointCount: args.setPenPointCount,
    effectiveVisible: args.effectiveVisible
  });

  const replayOverlay = useReplayOverlayRuntime({
    timeframe: args.timeframe,
    windowCandles: args.windowCandles,
    replayEnabled: args.replayEnabled,
    enablePenSegmentColor: args.enablePenSegmentColor,
    replayPatchRef: args.replayPatchRef,
    replayPatchAppliedIdxRef: args.replayPatchAppliedIdxRef,
    replayWindowIndexRef: args.replayWindowIndexRef,
    overlayCatalogRef: args.overlayCatalogRef,
    overlayActiveIdsRef: args.overlayActiveIdsRef,
    recomputeActiveIdsFromCatalog: overlay.recomputeActiveIdsFromCatalog,
    setReplayDrawInstructions: args.setReplayDrawInstructions,
    rebuildPivotMarkersFromOverlay: overlay.rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay: overlay.rebuildAnchorSwitchMarkersFromOverlay,
    rebuildPenPointsFromOverlay: overlay.rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay: overlay.rebuildOverlayPolylinesFromOverlay,
    syncMarkers: overlay.syncMarkers,
    effectiveVisible: args.effectiveVisible,
    penSeriesRef: args.penSeriesRef,
    penPointsRef: args.penPointsRef,
    penSegmentsRef: args.penSegmentsRef,
    setPenPointCount: args.setPenPointCount
  });

  const requestReplayFrameAtTime = useReplayFrameRequest({
    replayEnabled: args.replayEnabled,
    seriesId: args.seriesId,
    windowCandles: args.windowCandles,
    replayFrameLatestTimeRef: args.replayFrameLatestTimeRef,
    replayFramePendingTimeRef: args.replayFramePendingTimeRef,
    replayFramePullInFlightRef: args.replayFramePullInFlightRef,
    setReplayFrameLoading: args.setReplayFrameLoading,
    setReplayFrameError: args.setReplayFrameError,
    setReplayFrame: args.setReplayFrame,
    applyPenAndAnchorFromFactorSlices: penWorld.applyPenAndAnchorFromFactorSlices,
    setReplaySlices: args.setReplaySlices,
    setReplayCandle: args.setReplayCandle,
    setReplayDrawInstructions: args.setReplayDrawInstructions
  });

  return {
    ...overlay,
    ...penWorld,
    ...replayOverlay,
    requestReplayFrameAtTime
  };
}
