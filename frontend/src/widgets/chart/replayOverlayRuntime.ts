import type { MutableRefObject } from "react";

import type { ISeriesApi } from "lightweight-charts";

import type {
  OverlayInstructionPatchItemV1,
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

export type ReplayOverlayRuntimeArgs = ReplayRenderSyncArgs & {
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
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

export function applyReplayPackageWindowRuntime(args: ReplayOverlayRuntimeArgs & {
  bundle: {
    window: ReplayWindowV1;
  };
  targetIdx: number;
  replayWindowIndexRef: MutableRefObject<number | null>;
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
