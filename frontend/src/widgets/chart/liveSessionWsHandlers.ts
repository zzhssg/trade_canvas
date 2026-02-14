import { logDebugEvent } from "../../debug/debug";

import { fetchCandles } from "./api";
import { mergeCandlesWindow, mergeCandleWindow, toChartCandle } from "./candles";
import { timeframeToSeconds } from "./timeframe";
import { computePenPointCount, loadWorldFrameLiveWithRetry } from "./liveSessionOverlayFollow";
import type { OpenMarketWs, StartChartLiveSessionOptions } from "./liveSessionRuntimeTypes";

type LiveSessionWsHandlers = Omit<Parameters<OpenMarketWs>[0], "since" | "isActive">;

export function buildLiveSessionWsHandlers(
  args: StartChartLiveSessionOptions,
  schedule: (time: number) => void
): LiveSessionWsHandlers {
  return {
    onCandlesBatch: (msg) => {
      const last = msg.candles.length > 0 ? msg.candles[msg.candles.length - 1] : null;
      const time = last ? last.candle_time : null;
      if (time != null) {
        args.lastWsCandleTimeRef.current = time;
        args.setLastWsCandleTime(time);
      }

      args.setCandles((prev) => {
        const next = mergeCandlesWindow(prev, msg.candles.map(toChartCandle), args.windowCandles);
        args.candlesRef.current = next;
        if (next.length > 0) args.setLiveLoadState("ready");
        return next;
      });

      if (time != null) {
        logDebugEvent({
          pipe: "read",
          event: "read.ws.market_candles_batch",
          series_id: args.seriesId,
          level: "info",
          message: "ws candles batch",
          data: { count: msg.candles.length, last_time: time }
        });
      }

      if (time != null) schedule(time);
    },
    onSystem: (msg) => {
      if (msg.event !== "factor.rebuild") return;
      args.showToast(msg.message || "因子已自动重算");
      logDebugEvent({
        pipe: "read",
        event: "read.ws.system.factor_rebuild",
        series_id: args.seriesId,
        level: "warn",
        message: msg.message || "factor rebuild",
        data: msg.data
      });
    },
    onCandleForming: (msg) => {
      const next = toChartCandle(msg.candle);
      args.candlesRef.current = mergeCandleWindow(args.candlesRef.current, next, args.windowCandles);
      args.setCandles((prev) => {
        const merged = mergeCandleWindow(prev, next, args.windowCandles);
        if (merged.length > 0) args.setLiveLoadState("ready");
        return merged;
      });
    },
    onCandleClosed: (msg) => {
      const time = msg.candle.candle_time;
      args.lastWsCandleTimeRef.current = time;
      args.setLastWsCandleTime(time);

      const next = toChartCandle(msg.candle);
      args.candlesRef.current = mergeCandleWindow(args.candlesRef.current, next, args.windowCandles);
      args.setCandles((prev) => {
        const merged = mergeCandleWindow(prev, next, args.windowCandles);
        if (merged.length > 0) args.setLiveLoadState("ready");
        return merged;
      });
      logDebugEvent({
        pipe: "read",
        event: "read.ws.market_candle_closed",
        series_id: args.seriesId,
        level: "info",
        message: "ws candle_closed",
        data: { candle_time: time }
      });
      schedule(time);
    },
    onGap: (msg) => {
      logDebugEvent({
        pipe: "read",
        event: "read.ws.market_gap",
        series_id: args.seriesId,
        level: "warn",
        message: "ws gap",
        data: {
          expected_next_time: msg.expected_next_time ?? null,
          actual_time: msg.actual_time ?? null
        }
      });
      const tfSeconds = timeframeToSeconds(args.timeframe);
      const expectedNextTime =
        typeof msg.expected_next_time === "number" && Number.isFinite(msg.expected_next_time)
          ? Math.max(0, Math.trunc(msg.expected_next_time))
          : null;
      const tfStep = tfSeconds != null ? Math.max(1, tfSeconds) : 60;
      const gapSince = expectedNextTime != null ? Math.max(0, expectedNextTime - tfStep) : null;
      const last = args.candlesRef.current[args.candlesRef.current.length - 1];
      const fallbackSince = last != null ? (last.time as number) : null;
      const since = gapSince ?? fallbackSince;
      const fetchParams =
        since != null
          ? ({ seriesId: args.seriesId, since, limit: 5000 } as const)
          : ({ seriesId: args.seriesId, limit: args.windowCandles } as const);

      void fetchCandles(fetchParams).then(({ candles: chunk }) => {
        if (!args.isActive()) return;
        if (chunk.length === 0) return;
        args.setCandles((prev) => {
          const next = mergeCandlesWindow(prev, chunk, args.windowCandles);
          args.candlesRef.current = next;
          if (next.length > 0) args.setLiveLoadState("ready");
          return next;
        });
      });

      args.overlayCatalogRef.current.clear();
      args.overlayActiveIdsRef.current.clear();
      args.overlayCursorVersionRef.current = 0;
      args.anchorPenPointsRef.current = null;
      args.replayPenPreviewPointsRef.current["pen.extending"] = [];
      args.replayPenPreviewPointsRef.current["pen.candidate"] = [];
      args.factorPullPendingTimeRef.current = null;
      args.setAnchorHighlightEpoch((value) => value + 1);
      args.lastFactorAtTimeRef.current = null;
      if (args.enableWorldFrame && !args.replayEnabled && args.worldFrameHealthyRef.current) {
        void loadWorldFrameLiveWithRetry(args)
          .then((frame) => {
            if (!args.isActive()) return;
            if (!frame) {
              args.worldFrameHealthyRef.current = false;
              return;
            }
            args.applyWorldFrame(frame);
          })
          .catch(() => {
            args.worldFrameHealthyRef.current = false;
          });
      } else {
        void args.fetchOverlayLikeDelta({
          seriesId: args.seriesId,
          cursorVersionId: 0,
          windowCandles: args.windowCandles
        })
          .then((delta) => {
            if (!args.isActive()) return;
            args.applyOverlayDelta(delta);
            args.rebuildPivotMarkersFromOverlay();
            args.rebuildAnchorSwitchMarkersFromOverlay();
            args.syncMarkers();
            args.rebuildPenPointsFromOverlay();
            if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
              args.penSeriesRef.current.setData(args.penPointsRef.current);
            }
            args.setPenPointCount(computePenPointCount(args));
          })
          .catch(() => {
            // ignore
          });
        if (last && last.time != null) {
          void args.fetchAndApplyAnchorHighlightAtTime(last.time as number);
        }
      }
    },
    onSocketError: () => {
      if (!args.isActive()) return;
      args.setError("WS error");
      args.setLiveLoadState("error", "WS error");
    }
  };
}
