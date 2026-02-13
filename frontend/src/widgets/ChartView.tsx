import {
  type IChartApi,
  type ISeriesApi,
  type SeriesMarker,
  type Time
} from "lightweight-charts";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import useResizeObserver from "use-resize-observer";

import { getFactorParentsBySubKey, useFactorCatalog } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";
import { useUiStore } from "../state/uiStore";

import { ChartViewOverlayLayer } from "./chart/ChartViewOverlayLayer";
import { useFibPreview } from "./chart/draw_tools/useFibPreview";
import { useDrawToolState } from "./chart/draw_tools/useDrawToolState";

import { fetchDrawDelta } from "./chart/api";
import { MAX_BAR_SPACING_ON_FIT_CONTENT, clampBarSpacing } from "./chart/barSpacing";
import {
  applyOverlayDeltaToCatalog,
  recomputeActiveIdsFromCatalog as recomputeActiveIdsFromCatalogCore
} from "./chart/overlayRuntimeCore";
import { type PenLinePoint, type PenSegment } from "./chart/penAnchorRuntime";
import {
  applyPenAndAnchorFromFactorSlicesRuntime,
  applyWorldFrameRuntime,
  fetchAndApplyAnchorHighlightAtTimeRuntime,
  rebuildAnchorSwitchMarkersFromOverlayRuntime,
  rebuildOverlayPolylinesFromOverlayRuntime,
  rebuildPenPointsFromOverlayRuntime,
  rebuildPivotMarkersFromOverlayRuntime
} from "./chart/overlayCallbackRuntime";
import {
  toReplayCandle,
  useReplayFrameRequest,
  useReplayOverlayRuntime
} from "./chart/useReplayRuntimeCallbacks";
import { buildSmaLineData, computeSmaAtIndex, isSmaKey } from "./chart/sma";
import {
  useChartLiveSessionEffect,
  useChartSeriesSyncEffects,
  useReplayFocusSyncEffect,
  useReplayPackageResetEffect
} from "./chart/useChartSessionEffects";
import { useChartRuntimeEffects } from "./chart/chartRuntimeEffects";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  OverlayLikeDeltaV1,
  WorldStateV1
} from "./chart/types";
import { useLightweightChart } from "./chart/useLightweightChart";
import { useOverlayCanvas, type OverlayCanvasPath } from "./chart/useOverlayCanvas";
import { useReplayBindings } from "./chart/useReplayBindings";
import { useReplayController } from "./chart/useReplayController";
import { useReplayPackage } from "./chart/useReplayPackage";
import { useReplayPackageWindowSync } from "./chart/useReplayPackageWindowSync";
import { useChartDrawToolEffects } from "./chart/useChartDrawToolEffects";
import { useWsSync } from "./chart/useWsSync";
import { useChartWheelZoomGuard, useReplayViewportEffects } from "./chart/useChartViewportEffects";

const INITIAL_TAIL_LIMIT = 2000;
const ENABLE_REPLAY_V1 = String(import.meta.env.VITE_ENABLE_REPLAY_V1 ?? "1") === "1";
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
const ENABLE_ANCHOR_TOP_LAYER = String(import.meta.env.VITE_ENABLE_ANCHOR_TOP_LAYER ?? "1") === "1";
// Default to enabled (unless explicitly disabled) to avoid "delta + slices" double-fetch loops in live mode.
const ENABLE_WORLD_FRAME = String(import.meta.env.VITE_ENABLE_WORLD_FRAME ?? "1") === "1";
const PEN_SEGMENT_RENDER_LIMIT = 200;
const ENABLE_DRAW_TOOLS = String(import.meta.env.VITE_ENABLE_DRAW_TOOLS ?? "1") === "1";
const REPLAY_WINDOW_CANDLES = 2000;
const REPLAY_WINDOW_SIZE = 500;
const REPLAY_SNAPSHOT_INTERVAL = 25;
type ReplayPenPreviewFeature = "pen.extending" | "pen.candidate";
type OverlayPath = OverlayCanvasPath;

