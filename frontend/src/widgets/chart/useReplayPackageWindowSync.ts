import { useEffect } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";
import type { ReplayWindowBundle } from "../../state/replayStore";
import type {
  Candle,
  GetFactorSlicesResponseV1,
  ReplayFactorSchemaV1,
  ReplayFactorSnapshotV1,
  ReplayKlineBarV1,
  ReplayPackageMetadataV1
} from "./types";

type BuildReplayFactorSlices = (args: {
  atTime: number;
  factorSchema: ReplayFactorSchemaV1[];
  factorSnapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>;
}) => GetFactorSlicesResponseV1;
type ApplyReplayPackageWindow = (bundle: ReplayWindowBundle, targetIdx: number) => string[];

type UseReplayPackageWindowSyncArgs = {
  enabled: boolean;
  status: string;
  metadata: ReplayPackageMetadataV1 | null;
  windows: Record<number, ReplayWindowBundle>;
  ensureWindowRange: (startIdx: number, endIdx: number) => Promise<void>;
  replayIndex: number;
  replayFocusTime: number | null;
  seriesId: string;
  replayAllCandlesRef: MutableRefObject<Array<Candle | null>>;
  lastFactorAtTimeRef: MutableRefObject<number | null>;
  candlesRef: MutableRefObject<Candle[]>;
  toReplayCandle: (bar: ReplayKlineBarV1) => Candle;
  applyReplayPackageWindow: ApplyReplayPackageWindow;
  buildReplayFactorSlices: BuildReplayFactorSlices;
  applyPenAndAnchorFromFactorSlices: (slices: GetFactorSlicesResponseV1) => void;
  setReplayTotal: (total: number) => void;
  setReplayIndex: (index: number) => void;
  setReplayFocusTime: (time: number | null) => void;
  setReplaySlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setReplayCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setCandles: Dispatch<SetStateAction<Candle[]>>;
};

export function useReplayPackageWindowSync({
  enabled,
  status,
  metadata,
  windows,
  ensureWindowRange,
  replayIndex,
  replayFocusTime,
  seriesId,
  replayAllCandlesRef,
  lastFactorAtTimeRef,
  candlesRef,
  toReplayCandle,
  applyReplayPackageWindow,
  buildReplayFactorSlices,
  applyPenAndAnchorFromFactorSlices,
  setReplayTotal,
  setReplayIndex,
  setReplayFocusTime,
  setReplaySlices,
  setReplayCandle,
  setCandles
}: UseReplayPackageWindowSyncArgs) {
  useEffect(() => {
    if (!enabled || status !== "ready" || !metadata || metadata.total_candles <= 0) return;
    const meta = metadata;
    const total = meta.total_candles;
    setReplayTotal(total);
    const desiredIndex = replayFocusTime == null ? total - 1 : replayIndex;
    const clamped = Math.max(0, Math.min(desiredIndex, total - 1));
    if (clamped !== replayIndex) {
      setReplayIndex(clamped);
      return;
    }

    let cancelled = false;

    async function run() {
      await ensureWindowRange(0, total - 1);
      if (cancelled) return;

      if (replayAllCandlesRef.current.length !== total) {
        replayAllCandlesRef.current = Array.from({ length: total }, () => null);
      }
      for (const bundle of Object.values(windows)) {
        const startIdx = bundle.window.start_idx;
        const kline = bundle.window.kline ?? [];
        kline.forEach((bar, i) => {
          replayAllCandlesRef.current[startIdx + i] = toReplayCandle(bar);
        });
      }

      const filled = replayAllCandlesRef.current.filter(Boolean) as Candle[];
      const synced = filled.length === total ? (replayAllCandlesRef.current as Candle[]) : filled;
      if (synced.length > 0) {
        candlesRef.current = synced;
        setCandles(synced);
      }

      const windowIndex = Math.floor(clamped / meta.window_size);
      const bundle = windows[windowIndex];
      if (!bundle) return;

      const activeIds = applyReplayPackageWindow(bundle, clamped);
      const candle = replayAllCandlesRef.current[clamped];
      if (!candle) return;
      const toTime = candle.time as number;
      setReplayFocusTime(toTime);
      const slices = buildReplayFactorSlices({
        atTime: toTime,
        factorSchema: meta.factor_schema ?? [],
        factorSnapshotByTime: bundle.factorSnapshotByTime
      });
      lastFactorAtTimeRef.current = toTime;
      applyPenAndAnchorFromFactorSlices(slices);
      setReplaySlices(slices);
      setReplayCandle({ candleId: slices.candle_id ?? `${seriesId}:${toTime}`, atTime: toTime, activeIds });
    }

    void run();
    return () => { cancelled = true; };
  }, [
    applyPenAndAnchorFromFactorSlices,
    applyReplayPackageWindow,
    buildReplayFactorSlices,
    candlesRef,
    enabled,
    ensureWindowRange,
    lastFactorAtTimeRef,
    metadata,
    replayAllCandlesRef,
    replayFocusTime,
    replayIndex,
    seriesId,
    setCandles,
    setReplayCandle,
    setReplayFocusTime,
    setReplayIndex,
    setReplaySlices,
    setReplayTotal,
    status,
    toReplayCandle,
    windows
  ]);
}
