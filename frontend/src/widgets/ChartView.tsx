import { useCallback, useEffect, useMemo, useRef } from "react";
import useResizeObserver from "use-resize-observer";
import { getFactorParentsBySubKey, useFactorCatalog } from "../services/factorCatalog";
import { useFactorStore } from "../state/factorStore";
import { useUiStore } from "../state/uiStore";
import { ChartViewShell } from "./chart/ChartViewShell";
import { applyChartLifecycleCleanup, applyChartLifecycleCreated } from "./chart/chartLifecycleRuntime";
import { useChartRuntimeEffects } from "./chart/chartRuntimeEffects";
import { useChartDrawToolRuntime } from "./chart/useChartDrawToolRuntime";
import { useChartRuntimeCallbacks } from "./chart/chartRuntimeCallbacks";
import { toReplayCandle } from "./chart/useReplayRuntimeCallbacks";
import type { LiveLoadStatus } from "./chart/liveSessionRuntimeTypes";
import { useLightweightChart } from "./chart/useLightweightChart";
import { useOverlayCanvas } from "./chart/useOverlayCanvas";
import { useReplayBindings } from "./chart/useReplayBindings";
import { useReplayController } from "./chart/useReplayController";
import { useReplayPackage } from "./chart/useReplayPackage";
import { useChartRuntimeRefs } from "./chart/useChartRuntimeRefs";
import { useChartViewState } from "./chart/useChartViewState";
import { useWsSync } from "./chart/useWsSync";
import { useChartWheelZoomGuard, useReplayViewportEffects } from "./chart/useChartViewportEffects";

const INITIAL_TAIL_LIMIT = 2000;
const ENABLE_REPLAY_V1 = String(import.meta.env.VITE_ENABLE_REPLAY_V1 ?? "1") === "1";
const ENABLE_PEN_SEGMENT_COLOR = import.meta.env.VITE_ENABLE_PEN_SEGMENT_COLOR === "1";
const ENABLE_ANCHOR_TOP_LAYER = String(import.meta.env.VITE_ENABLE_ANCHOR_TOP_LAYER ?? "1") === "1";
const ENABLE_WORLD_FRAME = String(import.meta.env.VITE_ENABLE_WORLD_FRAME ?? "1") === "1";
const PEN_SEGMENT_RENDER_LIMIT = 200;
const ENABLE_DRAW_TOOLS = String(import.meta.env.VITE_ENABLE_DRAW_TOOLS ?? "1") === "1";
const REPLAY_WINDOW_CANDLES = 2000, REPLAY_WINDOW_SIZE = 500, REPLAY_SNAPSHOT_INTERVAL = 25;
const LIVE_LOAD_STATUS_LABELS: Record<LiveLoadStatus, string> = { idle: "准备加载K线...", loading: "正在加载K线...", backfilling: "正在补历史K线...", ready: "K线已就绪", empty: "暂无K线，等待后台同步...", error: "K线加载失败" };

