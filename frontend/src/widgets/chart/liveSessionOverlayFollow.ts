import { pollWorldDelta, fetchWorldFrameLive } from "./api";
import type { OverlayLikeDeltaV1, WorldStateV1 } from "./types";
import type { StartChartLiveSessionOptions } from "./liveSessionRuntimeTypes";

export function computePenPointCount(args: StartChartLiveSessionOptions): number {
  return args.enablePenSegmentColor ? args.penSegmentsRef.current.length * 2 : args.penPointsRef.current.length;
}

function parseHttpStatus(error: unknown): number | null {
  if (!(error instanceof Error)) return null;
  const [prefix] = String(error.message).split(":", 1);
  if (!prefix?.startsWith("HTTP ")) return null;
  const status = Number(prefix.slice(5));
  if (!Number.isFinite(status)) return null;
  return status;
}

export async function loadWorldFrameLiveWithRetry(args: StartChartLiveSessionOptions): Promise<WorldStateV1 | null> {
  const retryLimit = 6;
  const retryDelayMs = 200;
  let lastError: unknown = null;
  for (let attempt = 0; attempt <= retryLimit; attempt += 1) {
    try {
      return await fetchWorldFrameLive({ seriesId: args.seriesId, windowCandles: args.windowCandles });
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : "";
      const status = message.startsWith("HTTP ") ? Number(message.replace("HTTP ", "")) : null;
      if (status !== 409) throw error;
      await new Promise((resolve) => window.setTimeout(resolve, retryDelayMs));
    }
  }
  if (lastError) throw lastError;
  return null;
}

export async function applyOverlayBaseline(args: StartChartLiveSessionOptions, cursor: number) {
  const delta = await args.fetchOverlayLikeDelta({
    seriesId: args.seriesId,
    cursorVersionId: 0,
    windowCandles: args.windowCandles
  });
  if (!args.isActive()) return;
  args.applyOverlayDelta(delta);
  args.rebuildPivotMarkersFromOverlay();
  args.syncMarkers();
  args.rebuildPenPointsFromOverlay();
  args.setPenPointCount(computePenPointCount(args));
  if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
    args.penSeriesRef.current.setData(args.penPointsRef.current);
  }
  if (cursor > 0) {
    void args.fetchAndApplyAnchorHighlightAtTime(cursor);
  }
}

export function scheduleOverlayFollow(
  args: StartChartLiveSessionOptions,
  runOverlayFollowNow: (time: number) => void,
  time: number
) {
  if (!args.isActive()) return;
  args.followPendingTimeRef.current = Math.max(args.followPendingTimeRef.current ?? 0, time);
  if (args.overlayPullInFlightRef.current) return;
  if (args.followTimerIdRef.current != null) return;
  args.followTimerIdRef.current = window.setTimeout(() => {
    args.followTimerIdRef.current = null;
    const next = args.followPendingTimeRef.current;
    args.followPendingTimeRef.current = null;
    if (next == null || !args.isActive()) return;
    runOverlayFollowNow(next);
  }, 1000);
}

export function runOverlayFollowNow(
  args: StartChartLiveSessionOptions,
  time: number,
  schedule: (time: number) => void
) {
  if (!args.isActive()) return;
  if (args.overlayPullInFlightRef.current) {
    args.followPendingTimeRef.current = Math.max(args.followPendingTimeRef.current ?? 0, time);
    return;
  }
  args.overlayPullInFlightRef.current = true;

  if (args.enableWorldFrame && !args.replayEnabled && args.worldFrameHealthyRef.current) {
    const afterId = args.overlayCursorVersionRef.current;
    void pollWorldDelta({ seriesId: args.seriesId, afterId, windowCandles: args.windowCandles })
      .then((response) => {
        if (!args.isActive()) return;
        const record = response.records?.[0];
        if (record?.draw_delta) {
          args.applyOverlayDelta({
            active_ids: record.draw_delta.active_ids ?? [],
            instruction_catalog_patch: record.draw_delta.instruction_catalog_patch ?? [],
            next_cursor: { version_id: record.draw_delta.next_cursor?.version_id ?? afterId }
          });
          args.rebuildPivotMarkersFromOverlay();
          args.rebuildAnchorSwitchMarkersFromOverlay();
          args.rebuildOverlayPolylinesFromOverlay();
          args.syncMarkers();
          args.rebuildPenPointsFromOverlay();
          args.setPenPointCount(computePenPointCount(args));
          if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
            args.penSeriesRef.current.setData(args.penPointsRef.current);
          }
        }
        if (record?.factor_slices) {
          args.applyPenAndAnchorFromFactorSlices(record.factor_slices);
        } else {
          void args.fetchAndApplyAnchorHighlightAtTime(time);
        }
      })
      .catch((error: unknown) => {
        if (parseHttpStatus(error) === 409) return;
        args.worldFrameHealthyRef.current = false;
      })
      .finally(() => {
        args.overlayPullInFlightRef.current = false;
        const pending = args.followPendingTimeRef.current;
        args.followPendingTimeRef.current = null;
        if (pending != null && args.isActive()) {
          schedule(pending);
          return;
        }
        if (args.isActive() && time > 0 && args.lastFactorAtTimeRef.current !== time) {
          schedule(time);
        }
      });
    return;
  }

  const cursorVersionId = args.overlayCursorVersionRef.current;
  void args.fetchOverlayLikeDelta({ seriesId: args.seriesId, cursorVersionId, windowCandles: args.windowCandles })
    .then((delta: OverlayLikeDeltaV1) => {
      if (!args.isActive()) return;
      args.applyOverlayDelta(delta);
      args.rebuildPivotMarkersFromOverlay();
      args.rebuildAnchorSwitchMarkersFromOverlay();
      args.rebuildOverlayPolylinesFromOverlay();
      args.syncMarkers();
      args.rebuildPenPointsFromOverlay();
      if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
        args.penSeriesRef.current.setData(args.penPointsRef.current);
      }
      args.setPenPointCount(computePenPointCount(args));
    })
    .catch(() => {
      // ignore
    })
    .finally(() => {
      args.overlayPullInFlightRef.current = false;
      const pending = args.followPendingTimeRef.current;
      args.followPendingTimeRef.current = null;
      if (pending != null && args.isActive()) {
        schedule(pending);
        return;
      }
      if (args.isActive() && time > 0 && args.lastFactorAtTimeRef.current !== time) {
        schedule(time);
      }
    });

  void args.fetchAndApplyAnchorHighlightAtTime(time);
}
