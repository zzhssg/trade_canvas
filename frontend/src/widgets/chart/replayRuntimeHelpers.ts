import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { Candle, OverlayInstructionPatchItemV1 } from "./types";

type ReplayPenPreviewPointsRef = MutableRefObject<Record<"pen.extending" | "pen.candidate", Array<{ time: unknown; value: number }>>>;

type ResetReplayPackageStateArgs = {
  setCandles: Dispatch<SetStateAction<Candle[]>>;
  candlesRef: MutableRefObject<Candle[]>;
  replayAllCandlesRef: MutableRefObject<Array<Candle | null>>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  pivotMarkersRef: MutableRefObject<Array<{ time: unknown }>>;
  overlayCatalogRef: MutableRefObject<Map<string, OverlayInstructionPatchItemV1>>;
  overlayActiveIdsRef: MutableRefObject<Set<string>>;
  overlayCursorVersionRef: MutableRefObject<number>;
  overlayPullInFlightRef: MutableRefObject<boolean>;
  penSegmentsRef: MutableRefObject<Array<{ key: string }>>;
  anchorPenPointsRef: MutableRefObject<Array<{ time: unknown; value: number }> | null>;
  replayPenPreviewPointsRef: ReplayPenPreviewPointsRef;
  factorPullPendingTimeRef: MutableRefObject<number | null>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  setAnchorHighlightEpoch: Dispatch<SetStateAction<number>>;
  setPivotCount: (value: number) => void;
  setPenPointCount: (value: number) => void;
  setError: (value: string | null) => void;
  setReplayIndex: (value: number) => void;
  setReplayPlaying: (value: boolean) => void;
  setReplayTotal: (value: number) => void;
  setReplayFocusTime: (value: number | null) => void;
  setReplayFrame: (value: any) => void;
  setReplaySlices: (value: any) => void;
  setReplayCandle: (value: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (value: OverlayInstructionPatchItemV1[]) => void;
};

export function resetReplayPackageState(args: ResetReplayPackageStateArgs) {
  args.setCandles([]);
  args.candlesRef.current = [];
  args.replayAllCandlesRef.current = [];
  args.replayWindowIndexRef.current = null;
  args.pivotMarkersRef.current = [];
  args.overlayCatalogRef.current.clear();
  args.overlayActiveIdsRef.current.clear();
  args.overlayCursorVersionRef.current = 0;
  args.overlayPullInFlightRef.current = false;
  args.penSegmentsRef.current = [];
  args.anchorPenPointsRef.current = null;
  args.replayPenPreviewPointsRef.current["pen.extending"] = [];
  args.replayPenPreviewPointsRef.current["pen.candidate"] = [];
  args.factorPullPendingTimeRef.current = null;
  args.lastFactorAtTimeRef.current = null;
  args.setAnchorHighlightEpoch((value) => value + 1);
  args.setPivotCount(0);
  args.setPenPointCount(0);
  args.setError(null);
  args.replayPatchRef.current = [];
  args.replayPatchAppliedIdxRef.current = 0;
  args.setReplayIndex(0);
  args.setReplayPlaying(false);
  args.setReplayTotal(0);
  args.setReplayFocusTime(null);
  args.setReplayFrame(null);
  args.setReplaySlices(null);
  args.setReplayCandle({ candleId: null, atTime: null, activeIds: [] });
  args.setReplayDrawInstructions([]);
}

type SyncReplayFocusArgs = {
  replayEnabled: boolean;
  replayPackageEnabled: boolean;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  replayAllCandlesRef: MutableRefObject<Array<Candle | null>>;
  setReplayIndex: (value: number) => void;
  setReplayFocusTime: (value: number | null) => void;
  applyReplayOverlayAtTime: (time: number) => void;
  fetchAndApplyAnchorHighlightAtTime: (time: number) => Promise<void>;
  requestReplayFrameAtTime: (time: number) => Promise<void>;
};

export function syncReplayFocusFromIndex(args: SyncReplayFocusArgs) {
  if (!args.replayEnabled) return;
  if (args.replayPackageEnabled) return;
  const all = args.replayAllCandlesRef.current as Candle[];
  if (all.length === 0) return;

  const clamped = Math.max(0, Math.min(args.replayIndex, args.replayTotal - 1));
  if (clamped !== args.replayIndex) {
    args.setReplayIndex(clamped);
    return;
  }

  const time = all[clamped]!.time as number;
  if (args.replayFocusTime === time) {
    return;
  }
  args.setReplayFocusTime(time);
  args.applyReplayOverlayAtTime(time);
  void args.fetchAndApplyAnchorHighlightAtTime(time);
  void args.requestReplayFrameAtTime(time);
}
