import type { IChartApi, ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import { useOverlayRenderCallbacks, usePenWorldCallbacks } from "./chartOverlayCallbacks";
import { useReplayOverlayRuntime } from "./useReplayRuntimeCallbacks";
import type { Candle, GetFactorSlicesResponseV1, OverlayInstructionPatchItemV1 } from "./types";
import type { ReplayPenPreviewFeature } from "./liveSessionRuntimeTypes";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

type UseChartRuntimeCallbacksArgs = {
  seriesId: string;
  windowCandles: number;
  replayEnabled: boolean;
  enablePenSegmentColor: boolean;
  enableAnchorTopLayer: boolean;
  segmentRenderLimit: number;
  chartRef: MutableRefObject<IChartApi | null>;
  markersApiRef: MutableRefObject<{ setMarkers: (markers: Array<SeriesMarker<Time>>) => void } | null>;
  activeSeriesIdRef: MutableRefObject<string>;
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
  replayWindowIndexRef: MutableRefObject<number | null>;
  effectiveVisible: (key: string) => boolean;
  setPenPointCount: (value: number) => void;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  setReplaySlices: (slices: GetFactorSlicesResponseV1) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  setReplayCandle: (value: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
};

export function useChartRuntimeCallbacks(args: UseChartRuntimeCallbacksArgs) {
  const overlay = useOverlayRenderCallbacks(args);
  const overlayCallbacks = {
    applyOverlayDelta: overlay.applyOverlayDelta,
    rebuildPivotMarkersFromOverlay: overlay.rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay: overlay.rebuildAnchorSwitchMarkersFromOverlay,
    syncMarkers: overlay.syncMarkers,
    rebuildPenPointsFromOverlay: overlay.rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay: overlay.rebuildOverlayPolylinesFromOverlay
  };

  const penWorld = usePenWorldCallbacks({
    ...args,
    ...overlayCallbacks
  });

  const replayOverlay = useReplayOverlayRuntime({
    ...args,
    ...overlayCallbacks
  });

  return {
    ...overlay,
    ...penWorld,
    ...replayOverlay
  };
}
