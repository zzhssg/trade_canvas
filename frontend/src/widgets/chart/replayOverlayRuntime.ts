import type { MutableRefObject } from "react";

import type { ISeriesApi } from "lightweight-charts";

import { fetchWorldFrameAtTime } from "./api";
import type {
  OverlayInstructionPatchItemV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayWindowV1
} from "./types";
import type { PenLinePoint, PenSegment } from "./penAnchorRuntime";

export function resolveReplayActiveIds(window: ReplayWindowV1, targetIdx: number): string[] {
  const checkpoints = window.draw_active_checkpoints ?? [];
  const diffs = window.draw_active_diffs ?? [];
  let base: string[] = [];
  let baseIdx = window.start_idx;

  for (const checkpoint of checkpoints) {
    if (checkpoint.at_idx > targetIdx) break;
    base = Array.isArray(checkpoint.active_ids) ? checkpoint.active_ids.slice() : [];
    baseIdx = checkpoint.at_idx;
  }

  const active = new Set(base);
  for (const diff of diffs) {
    if (diff.at_idx <= baseIdx) continue;
    if (diff.at_idx > targetIdx) break;
    for (const id of diff.add_ids ?? []) active.add(id);
    for (const id of diff.remove_ids ?? []) active.delete(id);
  }

  return Array.from(active).sort();
}

type ReplayRenderSyncArgs = {
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  syncMarkers: () => void;
  effectiveVisible: (key: string) => boolean;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  enablePenSegmentColor: boolean;
  replayEnabled: boolean;
  setPenPointCount: (value: number) => void;
};

function syncReplayDrawState(args: ReplayRenderSyncArgs) {
  args.rebuildPivotMarkersFromOverlay();
  args.rebuildAnchorSwitchMarkersFromOverlay();
  args.rebuildPenPointsFromOverlay();
  args.rebuildOverlayPolylinesFromOverlay();
  if (args.effectiveVisible("pen.confirmed") && args.penSeriesRef.current) {
    args.penSeriesRef.current.setData(args.penPointsRef.current);
  }
  const pointCount =
    args.enablePenSegmentColor && !args.replayEnabled
      ? args.penSegmentsRef.current.length * 2
      : args.penPointsRef.current.length;
  args.setPenPointCount(pointCount);
  args.syncMarkers();
}

export function applyReplayOverlayAtTimeRuntime(args: {
  toTime: number;
  timeframeSeconds: number | null;
  windowCandles: number;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  recomputeActiveIdsFromCatalog: (params: { cutoffTime: number; toTime: number }) => string[];
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  syncMarkers: () => void;
  effectiveVisible: (key: string) => boolean;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  enablePenSegmentColor: boolean;
  replayEnabled: boolean;
  setPenPointCount: (value: number) => void;
}) {
  const patch = args.replayPatchRef.current;
  if (patch.length === 0) return;

  const lastApplied = args.replayPatchAppliedIdxRef.current > 0
    ? patch[args.replayPatchAppliedIdxRef.current - 1]
    : null;
  if (lastApplied && lastApplied.visible_time > args.toTime) {
    args.overlayCatalogRef.current.clear();
    args.replayPatchAppliedIdxRef.current = 0;
  }

  let index = args.replayPatchAppliedIdxRef.current;
  for (; index < patch.length; index += 1) {
    const item = patch[index]!;
    if (item.visible_time > args.toTime) break;
    args.overlayCatalogRef.current.set(item.instruction_id, item);
  }
  args.replayPatchAppliedIdxRef.current = index;

  const cutoffTime = args.timeframeSeconds
    ? Math.max(0, Math.floor(args.toTime - args.windowCandles * args.timeframeSeconds))
    : 0;
  args.overlayActiveIdsRef.current = new Set(args.recomputeActiveIdsFromCatalog({ cutoffTime, toTime: args.toTime }));
  const activeInstructions = Array.from(args.overlayActiveIdsRef.current)
    .map((id) => args.overlayCatalogRef.current.get(id))
    .filter(Boolean) as OverlayInstructionPatchItemV1[];
  args.setReplayDrawInstructions(activeInstructions);

  syncReplayDrawState(args);
}

