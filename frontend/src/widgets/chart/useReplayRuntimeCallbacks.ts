import type { UTCTimestamp } from "lightweight-charts";
import { useCallback, useRef, type MutableRefObject } from "react";
import {
  applyReplayPackageWindowRuntime,
  type ReplayOverlayRuntimeArgs
} from "./replayOverlayRuntime";
import type { Candle, ReplayKlineBarV1, ReplayWindowV1 } from "./types";

export function toReplayCandle(bar: ReplayKlineBarV1): Candle {
  return { time: bar.time as UTCTimestamp, open: bar.open, high: bar.high, low: bar.low, close: bar.close };
}

type ReplayWindowBundleLike = {
  window: ReplayWindowV1;
};

type UseReplayOverlayRuntimeArgs = ReplayOverlayRuntimeArgs & {
  replayWindowIndexRef: MutableRefObject<number | null>;
};

export function useReplayOverlayRuntime(args: UseReplayOverlayRuntimeArgs) {
  const latestArgsRef = useRef(args);
  latestArgsRef.current = args;

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

  return { applyReplayPackageWindow };
}
