import { logDebugEvent } from "../../debug/debug";
import { fetchCandles, fetchDrawDelta } from "./api";
import {
  applyOverlayBaseline,
  loadWorldFrameLiveWithRetry,
  runOverlayFollowNow,
  scheduleOverlayFollow
} from "./liveSessionOverlayFollow";
import { timeframeToSeconds } from "./timeframe";
import type {
  ReplayPenPreviewFeature,
  StartChartLiveSessionArgs,
  StartChartLiveSessionOptions
} from "./liveSessionRuntimeTypes";
import { buildLiveSessionWsHandlers } from "./liveSessionWsHandlers";
type CandleFetchResult = Awaited<ReturnType<typeof fetchCandles>>;
type CandleFetchSummary = {
  count: number;
  headTime: number | null;
  lastTime: number | null;
  contiguous: boolean;
};
function clearOverlayFollowTimer(ref: { current: number | null }) {
  if (ref.current == null) return;
  window.clearTimeout(ref.current);
  ref.current = null;
}
function resetLiveSessionRuntime(args: StartChartLiveSessionArgs) {
  const chart = args.chartRef.current;
  args.setCandles([]);
  args.candlesRef.current = [];
  args.candleSeriesRef.current?.setData([]);
  args.setLiveLoadState("loading", "正在加载K线...");
  args.lastWsCandleTimeRef.current = null;
  args.setLastWsCandleTime(null);
  args.appliedRef.current = { len: 0, lastTime: null };
  args.pivotMarkersRef.current = [];
  args.anchorSwitchMarkersRef.current = [];
  args.overlayCatalogRef.current.clear();
  args.overlayActiveIdsRef.current.clear();
  args.overlayCursorVersionRef.current = 0;
  args.overlayPullInFlightRef.current = false;
  args.rebuildPivotMarkersFromOverlay();
  args.rebuildAnchorSwitchMarkersFromOverlay();
  args.syncMarkers();
  args.rebuildPenPointsFromOverlay();
  args.rebuildOverlayPolylinesFromOverlay();
  if (chart) {
    for (const series of args.overlayPolylineSeriesByIdRef.current.values()) chart.removeSeries(series);
    for (const feature of ["pen.extending", "pen.candidate"] as ReplayPenPreviewFeature[]) {
      const series = args.replayPenPreviewSeriesByFeatureRef.current[feature];
      if (series) chart.removeSeries(series);
      args.replayPenPreviewSeriesByFeatureRef.current[feature] = null;
    }
  }
  args.overlayPolylineSeriesByIdRef.current.clear();
  args.setZhongshuCount(0);
  args.setAnchorCount(0);
  args.followPendingTimeRef.current = null;
  clearOverlayFollowTimer(args.followTimerIdRef);
  args.penSegmentsRef.current = [];
  args.penPointsRef.current = [];
  args.penSeriesRef.current?.setData([]);
  args.anchorPenPointsRef.current = null;
  args.replayPenPreviewPointsRef.current["pen.extending"] = [];
  args.replayPenPreviewPointsRef.current["pen.candidate"] = [];
  args.factorPullPendingTimeRef.current = null;
  args.factorPullInFlightRef.current = false;
  args.lastFactorAtTimeRef.current = null;
  args.setAnchorHighlightEpoch((value) => value + 1);
  args.setPivotCount(0);
  args.setAnchorSwitchCount(0);
  args.setPenPointCount(0);
  args.setError(null);
  args.worldFrameHealthyRef.current = args.enableWorldFrame;
}
function summarizeInitialCandles(result: CandleFetchResult, timeframeSeconds: number | null): CandleFetchSummary {
  const candles = result.candles;
  const count = candles.length;
  const headTime = result.headTime == null ? null : Number(result.headTime);
  const lastTime = count > 0 ? Number(candles[count - 1]!.time) : null;
  if (count <= 1) {
    return { count, headTime, lastTime, contiguous: count === 1 };
  }
  if (timeframeSeconds == null || timeframeSeconds <= 0) {
    let monotonic = true;
    for (let i = 1; i < count; i += 1) {
      if (Number(candles[i]!.time) <= Number(candles[i - 1]!.time)) {
        monotonic = false;
        break;
      }
    }
    return { count, headTime, lastTime, contiguous: monotonic };
  }
  let contiguous = true;
  for (let i = 1; i < count; i += 1) {
    const prev = Number(candles[i - 1]!.time);
    const current = Number(candles[i]!.time);
    if (current - prev !== timeframeSeconds) {
      contiguous = false;
      break;
    }
  }
  return { count, headTime, lastTime, contiguous };
}
function isInitialCandlesReady(args: {
  summary: CandleFetchSummary;
  previous: CandleFetchSummary | null;
  windowCandles: number;
}): boolean {
  const { summary, previous, windowCandles } = args;
  if (summary.count <= 0) return false;
  if (summary.lastTime == null) return false;
  if (summary.headTime != null && summary.lastTime !== summary.headTime) return false;
  if (summary.count > 1 && !summary.contiguous) return false;
  if (summary.count > 1) return true;
  const target = Math.max(1, Number(windowCandles));
  if (summary.count >= target) return true;
  if (previous == null) return false;
  const stable =
    previous.count === summary.count &&
    previous.headTime === summary.headTime &&
    previous.lastTime === summary.lastTime &&
    previous.contiguous === summary.contiguous;
  return stable;
}
async function waitForInitialCandles(args: StartChartLiveSessionOptions) {
  args.setLiveLoadState("loading", "正在加载K线...");
  let initial = await fetchCandles({ seriesId: args.seriesId, limit: args.windowCandles });
  if (args.replayEnabled) return initial;
  const retryLimit = 20;
  let retryDelayMs = 200;
  const timeframeSeconds = timeframeToSeconds(args.timeframe);
  let previous: CandleFetchSummary | null = null;
  for (let attempt = 0; attempt <= retryLimit; attempt += 1) {
    if (!args.isActive()) return initial;
    const summary = summarizeInitialCandles(initial, timeframeSeconds);
    if (
      isInitialCandlesReady({
        summary,
        previous,
        windowCandles: args.windowCandles
      })
    ) {
      return initial;
    }
    const unchanged =
      previous != null &&
      previous.count === summary.count &&
      previous.headTime === summary.headTime &&
      previous.lastTime === summary.lastTime &&
      previous.contiguous === summary.contiguous;
    previous = summary;
    if (attempt >= retryLimit) break;
    args.setLiveLoadState("backfilling", "正在补历史K线...");
    await new Promise((resolve) => window.setTimeout(resolve, retryDelayMs));
    retryDelayMs = unchanged ? Math.min(1000, retryDelayMs + 150) : 200;
    try {
      initial = await fetchCandles({
        seriesId: args.seriesId,
        limit: args.windowCandles,
        bypassCache: true
      });
    } catch {
      // ignore transient fetch errors while background coverage catches up
    }
  }
  return initial;
}
async function runLiveSession(args: StartChartLiveSessionOptions): Promise<WebSocket | null> {
  resetLiveSessionRuntime(args);
  let cursor = 0;
  const initial = await waitForInitialCandles(args);
  if (!args.isActive()) return null;
  logDebugEvent({
    pipe: "read",
    event: "read.http.market_candles_result",
    series_id: args.seriesId,
    level: "info",
    message: "initial candles loaded",
    data: { count: initial.candles.length }
  });
  if (initial.candles.length > 0) {
    args.setLiveLoadState("ready");
    if (args.replayEnabled) {
      logDebugEvent({
        pipe: "read",
        event: "read.replay.load_initial",
        series_id: args.seriesId,
        level: "info",
        message: "replay initial load",
        data: { count: initial.candles.length }
      });
      args.replayAllCandlesRef.current = initial.candles;
      args.replayPatchRef.current = [];
      args.replayPatchAppliedIdxRef.current = 0;
      args.overlayCatalogRef.current.clear();
      args.overlayActiveIdsRef.current.clear();
      args.overlayCursorVersionRef.current = 0;
      args.replayFrameLatestTimeRef.current = null;
      const endTime = args.replayPreparedAlignedTime ?? (initial.candles[initial.candles.length - 1]!.time as number);
      try {
        const draw = await fetchDrawDelta({
          seriesId: args.seriesId,
          cursorVersionId: 0,
          windowCandles: args.windowCandles,
          atTime: endTime
        });
        if (!args.isActive()) return null;
        const raw = Array.isArray(draw.instruction_catalog_patch) ? draw.instruction_catalog_patch : [];
        args.replayPatchRef.current = raw
          .slice()
          .sort((a, b) => (a.visible_time - b.visible_time !== 0 ? a.visible_time - b.visible_time : a.version_id - b.version_id));
      } catch {
        args.replayPatchRef.current = [];
      }
      args.candlesRef.current = initial.candles;
      args.setCandles(initial.candles);
      args.setReplayTotal(initial.candles.length);
      args.setReplayPlaying(false);
      const lastIdx = Math.max(0, initial.candles.length - 1);
      args.setReplayIndex(lastIdx);
      return null;
    }
    args.candlesRef.current = initial.candles;
    args.setCandles(initial.candles);
    cursor = initial.candles[initial.candles.length - 1]!.time as number;
  } else if (!args.replayEnabled) {
    args.setLiveLoadState("empty", "暂无K线，等待后台同步...");
  }
  try {
    if (args.enableWorldFrame && !args.replayEnabled && args.worldFrameHealthyRef.current) {
      const frame = await loadWorldFrameLiveWithRetry(args);
      if (!args.isActive()) return null;
      if (frame) {
        args.applyWorldFrame(frame);
      } else {
        args.worldFrameHealthyRef.current = false;
        await applyOverlayBaseline(args, cursor);
      }
    } else {
      await applyOverlayBaseline(args, cursor);
    }
  } catch {
    args.worldFrameHealthyRef.current = false;
    try {
      await applyOverlayBaseline(args, cursor);
    } catch {
      // ignore overlay/frame errors (best-effort)
    }
  }
  const schedule = (time: number) =>
    scheduleOverlayFollow(args, (value) => runOverlayFollowNow(args, value, schedule), time);
  if (!args.replayEnabled && cursor > 0) {
    schedule(cursor);
  }
  const handlers = buildLiveSessionWsHandlers(args, schedule);
  return args.openMarketWs({
    since: cursor > 0 ? cursor : null,
    isActive: args.isActive,
    ...handlers
  });
}
export function startChartLiveSession(args: StartChartLiveSessionArgs): { stop: () => void } {
  let active = true;
  let ws: WebSocket | null = null;
  const options: StartChartLiveSessionOptions = {
    ...args,
    isActive: () => active
  };
  void runLiveSession(options)
    .then((socket) => {
      if (!active) {
        socket?.close();
        return;
      }
      ws = socket;
    })
    .catch((error: unknown) => {
      if (!active) return;
      const message = error instanceof Error ? error.message : "Failed to load market candles";
      args.setError(message);
      args.setLiveLoadState("error", message);
    });
  return {
    stop: () => {
      active = false;
      clearOverlayFollowTimer(args.followTimerIdRef);
      args.factorPullPendingTimeRef.current = null;
      args.factorPullInFlightRef.current = false;
      ws?.close();
      args.setCandles([]);
      args.candleSeriesRef.current?.setData([]);
      args.setLiveLoadState("idle");
    }
  };
}