export function applyReplayPackageWindowRuntime(args: {
  bundle: {
    window: ReplayWindowV1;
    headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
    historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
  };
  targetIdx: number;
  replayWindowIndexRef: MutableRefObject<number | null>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  rebuildPivotMarkersFromOverlay: () => void;
  rebuildAnchorSwitchMarkersFromOverlay: () => void;
  rebuildPenPointsFromOverlay: () => void;
  rebuildOverlayPolylinesFromOverlay: () => void;
  syncMarkers: () => void;
  effectiveVisible: (key: string) => boolean;
  penSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  penPointsRef: MutableRefObject<PenLinePoint[]>;
  penSegmentsRef: MutableRefObject<PenSegment[]>;
  enablePenSegmentColor: boolean;
  replayEnabled: boolean;
  setPenPointCount: (value: number) => void;
}): string[] {
  const window = args.bundle.window;
  if (args.replayWindowIndexRef.current !== window.window_index) {
    args.overlayCatalogRef.current.clear();
    const catalog = [...(window.draw_catalog_base ?? []), ...(window.draw_catalog_patch ?? [])];
    catalog.sort((a, b) => (a.version_id - b.version_id !== 0 ? a.version_id - b.version_id : a.visible_time - b.visible_time));
    for (const item of catalog) {
      args.overlayCatalogRef.current.set(item.instruction_id, item);
    }
    args.replayWindowIndexRef.current = window.window_index;
  }

  const activeIds = resolveReplayActiveIds(window, args.targetIdx);
  args.overlayActiveIdsRef.current = new Set(activeIds);
  const activeInstructions = activeIds
    .map((id) => args.overlayCatalogRef.current.get(id))
    .filter(Boolean) as OverlayInstructionPatchItemV1[];
  args.setReplayDrawInstructions(activeInstructions);

  syncReplayDrawState(args);
  return activeIds;
}

export async function requestReplayFrameAtTimeRuntime(args: {
  atTime: number;
  replayEnabled: boolean;
  replayFrameLatestTimeRef: MutableRefObject<number | null>;
  replayFramePendingTimeRef: MutableRefObject<number | null>;
  replayFramePullInFlightRef: MutableRefObject<boolean>;
  seriesId: string;
  windowCandles: number;
  setReplayFrameLoading: (loading: boolean) => void;
  setReplayFrameError: (error: string | null) => void;
  setReplayFrame: (frame: any) => void;
  applyPenAndAnchorFromFactorSlices: (slices: any) => void;
  setReplaySlices: (slices: any) => void;
  setReplayCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
}) {
  const aligned = Math.max(0, Math.floor(args.atTime));
  if (!args.replayEnabled || aligned <= 0) return;
  if (args.replayFrameLatestTimeRef.current === aligned) return;
  args.replayFramePendingTimeRef.current = aligned;
  if (args.replayFramePullInFlightRef.current) return;

  args.replayFramePullInFlightRef.current = true;
  args.setReplayFrameLoading(true);
  args.setReplayFrameError(null);
  try {
    while (args.replayFramePendingTimeRef.current != null) {
      const next = args.replayFramePendingTimeRef.current;
      args.replayFramePendingTimeRef.current = null;
      const frame = await fetchWorldFrameAtTime({
        seriesId: args.seriesId,
        atTime: next,
        windowCandles: args.windowCandles
      });
      if (!args.replayEnabled) break;
      args.replayFrameLatestTimeRef.current = next;
      args.setReplayFrame(frame);
      args.applyPenAndAnchorFromFactorSlices(frame.factor_slices);
      args.setReplaySlices(frame.factor_slices);
      args.setReplayCandle({
        candleId: frame.time.candle_id,
        atTime: frame.time.aligned_time,
        activeIds: frame.draw_state?.active_ids ?? []
      });
      const patch = Array.isArray(frame.draw_state?.instruction_catalog_patch)
        ? frame.draw_state.instruction_catalog_patch
        : [];
      args.setReplayDrawInstructions(patch);
    }
  } catch (error: unknown) {
    if (!args.replayEnabled) return;
    args.setReplayFrameError(error instanceof Error ? error.message : "Failed to load replay frame");
  } finally {
    if (args.replayEnabled) args.setReplayFrameLoading(false);
    args.replayFramePullInFlightRef.current = false;
  }
}
