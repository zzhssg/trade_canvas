import type { ISeriesApi, SeriesMarker, Time } from "lightweight-charts";
import { useCallback, type MutableRefObject } from "react";
import type { ReplayWindowBundle } from "../../state/replayStore";
import { buildReplayFactorSlices } from "./replayFactorSlices";
import {
  useChartLiveSessionEffect,
  useChartSeriesSyncEffects,
  useReplayFocusSyncEffect,
  useReplayPackageResetEffect
} from "./useChartSessionEffects";
import { useReplayPackageWindowSync } from "./useReplayPackageWindowSync";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  ReplayHistoryEventV1,
  ReplayKlineBarV1,
  ReplayPackageMetadataV1,
  WorldStateV1
} from "./types";
import type { StartChartLiveSessionArgs } from "./liveSessionRuntimeTypes";

type ReplayOverlayBundle = {
  window: ReplayWindowBundle["window"];
  headByTime: ReplayWindowBundle["headByTime"];
  historyDeltaByIdx: ReplayWindowBundle["historyDeltaByIdx"];
};
export type UseChartRuntimeEffectsArgs = StartChartLiveSessionArgs & {
  replayPrepareStatus: string;
  replayPackageEnabled: boolean;
  replayPackageStatus: string;
  replayPackageMeta: ReplayPackageMetadataV1 | null;
  replayPackageHistory: ReplayHistoryEventV1[];
  replayPackageWindows: Record<number, ReplayWindowBundle>;
  replayEnsureWindowRange: (startIdx: number, endIdx: number) => Promise<void>;
  replayIndex: number;
  replayTotal: number;
  replayFocusTime: number | null;
  candles: Candle[];
  visibleFeatures: Record<string, boolean | undefined>;
  chartEpoch: number;
  anchorHighlightEpoch: number;
  enableAnchorTopLayer: boolean;
  lineSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  entryEnabledRef: MutableRefObject<boolean>;
  entryMarkersRef: MutableRefObject<Array<SeriesMarker<Time>>>;
  penSegmentSeriesByKeyRef: MutableRefObject<Map<string, ISeriesApi<"Line">>>;
  anchorPenSeriesRef: MutableRefObject<ISeriesApi<"Line"> | null>;
  anchorPenIsDashedRef: MutableRefObject<boolean>;
  replayWindowIndexRef: MutableRefObject<number | null>;
  applyReplayOverlayAtTime: (toTime: number) => void;
  applyReplayPackageWindow: (bundle: ReplayOverlayBundle, targetIdx: number) => string[];
  requestReplayFrameAtTime: (atTime: number) => Promise<void>;
  toReplayCandle: (bar: ReplayKlineBarV1) => Candle;
  setReplayFocusTime: (value: number | null) => void;
  setReplayFrame: (frame: WorldStateV1 | null) => void;
  setReplaySlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setReplayCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setReplayDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  setReplayFrameLoading: (value: boolean) => void;
  setReplayFrameError: (value: string | null) => void;
};

export function useChartRuntimeEffects(args: UseChartRuntimeEffectsArgs) {
  useChartSeriesSyncEffects(args);
  useChartLiveSessionEffect(args);
  useReplayPackageResetEffect(args);

  useReplayPackageWindowSync({
    enabled: args.replayPackageEnabled,
    status: args.replayPackageStatus,
    metadata: args.replayPackageMeta,
    windows: args.replayPackageWindows,
    historyEvents: args.replayPackageHistory,
    ensureWindowRange: args.replayEnsureWindowRange,
    replayIndex: args.replayIndex,
    replayFocusTime: args.replayFocusTime,
    seriesId: args.seriesId,
    replayAllCandlesRef: args.replayAllCandlesRef,
    lastFactorAtTimeRef: args.lastFactorAtTimeRef,
    candlesRef: args.candlesRef,
    toReplayCandle: args.toReplayCandle,
    applyReplayPackageWindow: args.applyReplayPackageWindow,
    buildReplayFactorSlices: useCallback(
      (runtimeArgs) => buildReplayFactorSlices({ ...runtimeArgs, seriesId: args.seriesId }),
      [args.seriesId]
    ),
    applyPenAndAnchorFromFactorSlices: args.applyPenAndAnchorFromFactorSlices,
    setReplayTotal: args.setReplayTotal,
    setReplayIndex: args.setReplayIndex,
    setReplayFocusTime: args.setReplayFocusTime,
    setReplaySlices: args.setReplaySlices,
    setReplayCandle: args.setReplayCandle,
    setCandles: args.setCandles
  });

  useReplayFocusSyncEffect(args);
}
