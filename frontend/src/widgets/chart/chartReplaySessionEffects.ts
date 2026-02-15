import { useEffect, useRef } from "react";

import { startChartLiveSession } from "./liveSessionRuntime";
import type { StartChartLiveSessionArgs } from "./liveSessionRuntimeTypes";
import { resetReplayPackageState, syncReplayFocusFromIndex } from "./replayRuntimeHelpers";

type UseChartLiveSessionEffectArgs = StartChartLiveSessionArgs & {
  replayPackageEnabled: boolean;
  replayPrepareStatus: string;
};

export function useChartLiveSessionEffect(args: UseChartLiveSessionEffectArgs) {
  useEffect(() => {
    if (args.replayPackageEnabled) return;
    if (args.replayEnabled && args.replayPrepareStatus !== "ready") return;
    const session = startChartLiveSession(args);
    return () => session.stop();
  }, [
    args.applyOverlayDelta,
    args.applyPenAndAnchorFromFactorSlices,
    args.applyWorldFrame,
    args.effectiveVisible,
    args.fetchAndApplyAnchorHighlightAtTime,
    args.fetchOverlayLikeDelta,
    args.openMarketWs,
    args.rebuildOverlayPolylinesFromOverlay,
    args.rebuildPenPointsFromOverlay,
    args.rebuildPivotMarkersFromOverlay,
    args.rebuildAnchorSwitchMarkersFromOverlay,
    args.replayEnabled,
    args.replayPackageEnabled,
    args.replayPrepareStatus,
    args.replayPreparedAlignedTime,
    args.seriesId,
    args.setLiveLoadState,
    args.showToast,
    args.syncMarkers,
    args.timeframe
  ]);
}

type UseReplayPackageResetEffectArgs = Parameters<typeof resetReplayPackageState>[0] & {
  replayPackageEnabled: boolean;
  seriesId: string;
};

export function useReplayPackageResetEffect(args: UseReplayPackageResetEffectArgs) {
  useEffect(() => {
    if (!args.replayPackageEnabled) return;
    resetReplayPackageState(args);
  }, [
    args.replayPackageEnabled,
    args.seriesId,
    args.setReplayCandle,
    args.setReplayDrawInstructions,
    args.setReplayFocusTime,
    args.setReplayIndex,
    args.setReplayPlaying,
    args.setReplaySlices,
    args.setReplayTotal
  ]);
}

export function useReplayFocusSyncEffect(args: Parameters<typeof syncReplayFocusFromIndex>[0]) {
  const latestArgsRef = useRef(args);
  latestArgsRef.current = args;

  useEffect(() => {
    syncReplayFocusFromIndex(latestArgsRef.current);
  }, [
    args.replayEnabled,
    args.replayIndex,
    args.replayPackageEnabled,
    args.replayTotal
  ]);
}
