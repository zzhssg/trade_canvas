import type { ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useRef, useState } from "react";

import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";
import type { Candle, OverlayInstructionPatchItemV1 } from "./types";
import type { ReplayPenPreviewFeature } from "./liveSessionRuntimeTypes";
import type { OverlayCanvasPath } from "./useOverlayCanvas";

export function useChartRuntimeRefs(enableWorldFrame: boolean) {
  const activeSeriesIdRef = useRef("");
  const candlesRef = useRef<Candle[]>([]);
  const candleTimesSecRef = useRef<number[]>([]);
  const appliedRef = useRef<{ len: number; lastTime: number | null }>({ len: 0, lastTime: null });

  const lineSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const entryEnabledRef = useRef<boolean>(false);
  const entryMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const pivotMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const anchorSwitchMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);

  const overlayCatalogRef = useRef<Map<string, OverlayInstructionPatchItemV1>>(new Map());
  const overlayActiveIdsRef = useRef<Set<string>>(new Set());
  const overlayCursorVersionRef = useRef<number>(0);
  const overlayPullInFlightRef = useRef(false);
  const overlayPolylineSeriesByIdRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

  const [pivotCount, setPivotCount] = useState(0);
  const [zhongshuCount, setZhongshuCount] = useState(0);
  const [anchorCount, setAnchorCount] = useState(0);
  const [anchorSwitchCount, setAnchorSwitchCount] = useState(0);

  const replayAllCandlesRef = useRef<Array<Candle | null>>([]);
  const replayWindowIndexRef = useRef<number | null>(null);
  const replayPatchRef = useRef<OverlayInstructionPatchItemV1[]>([]);
  const replayPatchAppliedIdxRef = useRef<number>(0);
  const replayFramePullInFlightRef = useRef(false);
  const replayFramePendingTimeRef = useRef<number | null>(null);
  const replayFrameLatestTimeRef = useRef<number | null>(null);
  const followPendingTimeRef = useRef<number | null>(null);
  const followTimerIdRef = useRef<number | null>(null);

  const penSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const penPointsRef = useRef<PenLinePoint[]>([]);
  const [penPointCount, setPenPointCount] = useState(0);
  const [anchorHighlightEpoch, setAnchorHighlightEpoch] = useState(0);

  const penSegmentSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const penSegmentsRef = useRef<PenSegment[]>([]);
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
  const worldFrameHealthyRef = useRef<boolean>(enableWorldFrame);

  const anchorTopLayerPathsRef = useRef<OverlayCanvasPath[]>([]);
  const [overlayPaintEpoch, setOverlayPaintEpoch] = useState(0);
  const [anchorTopLayerPathCount, setAnchorTopLayerPathCount] = useState(0);

  return {
    activeSeriesIdRef,
    candlesRef,
    candleTimesSecRef,
    appliedRef,
    lineSeriesByKeyRef,
    entryEnabledRef,
    entryMarkersRef,
    pivotMarkersRef,
    anchorSwitchMarkersRef,
    overlayCatalogRef,
    overlayActiveIdsRef,
    overlayCursorVersionRef,
    overlayPullInFlightRef,
    overlayPolylineSeriesByIdRef,
    pivotCount,
    setPivotCount,
    zhongshuCount,
    setZhongshuCount,
    anchorCount,
    setAnchorCount,
    anchorSwitchCount,
    setAnchorSwitchCount,
    replayAllCandlesRef,
    replayWindowIndexRef,
    replayPatchRef,
    replayPatchAppliedIdxRef,
    replayFramePullInFlightRef,
    replayFramePendingTimeRef,
    replayFrameLatestTimeRef,
    followPendingTimeRef,
    followTimerIdRef,
    penSeriesRef,
    penPointsRef,
    penPointCount,
    setPenPointCount,
    anchorHighlightEpoch,
    setAnchorHighlightEpoch,
    penSegmentSeriesByKeyRef,
    penSegmentsRef,
    anchorPenSeriesRef,
    anchorPenPointsRef,
    anchorPenIsDashedRef,
    replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef,
    factorPullInFlightRef,
    factorPullPendingTimeRef,
    lastFactorAtTimeRef,
    worldFrameHealthyRef,
    anchorTopLayerPathsRef,
    overlayPaintEpoch,
    setOverlayPaintEpoch,
    anchorTopLayerPathCount,
    setAnchorTopLayerPathCount
  };
}
