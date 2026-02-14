import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useCallback, type Dispatch, type MutableRefObject, type SetStateAction } from "react";

import { fetchDrawDelta } from "./api";
import {
  applyPenAndAnchorFromFactorSlicesRuntime,
  applyWorldFrameRuntime,
  fetchAndApplyAnchorHighlightAtTimeRuntime,
  rebuildAnchorSwitchMarkersFromOverlayRuntime,
  rebuildOverlayPolylinesFromOverlayRuntime,
  rebuildPenPointsFromOverlayRuntime,
  rebuildPivotMarkersFromOverlayRuntime
} from "./overlayCallbackRuntime";
import { applyOverlayDeltaToCatalog, recomputeActiveIdsFromCatalog } from "./overlayRuntimeCore";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  WorldStateV1
} from "./types";
import type { ReplayPenPreviewFeature } from "./liveSessionRuntimeTypes";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

type UseOverlayRenderCallbacksArgs = {
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
  effectiveVisible: (key: string) => boolean;
  enableAnchorTopLayer: boolean;
  setPivotCount: (value: number) => void;
  setAnchorSwitchCount: (value: number) => void;
  setAnchorTopLayerPathCount: (value: number) => void;
  setZhongshuCount: (value: number) => void;
  setAnchorCount: (value: number) => void;
  setOverlayPaintEpoch: Dispatch<SetStateAction<number>>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
};

export function useOverlayRenderCallbacks(args: UseOverlayRenderCallbacksArgs) {
  const syncMarkers = useCallback(() => {
    const markers = [...args.pivotMarkersRef.current, ...args.anchorSwitchMarkersRef.current, ...args.entryMarkersRef.current];
    args.markersApiRef.current?.setMarkers(markers);
    args.setPivotCount(args.pivotMarkersRef.current.length);
  }, []);

  const applyOverlayDelta = useCallback((delta: OverlayLikeDeltaV1) => {
    const { activeIds, nextCursorVersion } = applyOverlayDeltaToCatalog(delta, args.overlayCatalogRef.current);
    args.overlayActiveIdsRef.current = activeIds;
    if (nextCursorVersion != null) args.overlayCursorVersionRef.current = nextCursorVersion;
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
    args.pivotMarkersRef.current = rebuildPivotMarkersFromOverlayRuntime(args);
  }, [args.effectiveVisible]);

  const rebuildAnchorSwitchMarkersFromOverlay = useCallback(() => {
    const markers = rebuildAnchorSwitchMarkersFromOverlayRuntime(args);
    args.anchorSwitchMarkersRef.current = markers;
    args.setAnchorSwitchCount(markers.length);
  }, [args.effectiveVisible]);

  const rebuildPenPointsFromOverlay = useCallback(() => {
    args.penPointsRef.current = rebuildPenPointsFromOverlayRuntime(args);
  }, []);

  const rebuildOverlayPolylinesFromOverlay = useCallback(() => {
    rebuildOverlayPolylinesFromOverlayRuntime({
      ...args,
      chart: args.chartRef.current
    });
  }, [args.effectiveVisible]);

  const recomputeActiveIds = useCallback((params: { cutoffTime: number; toTime: number }): string[] => {
    return recomputeActiveIdsFromCatalog({
      overlayCatalog: args.overlayCatalogRef.current,
      cutoffTime: params.cutoffTime,
      toTime: params.toTime
    });
  }, []);

  return {
    syncMarkers,
    applyOverlayDelta,
    fetchOverlayLikeDelta,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay,
    recomputeActiveIdsFromCatalog: recomputeActiveIds
  };
}

type UsePenWorldCallbacksArgs = {
  seriesId: string;
  windowCandles: number;
  replayEnabled: boolean;
  enablePenSegmentColor: boolean;
  segmentRenderLimit: number;
  activeSeriesIdRef: MutableRefObject<string>;
  candlesRef: MutableRefObject<Candle[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  replayPenPreviewPointsRef: MutableRefObject<Record<ReplayPenPreviewFeature, PenLinePoint[]>>;
  anchorPenPointsRef: MutableRefObject<PenLinePoint[] | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  factorPullInFlightRef: MutableRefObject<boolean>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  setReplaySlices: (slices: GetFactorSlicesResponseV1) => void;
  applyOverlayDelta: (delta: OverlayLikeDeltaV1) => void;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  syncMarkers: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  setPenPointCount: (value: number) => void;
  effectiveVisible: (key: string) => boolean;
};

export function usePenWorldCallbacks(args: UsePenWorldCallbacksArgs) {
  const applyPenAndAnchorFromFactorSlices = useCallback(
    (slices: GetFactorSlicesResponseV1) => {
      applyPenAndAnchorFromFactorSlicesRuntime({
        ...args,
        slices
      });
    },
    [args.replayEnabled, args.setAnchorHighlightEpoch]
  );

  const fetchAndApplyAnchorHighlightAtTime = useCallback(
    async (time: number) => {
      await fetchAndApplyAnchorHighlightAtTimeRuntime({
        ...args,
        time,
        applyPenAndAnchorFromFactorSlices,
      });
    },
    [applyPenAndAnchorFromFactorSlices, args.replayEnabled, args.seriesId, args.setReplaySlices, args.windowCandles]
  );

  const applyWorldFrame = useCallback(
    (frame: WorldStateV1) => {
      applyWorldFrameRuntime({
        ...args,
        frame,
        applyPenAndAnchorFromFactorSlices
      });
    },
    [
      args.applyOverlayDelta,
      applyPenAndAnchorFromFactorSlices,
      args.effectiveVisible,
      args.rebuildOverlayPolylinesFromOverlay,
      args.rebuildPenPointsFromOverlay,
      args.rebuildPivotMarkersFromOverlay,
      args.rebuildAnchorSwitchMarkersFromOverlay,
      args.syncMarkers
    ]
  );

  return {
    applyPenAndAnchorFromFactorSlices,
    fetchAndApplyAnchorHighlightAtTime,
    applyWorldFrame
  };
}
