import { useEffect } from "react";
import type { Dispatch, MutableRefObject, SetStateAction } from "react";

import type { ReplayWindowBundle } from "../../state/replayStore";

import type {
  Candle,
  GetFactorSlicesResponseV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayHistoryEventV1,
  ReplayKlineBarV1,
  ReplayPackageMetadataV1,
  ReplayWindowV1
} from "./types";

type BuildReplayFactorSlices = (args: {
  atTime: number;
  toEventId: number;
  historyEvents: ReplayHistoryEventV1[];
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
}) => GetFactorSlicesResponseV1;

type ApplyReplayPackageWindow = (
  bundle: {
    window: ReplayWindowV1;
    headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
    historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
  },
  targetIdx: number
) => string[];

type UseReplayPackageWindowSyncArgs = {
  enabled: boolean;
  status: string;
  metadata: ReplayPackageMetadataV1 | null;
  windows: Record<number, ReplayWindowBundle>;
  historyEvents: ReplayHistoryEventV1[];
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

/**
 * 回放窗口数据同步 hook — 将 package window 数据投射到图表。
 *
 * 当 status="ready" 且 replayIndex 变化时:
 * 1. ensureWindowRange 确保所有窗口数据已加载
 * 2. 填充 replayAllCandlesRef (全量 candle 数组) 并更新图表 candles
 * 3. applyReplayPackageWindow 应用当前窗口的 overlay 数据
 * 4. buildReplayFactorSlices 构建当前帧的因子切片
 * 5. applyPenAndAnchorFromFactorSlices 渲染 pen/anchor 到图表
 * 6. setReplayCandle 更新当前帧的 candleId + activeIds
 */
export function useReplayPackageWindowSync({
  enabled,
  status,
  metadata,
  windows,
  historyEvents,
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
    if (!enabled) return;
    if (status !== "ready") return;
    const meta = metadata;
    if (!meta || meta.total_candles <= 0) return;
    const metaValue = meta;
    const total = metaValue.total_candles;
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
      if (filled.length === total) {
        const all = replayAllCandlesRef.current as Candle[];
        candlesRef.current = all;
        setCandles(all);
      } else if (filled.length > 0) {
        candlesRef.current = filled;
        setCandles(filled);
      }

      const windowIndex = Math.floor(clamped / metaValue.window_size);
      const bundle = windows[windowIndex];
      if (!bundle) return;

      const activeIds = applyReplayPackageWindow(bundle, clamped);
      const candle = replayAllCandlesRef.current[clamped];
      if (!candle) return;
      const toTime = candle.time as number;
      setReplayFocusTime(toTime);
      const delta = bundle.historyDeltaByIdx[clamped];
      const toEventId = delta ? delta.to_event_id : 0;
      const slices = buildReplayFactorSlices({
        atTime: toTime,
        toEventId,
        historyEvents,
        headByTime: bundle.headByTime
      });
      lastFactorAtTimeRef.current = toTime;
      applyPenAndAnchorFromFactorSlices(slices);
      setReplaySlices(slices);
      setReplayCandle({ candleId: slices.candle_id ?? `${seriesId}:${toTime}`, atTime: toTime, activeIds });
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    applyPenAndAnchorFromFactorSlices,
    applyReplayPackageWindow,
    buildReplayFactorSlices,
    candlesRef,
    enabled,
    ensureWindowRange,
    historyEvents,
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