export function ChartView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const { ref: resizeRef, width, height } = useResizeObserver<HTMLDivElement>();
  const wheelGuardRef = useRef<HTMLDivElement | null>(null);

  const {
    candles,
    setCandles,
    barSpacing,
    setBarSpacing,
    lastWsCandleTime,
    setLastWsCandleTime,
    error,
    setError,
    liveLoadStatus,
    liveLoadMessage,
    updateLiveLoadState,
    toastMessage,
    showToast,
    replayMaskX,
    setReplayMaskX
  } = useChartViewState(LIVE_LOAD_STATUS_LABELS);
  const lastWsCandleTimeRef = useRef<number | null>(null);
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
  const replayEnabled = ENABLE_REPLAY_V1 && replayMode === "replay";
  const runtimeRefs = useChartRuntimeRefs(ENABLE_WORLD_FRAME);
  const { candlesRef, candleTimesSecRef, appliedRef } = runtimeRefs;

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

  const { chartRef, candleSeriesRef: seriesRef, markersApiRef, chartEpoch } = useLightweightChart({
    containerRef,
    width,
    height,
    onCreated: ({ chart, candleSeries }) => {
      applyChartLifecycleCreated({ chart, candleSeries, candlesRef, appliedRef });
    },
    onCleanup: () => {
      applyChartLifecycleCleanup({
        chartRef,
        lineSeriesByKeyRef: runtimeRefs.lineSeriesByKeyRef,
        entryMarkersRef: runtimeRefs.entryMarkersRef,
        pivotMarkersRef: runtimeRefs.pivotMarkersRef,
        overlayCatalogRef: runtimeRefs.overlayCatalogRef,
        overlayActiveIdsRef: runtimeRefs.overlayActiveIdsRef,
        overlayCursorVersionRef: runtimeRefs.overlayCursorVersionRef,
        penPointsRef: runtimeRefs.penPointsRef,
        penSeriesRef: runtimeRefs.penSeriesRef,
        anchorPenPointsRef: runtimeRefs.anchorPenPointsRef,
        anchorPenIsDashedRef: runtimeRefs.anchorPenIsDashedRef,
        anchorPenSeriesRef: runtimeRefs.anchorPenSeriesRef,
        replayPenPreviewSeriesByFeatureRef: runtimeRefs.replayPenPreviewSeriesByFeatureRef,
        replayPenPreviewPointsRef: runtimeRefs.replayPenPreviewPointsRef,
        penSegmentSeriesByKeyRef: runtimeRefs.penSegmentSeriesByKeyRef,
        penSegmentsRef: runtimeRefs.penSegmentsRef,
        overlayPullInFlightRef: runtimeRefs.overlayPullInFlightRef,
        factorPullInFlightRef: runtimeRefs.factorPullInFlightRef,
        factorPullPendingTimeRef: runtimeRefs.factorPullPendingTimeRef,
        lastFactorAtTimeRef: runtimeRefs.lastFactorAtTimeRef,
        entryEnabledRef: runtimeRefs.entryEnabledRef,
        appliedRef,
        anchorTopLayerPathsRef: runtimeRefs.anchorTopLayerPathsRef
      });
      cleanupCanvases();
    }
  });

  const {
    positionTools,
    fibTools,
    activeToolId,
    measureState,
    fibPreviewTool,
    interactionLockRef,
    updatePositionTool,
    removePositionTool,
    updateFibTool,
    removeFibTool,
    selectTool
  } = useChartDrawToolRuntime({
    enableDrawTools: ENABLE_DRAW_TOOLS,
    activeChartTool,
    setActiveChartTool,
    seriesId,
    candles,
    candlesRef,
    candleTimesSecRef,
    chartEpoch,
    chartRef,
    seriesRef,
    containerRef,
    replayEnabled,
    setReplayIndexAndFocus
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
    overlayActiveIdsRef: runtimeRefs.overlayActiveIdsRef,
    overlayCatalogRef: runtimeRefs.overlayCatalogRef,
    anchorTopLayerPathsRef: runtimeRefs.anchorTopLayerPathsRef,
    anchorPenPointsRef: runtimeRefs.anchorPenPointsRef,
    anchorPenIsDashedRef: runtimeRefs.anchorPenIsDashedRef,
    effectiveVisible,
    chartEpoch,
    overlayPaintEpoch: runtimeRefs.overlayPaintEpoch,
    anchorHighlightEpoch: runtimeRefs.anchorHighlightEpoch,
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

  const runtimeCallbacks = useChartRuntimeCallbacks({
    seriesId,
    timeframe,
    replayEnabled,
    windowCandles: INITIAL_TAIL_LIMIT,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
    segmentRenderLimit: PEN_SEGMENT_RENDER_LIMIT,
    chartRef,
    markersApiRef,
    candlesRef,
    overlayActiveIdsRef: runtimeRefs.overlayActiveIdsRef,
    overlayCatalogRef: runtimeRefs.overlayCatalogRef,
    overlayCursorVersionRef: runtimeRefs.overlayCursorVersionRef,
    overlayPolylineSeriesByIdRef: runtimeRefs.overlayPolylineSeriesByIdRef,
    anchorTopLayerPathsRef: runtimeRefs.anchorTopLayerPathsRef,
    pivotMarkersRef: runtimeRefs.pivotMarkersRef,
    anchorSwitchMarkersRef: runtimeRefs.anchorSwitchMarkersRef,
    entryMarkersRef: runtimeRefs.entryMarkersRef,
    setPivotCount: runtimeRefs.setPivotCount,
    setAnchorSwitchCount: runtimeRefs.setAnchorSwitchCount,
    setAnchorTopLayerPathCount: runtimeRefs.setAnchorTopLayerPathCount,
    setZhongshuCount: runtimeRefs.setZhongshuCount,
    setAnchorCount: runtimeRefs.setAnchorCount,
    setOverlayPaintEpoch: runtimeRefs.setOverlayPaintEpoch,
    penSeriesRef: runtimeRefs.penSeriesRef,
    penPointsRef: runtimeRefs.penPointsRef,
    penSegmentsRef: runtimeRefs.penSegmentsRef,
    penSegmentSeriesByKeyRef: runtimeRefs.penSegmentSeriesByKeyRef,
    anchorPenPointsRef: runtimeRefs.anchorPenPointsRef,
    anchorPenIsDashedRef: runtimeRefs.anchorPenIsDashedRef,
    replayPenPreviewPointsRef: runtimeRefs.replayPenPreviewPointsRef,
    replayPenPreviewSeriesByFeatureRef: runtimeRefs.replayPenPreviewSeriesByFeatureRef,
    factorPullPendingTimeRef: runtimeRefs.factorPullPendingTimeRef,
    factorPullInFlightRef: runtimeRefs.factorPullInFlightRef,
    lastFactorAtTimeRef: runtimeRefs.lastFactorAtTimeRef,
    replayPatchRef: runtimeRefs.replayPatchRef,
    replayPatchAppliedIdxRef: runtimeRefs.replayPatchAppliedIdxRef,
    replayWindowIndexRef: runtimeRefs.replayWindowIndexRef,
    replayFrameLatestTimeRef: runtimeRefs.replayFrameLatestTimeRef,
    replayFramePendingTimeRef: runtimeRefs.replayFramePendingTimeRef,
    replayFramePullInFlightRef: runtimeRefs.replayFramePullInFlightRef,
    effectiveVisible,
    setPenPointCount: runtimeRefs.setPenPointCount,
    setAnchorHighlightEpoch: runtimeRefs.setAnchorHighlightEpoch,
    setReplaySlices,
    setReplayDrawInstructions,
    setReplayFrameLoading,
    setReplayFrameError,
    setReplayFrame,
    setReplayCandle
  });

  useChartRuntimeEffects({
    seriesId,
    timeframe,
    replayEnabled,
    replayPreparedAlignedTime,
    replayPrepareStatus,
    replayPackageEnabled,
    replayPackageStatus,
    replayPackageMeta,
    replayPackageHistory,
    replayPackageWindows,
    replayEnsureWindowRange,
    replayIndex,
    replayTotal,
    replayFocusTime,
    candles,
    visibleFeatures,
    chartEpoch,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
    enableWorldFrame: ENABLE_WORLD_FRAME,
    windowCandles: INITIAL_TAIL_LIMIT,
    chartRef,
    seriesRef,
    lastWsCandleTimeRef,
    effectiveVisible,
    openMarketWs,
    toReplayCandle,
    setCandles,
    setReplayTotal,
    setReplayPlaying,
    setReplayIndex,
    setReplayFocusTime,
    setReplayFrame,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions,
    setReplayFrameLoading,
    setReplayFrameError,
    setLastWsCandleTime,
    setLiveLoadState: updateLiveLoadState,
    setError,
    showToast,
    ...runtimeRefs,
    ...runtimeCallbacks
  });

  const lastCandle = candles.length > 0 ? candles[candles.length - 1]! : null;

  return (
    <ChartViewShell
      wheelGuardRef={wheelGuardRef}
      bindContainerRef={(el) => {
        containerRef.current = el;
        resizeRef(el);
      }}
      seriesId={seriesId}
      candlesLength={candles.length}
      lastCandle={lastCandle}
      lastWsCandleTime={lastWsCandleTime}
      chartEpoch={chartEpoch}
      barSpacing={barSpacing}
      pivotCount={runtimeRefs.pivotCount}
      penPointCount={runtimeRefs.penPointCount}
      zhongshuCount={runtimeRefs.zhongshuCount}
      anchorCount={runtimeRefs.anchorCount}
      anchorSwitchCount={runtimeRefs.anchorSwitchCount}
      enableAnchorTopLayer={ENABLE_ANCHOR_TOP_LAYER}
      anchorTopLayerPathCount={runtimeRefs.anchorTopLayerPathCount}
      replayEnabled={replayEnabled}
      replayIndex={replayIndex}
      replayTotal={replayTotal}
      replayFocusTime={replayFocusTime}
      replayPlaying={replayPlaying}
      error={error}
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
      liveLoadStatus={liveLoadStatus}
      liveLoadMessage={liveLoadMessage}
      toastMessage={toastMessage}
    />
  );
}