export function ChartView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();
  const wheelGuardRef = useRef<HTMLDivElement | null>(null);

  const [candles, setCandles] = useState<Candle[]>([]);
  const [barSpacing, setBarSpacing] = useState<number | null>(null);
  const candlesRef = useRef<Candle[]>([]);
  const candleTimesSecRef = useRef<number[]>([]);
  const lastWsCandleTimeRef = useRef<number | null>(null);
  const [lastWsCandleTime, setLastWsCandleTime] = useState<number | null>(null);
  const appliedRef = useRef<{ len: number; lastTime: number | null }>({ len: 0, lastTime: null });
  const [error, setError] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimerRef = useRef<number | null>(null);
  const { exchange, market, symbol, timeframe, activeChartTool, setActiveChartTool } = useUiStore();
  const {
    replayMode,
    replayPlaying,
    replaySpeedMs,
    replayIndex,
    replayTotal,
    replayFocusTime,
    replayPrepareStatus,
    replayPreparedAlignedTime,
    setReplayPlaying,
    setReplayIndex,
    setReplayTotal,
    setReplayFocusTime,
    setReplayFrame,
    setReplayFrameLoading,
    setReplayFrameError,
    setReplayPrepareStatus,
    setReplayPrepareError,
    setReplayPreparedAlignedTime,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions,
    resetReplayData
  } = useReplayBindings();
  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);

  const { visibleFeatures } = useFactorStore();
  const factorCatalog = useFactorCatalog();
  const visibleFeaturesRef = useRef(visibleFeatures);
  const parentBySubKey = useMemo(() => getFactorParentsBySubKey(factorCatalog), [factorCatalog]);
  const lineSeriesByKeyRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const showToast = useCallback((message: string) => {
    setToastMessage(message);
    if (toastTimerRef.current != null) window.clearTimeout(toastTimerRef.current);
    toastTimerRef.current = window.setTimeout(() => {
      setToastMessage(null);
      toastTimerRef.current = null;
    }, 3200);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current != null) {
        window.clearTimeout(toastTimerRef.current);
        toastTimerRef.current = null;
      }
    };
  }, []);
  const entryMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const pivotMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const anchorSwitchMarkersRef = useRef<Array<SeriesMarker<Time>>>([]);
  const overlayCatalogRef = useRef<Map<string, OverlayInstructionPatchItemV1>>(new Map());
  const overlayActiveIdsRef = useRef<Set<string>>(new Set());
  const overlayCursorVersionRef = useRef<number>(0);
  const overlayPullInFlightRef = useRef(false);
  const overlayPolylineSeriesByIdRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());
  const entryEnabledRef = useRef<boolean>(false);
  const worldFrameHealthyRef = useRef<boolean>(ENABLE_WORLD_FRAME);
  const [pivotCount, setPivotCount] = useState(0);
  const [zhongshuCount, setZhongshuCount] = useState(0);
  const [anchorCount, setAnchorCount] = useState(0);
  const [anchorSwitchCount, setAnchorSwitchCount] = useState(0);
  const replayEnabled = ENABLE_REPLAY_V1 && replayMode === "replay";
  const [replayMaskX, setReplayMaskX] = useState<number | null>(null);
  const replayAllCandlesRef = useRef<Array<Candle | null>>([]);
  const replayWindowIndexRef = useRef<number | null>(null);
  const replayPatchRef = useRef<OverlayInstructionPatchItemV1[]>([]);
  const replayPatchAppliedIdxRef = useRef<number>(0);
  const replayFramePullInFlightRef = useRef(false);
  const replayFramePendingTimeRef = useRef<number | null>(null);
  const replayFrameLatestTimeRef = useRef<number | null>(null);
  const followPendingTimeRef = useRef<number | null>(null);
  const followTimerIdRef = useRef<number | null>(null);

  const replayPackage = useReplayPackage({
    seriesId,
    enabled: replayEnabled && replayPrepareStatus === "ready",
    windowCandles: REPLAY_WINDOW_CANDLES,
    windowSize: REPLAY_WINDOW_SIZE,
    snapshotInterval: REPLAY_SNAPSHOT_INTERVAL
  });
  const replayPackageEnabled = replayEnabled && replayPrepareStatus === "ready" && replayPackage.enabled;
  const replayPackageStatus = replayPackage.status;
  const replayPackageMeta = replayPackage.metadata;
  const replayPackageHistory = replayPackage.historyEvents;
  const replayPackageWindows = replayPackage.windows;
  const replayEnsureWindowRange = replayPackage.ensureWindowRange;
  const { setReplayIndexAndFocus } = useReplayController({
    seriesId,
    replayEnabled,
    replayPlaying,
    replaySpeedMs,
    replayIndex,
    replayTotal,
    windowCandles: INITIAL_TAIL_LIMIT,
    resetReplayData,
    setReplayPlaying,
    setReplayIndex,
    setReplayPrepareStatus,
    setReplayPrepareError,
    setReplayPreparedAlignedTime
  });
  const { openMarketWs } = useWsSync({ seriesId });

  const {
    positionTools,
    setPositionTools,
    fibTools,
    setFibTools,
    activeToolId,
    setActiveToolId,
    fibAnchorA,
    setFibAnchorA,
    measureState,
    setMeasureState,
    activeChartToolRef,
    fibAnchorARef,
    measureStateRef,
    activeToolIdRef,
    interactionLockRef,
    suppressDeselectUntilRef,
    genId,
    updatePositionTool,
    removePositionTool,
    updateFibTool,
    removeFibTool,
    selectTool
  } = useDrawToolState({
    enableDrawTools: ENABLE_DRAW_TOOLS,
    activeChartTool,
    setActiveChartTool,
    seriesId
  });

  const findReplayIndexByTime = useCallback((timeSec: number) => {
    const all = candlesRef.current;
    if (all.length === 0) return null;
    let lo = 0;
    let hi = all.length - 1;
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      const t = Number(all[mid]!.time);
      if (t === timeSec) return mid;
      if (t < timeSec) lo = mid + 1;
      else hi = mid - 1;
    }
    const idx = Math.max(0, Math.min(all.length - 1, hi));
    return idx;
  }, []);

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
  const anchorTopLayerPathsRef = useRef<OverlayPath[]>([]);
  const [overlayPaintEpoch, setOverlayPaintEpoch] = useState(0);
  const [anchorTopLayerPathCount, setAnchorTopLayerPathCount] = useState(0);

  const { chartRef, candleSeriesRef: seriesRef, markersApiRef, chartEpoch } = useLightweightChart({
    containerRef,
    width,
    height,
    onCreated: ({ chart, candleSeries }) => {
      const existing = candlesRef.current;
      if (existing.length > 0) {
        candleSeries.setData(existing);
        chart.timeScale().fitContent();
        const cur = chart.timeScale().options().barSpacing;
        const next = clampBarSpacing(cur, MAX_BAR_SPACING_ON_FIT_CONTENT);
        if (next !== cur) chart.applyOptions({ timeScale: { barSpacing: next } });
        const last = existing[existing.length - 1]!;
        appliedRef.current = { len: existing.length, lastTime: last.time as number };
      }
    },
    onCleanup: () => {
      lineSeriesByKeyRef.current.clear();
      entryMarkersRef.current = [];
      pivotMarkersRef.current = [];
      overlayCatalogRef.current.clear();
      overlayActiveIdsRef.current.clear();
      overlayCursorVersionRef.current = 0;
      penPointsRef.current = [];
      penSeriesRef.current = null;
      anchorPenPointsRef.current = null;
      anchorPenIsDashedRef.current = false;
      anchorPenSeriesRef.current = null;
      for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
        const series = replayPenPreviewSeriesByFeatureRef.current[feature];
        if (series) chartRef.current?.removeSeries(series);
        replayPenPreviewSeriesByFeatureRef.current[feature] = null;
        replayPenPreviewPointsRef.current[feature] = [];
      }
      for (const s of penSegmentSeriesByKeyRef.current.values()) chartRef.current?.removeSeries(s);
      penSegmentSeriesByKeyRef.current.clear();
      penSegmentsRef.current = [];
      overlayPullInFlightRef.current = false;
      factorPullInFlightRef.current = false;
      factorPullPendingTimeRef.current = null;
      lastFactorAtTimeRef.current = null;
      entryEnabledRef.current = false;
      appliedRef.current = { len: 0, lastTime: null };
      cleanupCanvases();
      anchorTopLayerPathsRef.current = [];
    }
  });

  const fibPreviewTool = useFibPreview({
    enabled: ENABLE_DRAW_TOOLS && activeChartTool === "fib" && fibAnchorA != null,
    anchorA: fibAnchorA,
    chartRef,
    seriesRef,
    candleTimesSecRef,
    containerRef
  });

  useChartDrawToolEffects({
    enableDrawTools: ENABLE_DRAW_TOOLS,
    candles,
    activeChartTool,
    chartEpoch,
    chartRef,
    seriesRef,
    containerRef,
    candleTimesSecRef,
    interactionLockRef,
    measureStateRef,
    setMeasureState,
    setActiveChartTool,
    activeChartToolRef,
    activeToolIdRef,
    fibAnchorARef,
    setFibAnchorA,
    setActiveToolId,
    replayEnabled,
    findReplayIndexByTime,
    setReplayIndexAndFocus,
    genId,
    setPositionTools,
    selectTool,
    setFibTools,
    suppressDeselectUntilRef
  });

  useChartWheelZoomGuard({
    wheelGuardRef,
    chartRef,
    chartEpoch,
    setBarSpacing
  });

  useEffect(() => {
    visibleFeaturesRef.current = visibleFeatures;
  }, [visibleFeatures]);

  const effectiveVisible = useCallback(
    (key: string): boolean => {
      const features = visibleFeaturesRef.current;
      const direct = features[key];
      const visible = direct === undefined ? true : direct;
      const parentKey = parentBySubKey[key];
      if (!parentKey) return visible;
      const parentVisible = features[parentKey];
      return (parentVisible === undefined ? true : parentVisible) && visible;
    },
    [parentBySubKey]
  );

  const { cleanupCanvases } = useOverlayCanvas({
    chartRef,
    seriesRef,
    containerRef,
    overlayActiveIdsRef,
    overlayCatalogRef,
    anchorTopLayerPathsRef,
    anchorPenPointsRef,
    anchorPenIsDashedRef,
    effectiveVisible,
    chartEpoch,
    overlayPaintEpoch,
    anchorHighlightEpoch,
    enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
  });

  useReplayViewportEffects({
    replayEnabled,
    replayFocusTime,
    width,
    height,
    chartEpoch,
    chartRef,
    containerRef,
    setReplayMaskX,
    setBarSpacing
  });

  const syncMarkers = useCallback(() => {
    const markers = [...pivotMarkersRef.current, ...anchorSwitchMarkersRef.current, ...entryMarkersRef.current];
    markersApiRef.current?.setMarkers(markers);
    setPivotCount(pivotMarkersRef.current.length);
  }, []);

  const applyOverlayDelta = useCallback((delta: OverlayLikeDeltaV1) => {
    const { activeIds, nextCursorVersion } = applyOverlayDeltaToCatalog(delta, overlayCatalogRef.current);
    overlayActiveIdsRef.current = activeIds;
    if (nextCursorVersion != null) overlayCursorVersionRef.current = nextCursorVersion;
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
    pivotMarkersRef.current = rebuildPivotMarkersFromOverlayRuntime({
      candlesRef,
      overlayActiveIdsRef,
      overlayCatalogRef,
      effectiveVisible
    });
  }, [effectiveVisible]);

  const rebuildAnchorSwitchMarkersFromOverlay = useCallback(() => {
    const markers = rebuildAnchorSwitchMarkersFromOverlayRuntime({
      candlesRef,
      overlayActiveIdsRef,
      overlayCatalogRef,
      effectiveVisible
    });
    anchorSwitchMarkersRef.current = markers;
    setAnchorSwitchCount(markers.length);
  }, [effectiveVisible]);

  const rebuildPenPointsFromOverlay = useCallback(() => {
    penPointsRef.current = rebuildPenPointsFromOverlayRuntime({
      candlesRef,
      overlayActiveIdsRef,
      overlayCatalogRef
    });
  }, []);

  const rebuildOverlayPolylinesFromOverlay = useCallback(() => {
    rebuildOverlayPolylinesFromOverlayRuntime({
      chart: chartRef.current,
      candlesRef,
      overlayActiveIdsRef,
      overlayCatalogRef,
      effectiveVisible,
      enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
      overlayPolylineSeriesByIdRef,
      anchorTopLayerPathsRef,
      setAnchorTopLayerPathCount,
      setZhongshuCount,
      setAnchorCount,
      setOverlayPaintEpoch
    });
  }, [effectiveVisible]);

  const applyPenAndAnchorFromFactorSlices = useCallback(
    (slices: GetFactorSlicesResponseV1) => {
      applyPenAndAnchorFromFactorSlicesRuntime({
        slices,
        candlesRef,
        replayEnabled,
        enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
        segmentRenderLimit: PEN_SEGMENT_RENDER_LIMIT,
        penSegmentsRef,
        penPointsRef,
        replayPenPreviewPointsRef,
        anchorPenPointsRef,
        anchorPenIsDashedRef,
        setAnchorHighlightEpoch
      });
    },
    [replayEnabled, setAnchorHighlightEpoch]
  );

  const fetchAndApplyAnchorHighlightAtTime = useCallback(
    async (t: number) => {
      await fetchAndApplyAnchorHighlightAtTimeRuntime({
        time: t,
        seriesId,
        windowCandles: INITIAL_TAIL_LIMIT,
        replayEnabled,
        factorPullPendingTimeRef,
        factorPullInFlightRef,
        lastFactorAtTimeRef,
        applyPenAndAnchorFromFactorSlices,
        setReplaySlices
      });
    },
    [applyPenAndAnchorFromFactorSlices, replayEnabled, seriesId, setReplaySlices]
  );

  const applyWorldFrame = useCallback(
    (frame: WorldStateV1) => {
      applyWorldFrameRuntime({
        frame,
        overlayCatalogRef,
        overlayActiveIdsRef,
        overlayCursorVersionRef,
        applyOverlayDelta,
        rebuildPivotMarkersFromOverlay,
        rebuildAnchorSwitchMarkersFromOverlay,
        syncMarkers,
        rebuildPenPointsFromOverlay,
        rebuildOverlayPolylinesFromOverlay,
        enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
        penSegmentsRef,
        penPointsRef,
        setPenPointCount,
        effectiveVisible,
        penSeriesRef,
        applyPenAndAnchorFromFactorSlices
      });
    },
    [
      applyOverlayDelta,
      applyPenAndAnchorFromFactorSlices,
      effectiveVisible,
      rebuildOverlayPolylinesFromOverlay,
      rebuildPenPointsFromOverlay,
      rebuildPivotMarkersFromOverlay,
      rebuildAnchorSwitchMarkersFromOverlay,
      syncMarkers
    ]
  );

  const recomputeActiveIdsFromCatalog = useCallback((params: { cutoffTime: number; toTime: number }): string[] => {
    return recomputeActiveIdsFromCatalogCore({
      overlayCatalog: overlayCatalogRef.current,
      cutoffTime: params.cutoffTime,
      toTime: params.toTime
    });
  }, []);

  const { applyReplayOverlayAtTime, applyReplayPackageWindow } = useReplayOverlayRuntime({
    timeframe,
    windowCandles: INITIAL_TAIL_LIMIT,
    replayEnabled,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    replayPatchRef,
    replayPatchAppliedIdxRef,
    replayWindowIndexRef,
    overlayCatalogRef,
    overlayActiveIdsRef,
    recomputeActiveIdsFromCatalog,
    setReplayDrawInstructions,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay,
    syncMarkers,
    effectiveVisible,
    penSeriesRef,
    penPointsRef,
    penSegmentsRef,
    setPenPointCount
  });

  const requestReplayFrameAtTime = useReplayFrameRequest({
    replayEnabled,
    seriesId,
    windowCandles: INITIAL_TAIL_LIMIT,
    replayFrameLatestTimeRef,
    replayFramePendingTimeRef,
    replayFramePullInFlightRef,
    setReplayFrameLoading,
    setReplayFrameError,
    setReplayFrame,
    applyPenAndAnchorFromFactorSlices,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions
  });

  useChartSeriesSyncEffects({
    candles,
    chartEpoch,
    chartRef,
    seriesRef,
    candlesRef,
    appliedRef,
    lineSeriesByKeyRef,
    entryEnabledRef,
    entryMarkersRef,
    syncMarkers,
    visibleFeatures,
    effectiveVisible,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    rebuildOverlayPolylinesFromOverlay,
    penSeriesRef,
    penSegmentSeriesByKeyRef,
    penSegmentsRef,
    penPointsRef,
    anchorPenSeriesRef,
    anchorPenPointsRef,
    anchorPenIsDashedRef,
    replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
    replayEnabled,
    setPenPointCount,
    anchorHighlightEpoch,
    seriesId
  });

  useChartLiveSessionEffect({
    seriesId,
    timeframe,
    replayEnabled,
    replayPreparedAlignedTime,
    replayPackageEnabled,
    replayPrepareStatus,
    windowCandles: INITIAL_TAIL_LIMIT,
    enableWorldFrame: ENABLE_WORLD_FRAME,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    openMarketWs,
    chartRef,
    candleSeriesRef: seriesRef,
    candlesRef,
    setCandles,
    lastWsCandleTimeRef,
    setLastWsCandleTime,
    appliedRef,
    pivotMarkersRef,
    anchorSwitchMarkersRef,
    overlayCatalogRef,
    overlayActiveIdsRef,
    overlayCursorVersionRef,
    overlayPullInFlightRef,
    overlayPolylineSeriesByIdRef,
    replayPenPreviewSeriesByFeatureRef,
    replayPenPreviewPointsRef,
    followPendingTimeRef,
    followTimerIdRef,
    penSegmentsRef,
    anchorPenPointsRef,
    factorPullPendingTimeRef,
    lastFactorAtTimeRef,
    worldFrameHealthyRef,
    replayAllCandlesRef,
    replayPatchRef,
    replayPatchAppliedIdxRef,
    replayFrameLatestTimeRef,
    penSeriesRef,
    penPointsRef,
    effectiveVisible,
    showToast,
    setError,
    setZhongshuCount,
    setAnchorCount,
    setAnchorHighlightEpoch,
    setPivotCount,
    setAnchorSwitchCount,
    setPenPointCount,
    setReplayTotal,
    setReplayPlaying,
    setReplayIndex,
    applyOverlayDelta,
    fetchOverlayLikeDelta,
    rebuildPivotMarkersFromOverlay,
    rebuildAnchorSwitchMarkersFromOverlay,
    rebuildPenPointsFromOverlay,
    rebuildOverlayPolylinesFromOverlay,
    syncMarkers,
    fetchAndApplyAnchorHighlightAtTime,
    applyWorldFrame,
    applyPenAndAnchorFromFactorSlices
  });

  useReplayPackageResetEffect({
    replayPackageEnabled,
    seriesId,
    setCandles,
    candlesRef,
    replayAllCandlesRef,
    replayWindowIndexRef,
    pivotMarkersRef,
    overlayCatalogRef,
    overlayActiveIdsRef,
    overlayCursorVersionRef,
    overlayPullInFlightRef,
    penSegmentsRef,
    anchorPenPointsRef,
    replayPenPreviewPointsRef,
    factorPullPendingTimeRef,
    lastFactorAtTimeRef,
    replayPatchRef,
    replayPatchAppliedIdxRef,
    setAnchorHighlightEpoch,
    setPivotCount,
    setPenPointCount,
    setError,
    setReplayIndex,
    setReplayPlaying,
    setReplayTotal,
    setReplayFocusTime,
    setReplayFrame,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions
  });

  useReplayPackageWindowSync({
    enabled: replayPackageEnabled,
    status: replayPackageStatus,
    metadata: replayPackageMeta,
    windows: replayPackageWindows,
    historyEvents: replayPackageHistory,
    ensureWindowRange: replayEnsureWindowRange,
    replayIndex,
    replayFocusTime,
    seriesId,
    replayAllCandlesRef,
    lastFactorAtTimeRef,
    candlesRef,
    toReplayCandle,
    applyReplayPackageWindow,
    buildReplayFactorSlices: useCallback((args) => buildReplayFactorSlices({ ...args, seriesId }), [seriesId]),
    applyPenAndAnchorFromFactorSlices,
    setReplayTotal,
    setReplayIndex,
    setReplayFocusTime,
    setReplaySlices,
    setReplayCandle,
    setCandles
  });

  useReplayFocusSyncEffect({
    replayEnabled,
    replayPackageEnabled,
    replayIndex,
    replayTotal,
    replayAllCandlesRef,
    setReplayIndex,
    setReplayFocusTime,
    applyReplayOverlayAtTime,
    fetchAndApplyAnchorHighlightAtTime,
    requestReplayFrameAtTime
  });

  return (
    <div
      ref={wheelGuardRef}
      data-testid="chart-view"
      data-series-id={seriesId}
      data-candles-len={String(candles.length)}
      data-last-time={candles.length ? String(candles[candles.length - 1]!.time) : ""}
      data-last-open={candles.length ? String(candles[candles.length - 1]!.open) : ""}
      data-last-high={candles.length ? String(candles[candles.length - 1]!.high) : ""}
      data-last-low={candles.length ? String(candles[candles.length - 1]!.low) : ""}
      data-last-close={candles.length ? String(candles[candles.length - 1]!.close) : ""}
      data-last-ws-candle-time={lastWsCandleTime != null ? String(lastWsCandleTime) : ""}
      data-chart-epoch={String(chartEpoch)}
      data-bar-spacing={barSpacing != null ? String(barSpacing) : ""}
      data-pivot-count={String(pivotCount)}
      data-pen-point-count={String(penPointCount)}
      data-zhongshu-count={String(zhongshuCount)}
      data-anchor-count={String(anchorCount)}
      data-anchor-switch-count={String(anchorSwitchCount)}
      data-anchor-on={anchorCount > 0 ? "1" : "0"}
      data-anchor-top-layer={ENABLE_ANCHOR_TOP_LAYER ? "1" : "0"}
      data-anchor-top-layer-path-count={String(anchorTopLayerPathCount)}
      data-replay-mode={replayEnabled ? "replay" : "live"}
      data-replay-index={String(replayIndex)}
      data-replay-total={String(replayTotal)}
      data-replay-focus-time={replayFocusTime != null ? String(replayFocusTime) : ""}
      data-replay-playing={replayPlaying ? "1" : "0"}
      className="relative h-full w-full"
      title={error ?? undefined}
    >
      <div
        ref={(el) => {
          containerRef.current = el;
          resizeRef(el);
        }}
        className="h-full w-full"
      />

      <ChartViewOverlayLayer
        replayEnabled={replayEnabled}
        replayMaskX={replayMaskX}
        enableDrawTools={ENABLE_DRAW_TOOLS}
        activeChartTool={activeChartTool}
        containerRef={containerRef}
        candleTimesSec={candleTimesSecRef.current}
        measureState={measureState}
        positionTools={positionTools}
        fibTools={fibTools}
        fibPreviewTool={fibPreviewTool}
        activeToolId={activeToolId}
        chartRef={chartRef}
        seriesRef={seriesRef}
        onUpdatePositionTool={updatePositionTool}
        onRemovePositionTool={removePositionTool}
        onUpdateFibTool={updateFibTool}
        onRemoveFibTool={removeFibTool}
        onSelectTool={selectTool}
        onInteractionLockChange={(locked) => {
          interactionLockRef.current.dragging = locked;
        }}
        error={error}
        candlesLength={candles.length}
        toastMessage={toastMessage}
      />
    </div>
  );
}
