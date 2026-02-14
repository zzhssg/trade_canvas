import type { UTCTimestamp } from "lightweight-charts";
import { useCallback, useRef, type MutableRefObject } from "react";
import {
  applyReplayOverlayAtTimeRuntime,
  applyReplayPackageWindowRuntime,
  requestReplayFrameAtTimeRuntime,
  type ReplayOverlayRuntimeArgs
} from "./replayOverlayRuntime";
import { timeframeToSeconds } from "./timeframe";
import type { Candle, OverlayInstructionPatchItemV1, ReplayFactorHeadSnapshotV1, ReplayHistoryDeltaV1, ReplayKlineBarV1, ReplayWindowV1 } from "./types";

export function toReplayCandle(bar: ReplayKlineBarV1): Candle {
  return { time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close };
}

type ReplayWindowBundleLike = {
  window: ReplayWindowV1;
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

type UseReplayOverlayRuntimeArgs = ReplayOverlayRuntimeArgs & {
  timeframe: string;
  windowCandles: number;
  replayPatchRef: MutableRefObject<OverlayInstructionPatchItemV1[]>;
  replayPatchAppliedIdxRef: MutableRefObject<number>;
  replayWindowIndexRef: MutableRefObject<number | null>;
};

export function useReplayOverlayRuntime(args: UseReplayOverlayRuntimeArgs) {
  const latestArgsRef = useRef(args);
  latestArgsRef.current = args;

  const applyReplayOverlayAtTime = useCallback(
    (toTime: number) => {
      const current = latestArgsRef.current;
      const runtimeArgs: ReplayOverlayRuntimeArgs = current;
      return applyReplayOverlayAtTimeRuntime({
        ...runtimeArgs,
        toTime,
        timeframeSeconds: timeframeToSeconds(current.timeframe),
        windowCandles: current.windowCandles,
        replayPatchRef: current.replayPatchRef,
        replayPatchAppliedIdxRef: current.replayPatchAppliedIdxRef
      });
    },
    []
  );

  const applyReplayPackageWindow = useCallback(
    (bundle: ReplayWindowBundleLike, targetIdx: number) => {
      const current = latestArgsRef.current;
      const runtimeArgs: ReplayOverlayRuntimeArgs = current;
      return applyReplayPackageWindowRuntime({
        ...runtimeArgs,
        bundle,
        targetIdx,
        replayWindowIndexRef: current.replayWindowIndexRef
      });
    },
    []
  );

  return { applyReplayOverlayAtTime, applyReplayPackageWindow };
}

type UseReplayFrameRequestArgs = {
  replayEnabled: boolean;
  seriesId: string;
  windowCandles: number;
  replayFrameLatestTimeRef: MutableRefObject<number | null>;
  replayFramePendingTimeRef: MutableRefObject<number | null>;
  replayFramePullInFlightRef: MutableRefObject<boolean>;
  setReplayFrameLoading: (loading: boolean) => void;
  setReplayFrameError: (error: string | null) => void;
  setReplayFrame: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["setReplayFrame"];
  applyPenAndAnchorFromFactorSlices: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["applyPenAndAnchorFromFactorSlices"];
  setReplaySlices: Parameters<typeof requestReplayFrameAtTimeRuntime>[0]["setReplaySlices"];
  setReplayCandle: (value: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
};

export function useReplayFrameRequest(args: UseReplayFrameRequestArgs) {
  return useCallback(
    async (atTime: number) =>
      requestReplayFrameAtTimeRuntime({
        ...args,
        atTime
      }),
    [args.applyPenAndAnchorFromFactorSlices, args.replayEnabled, args.seriesId, args.setReplayCandle, args.setReplayDrawInstructions, args.setReplayFrame, args.setReplayFrameError, args.setReplayFrameLoading, args.setReplaySlices, args.windowCandles]
  );
}
