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
  const chartState = useChartViewState(LIVE_LOAD_STATUS_LABELS);
  const lastWsCandleTimeRef = useRef<number | null>(null);
  const exchange = useUiStore((state) => state.exchange);
  const market = useUiStore((state) => state.market);
  const symbol = useUiStore((state) => state.symbol);
  const timeframe = useUiStore((state) => state.timeframe);
  const activeChartTool = useUiStore((state) => state.activeChartTool);
  const setActiveChartTool = useUiStore((state) => state.setActiveChartTool);
  const replay = useReplayBindings();
  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);
  const visibleFeatures = useFactorStore((state) => state.visibleFeatures);
  const factorCatalog = useFactorCatalog();
  const visibleFeaturesRef = useRef(visibleFeatures);
  const parentBySubKey = useMemo(() => getFactorParentsBySubKey(factorCatalog), [factorCatalog]);
  const replayEnabled = ENABLE_REPLAY_V1 && replay.replayMode === "replay";
  const runtimeRefs = useChartRuntimeRefs(ENABLE_WORLD_FRAME);
  const { candlesRef, candleTimesSecRef, appliedRef } = runtimeRefs;

  useEffect(() => {
    runtimeRefs.activeSeriesIdRef.current = seriesId;
  }, [seriesId]);
  const replayPackage = useReplayPackage({
    seriesId,
    enabled: replayEnabled && replay.replayPrepareStatus === "ready",
    windowCandles: REPLAY_WINDOW_CANDLES,
    windowSize: REPLAY_WINDOW_SIZE,
    snapshotInterval: REPLAY_SNAPSHOT_INTERVAL
  });
  const replayPackageEnabled = replayEnabled && replay.replayPrepareStatus === "ready" && replayPackage.enabled;
  const replayPackageStatus = replayPackage.status;
  const replayPackageMeta = replayPackage.metadata;
  const replayPackageWindows = replayPackage.windows;
  const replayEnsureWindowRange = replayPackage.ensureWindowRange;

  const { setReplayIndexAndFocus } = useReplayController({
    seriesId,
    replayEnabled,
    replayPlaying: replay.replayPlaying,
    replaySpeedMs: replay.replaySpeedMs,
    replayIndex: replay.replayIndex,
    replayTotal: replay.replayTotal,
    windowCandles: INITIAL_TAIL_LIMIT,
    resetReplayData: replay.resetReplayData,
    setReplayPlaying: replay.setReplayPlaying,
    setReplayIndex: replay.setReplayIndex,
    setReplayPrepareStatus: replay.setReplayPrepareStatus,
    setReplayPrepareError: replay.setReplayPrepareError,
    setReplayPreparedAlignedTime: replay.setReplayPreparedAlignedTime
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
      applyChartLifecycleCleanup({ chartRef, appliedRef, runtimeRefs });
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
    candles: chartState.candles,
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
    setBarSpacing: chartState.setBarSpacing
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
  const bindContainerRef = useCallback(
    (el: HTMLDivElement | null) => {
      containerRef.current = el;
      resizeRef(el);
    },
    [resizeRef]
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
    replayFocusTime: replay.replayFocusTime,
    width,
    height,
    chartEpoch,
    chartRef,
    containerRef,
    setReplayMaskX: chartState.setReplayMaskX,
    setBarSpacing: chartState.setBarSpacing
  });
  const runtimeCallbacks = useChartRuntimeCallbacks({
    ...runtimeRefs,
    seriesId,
    windowCandles: INITIAL_TAIL_LIMIT,
    replayEnabled,
    enablePenSegmentColor: ENABLE_PEN_SEGMENT_COLOR,
    enableAnchorTopLayer: ENABLE_ANCHOR_TOP_LAYER,
    segmentRenderLimit: PEN_SEGMENT_RENDER_LIMIT,
    chartRef,
    markersApiRef,
    candlesRef,
    effectiveVisible,
    setReplaySlices: replay.setReplaySlices,
    setReplayDrawInstructions: replay.setReplayDrawInstructions,
    setReplayCandle: replay.setReplayCandle
  });
  useChartRuntimeEffects({
    seriesId,
    timeframe,
    replayEnabled,
    replayPreparedAlignedTime: replay.replayPreparedAlignedTime,
    replayPrepareStatus: replay.replayPrepareStatus,
    replayPackageEnabled,
    replayPackageStatus,
    replayPackageMeta,
    replayPackageWindows,
    replayEnsureWindowRange,
    replayIndex: replay.replayIndex,
    replayTotal: replay.replayTotal,
    replayFocusTime: replay.replayFocusTime,
    candles: chartState.candles,
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
    setCandles: chartState.setCandles,
    setReplayTotal: replay.setReplayTotal,
    setReplayPlaying: replay.setReplayPlaying,
    setReplayIndex: replay.setReplayIndex,
    setReplayFocusTime: replay.setReplayFocusTime,
    setReplaySlices: replay.setReplaySlices,
    setReplayCandle: replay.setReplayCandle,
    setReplayDrawInstructions: replay.setReplayDrawInstructions,
    setLastWsCandleTime: chartState.setLastWsCandleTime,
    setLiveLoadState: chartState.updateLiveLoadState,
    setError: chartState.setError,
    showToast: chartState.showToast,
    ...runtimeRefs,
    ...runtimeCallbacks
  });
  const lastCandle = chartState.candles.length > 0 ? chartState.candles[chartState.candles.length - 1]! : null;
  const anchorHighlightPoints = runtimeRefs.anchorPenPointsRef.current;
  const anchorHighlightPointCount = anchorHighlightPoints?.length ?? 0;
  const anchorHighlightStartTime =
    anchorHighlightPointCount > 0 ? Number(anchorHighlightPoints?.[0]?.time ?? 0) : null;
  const anchorHighlightEndTime =
    anchorHighlightPointCount > 0 ? Number(anchorHighlightPoints?.[anchorHighlightPointCount - 1]?.time ?? 0) : null;

  return (
    <ChartViewShell
      wheelGuardRef={wheelGuardRef}
      bindContainerRef={bindContainerRef}
      seriesId={seriesId}
      candlesLength={chartState.candles.length}
      lastCandle={lastCandle}
      lastWsCandleTime={chartState.lastWsCandleTime}
      chartEpoch={chartEpoch}
      barSpacing={chartState.barSpacing}
      pivotCount={runtimeRefs.pivotCount}
      penPointCount={runtimeRefs.penPointCount}
      zhongshuCount={runtimeRefs.zhongshuCount}
      anchorCount={runtimeRefs.anchorCount}
      anchorSwitchCount={runtimeRefs.anchorSwitchCount}
      anchorHighlightPointCount={anchorHighlightPointCount}
      anchorHighlightStartTime={anchorHighlightStartTime}
      anchorHighlightEndTime={anchorHighlightEndTime}
      anchorHighlightDashed={runtimeRefs.anchorPenIsDashedRef.current}
      enableAnchorTopLayer={ENABLE_ANCHOR_TOP_LAYER}
      anchorTopLayerPathCount={runtimeRefs.anchorTopLayerPathCount}
      replayEnabled={replayEnabled}
      replayIndex={replay.replayIndex}
      replayTotal={replay.replayTotal}
      replayFocusTime={replay.replayFocusTime}
      replayPlaying={replay.replayPlaying}
      error={chartState.error}
      replayMaskX={chartState.replayMaskX}
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
      liveLoadStatus={chartState.liveLoadStatus}
      liveLoadMessage={chartState.liveLoadMessage}
      toastMessage={chartState.toastMessage}
    />
  );
}
