import { useCallback, useEffect } from "react";

import { prepareReplay } from "./api";

type ReplayPrepareStatus = "idle" | "loading" | "ready" | "error";

type UseReplayControllerArgs = {
  seriesId: string;
  replayEnabled: boolean;
  replayPlaying: boolean;
  replaySpeedMs: number;
  replayIndex: number;
  replayTotal: number;
  windowCandles: number;
  resetReplayData: () => void;
  setReplayPlaying: (playing: boolean) => void;
  setReplayIndex: (index: number) => void;
  setReplayPrepareStatus: (status: ReplayPrepareStatus) => void;
  setReplayPrepareError: (error: string | null) => void;
  setReplayPreparedAlignedTime: (time: number | null) => void;
};

/**
 * 回放播放控制 hook。
 *
 * 职责:
 * - series 切换时重置回放数据
 * - 启用回放时调用 prepare API 获取对齐时间
 * - 播放中通过 setTimeout 链式推进 replayIndex
 * - 提供 setReplayIndexAndFocus 用于手动跳帧 (自动 clamp 到有效范围)
 */
export function useReplayController({
  seriesId,
  replayEnabled,
  replayPlaying,
  replaySpeedMs,
  replayIndex,
  replayTotal,
  windowCandles,
  resetReplayData,
  setReplayPlaying,
  setReplayIndex,
  setReplayPrepareStatus,
  setReplayPrepareError,
  setReplayPreparedAlignedTime
}: UseReplayControllerArgs) {
  const setReplayIndexAndFocus = useCallback(
    (nextIndex: number, opts?: { pause?: boolean }) => {
      if (replayTotal <= 0) return;
      const clamped = Math.max(0, Math.min(nextIndex, replayTotal - 1));
      if (opts?.pause) setReplayPlaying(false);
      setReplayIndex(clamped);
    },
    [replayTotal, setReplayIndex, setReplayPlaying]
  );

  useEffect(() => {
    resetReplayData();
  }, [resetReplayData, seriesId]);

  useEffect(() => {
    if (!replayEnabled) resetReplayData();
  }, [replayEnabled, resetReplayData]);

  useEffect(() => {
    if (!replayEnabled) {
      setReplayPrepareStatus("idle");
      setReplayPrepareError(null);
      setReplayPreparedAlignedTime(null);
      return;
    }

    let cancelled = false;
    setReplayPrepareStatus("loading");
    setReplayPrepareError(null);
    setReplayPreparedAlignedTime(null);

    const run = async () => {
      try {
        const prep = await prepareReplay({ seriesId, windowCandles });
        if (cancelled) return;
        setReplayPreparedAlignedTime(prep.aligned_time);
        setReplayPrepareStatus("ready");
      } catch (e: unknown) {
        if (cancelled) return;
        setReplayPrepareStatus("error");
        setReplayPrepareError(e instanceof Error ? e.message : "Replay prepare failed");
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [
    replayEnabled,
    seriesId,
    setReplayPrepareError,
    setReplayPrepareStatus,
    setReplayPreparedAlignedTime,
    windowCandles
  ]);

  useEffect(() => {
    if (!replayEnabled) return;
    if (!replayPlaying) return;
    if (replayTotal <= 0) return;
    if (replayIndex >= replayTotal - 1) return;
    const id = window.setTimeout(() => {
      setReplayIndexAndFocus(replayIndex + 1);
    }, replaySpeedMs);
    return () => window.clearTimeout(id);
  }, [replayEnabled, replayIndex, replayPlaying, replaySpeedMs, replayTotal, setReplayIndexAndFocus]);

  return { setReplayIndexAndFocus };
}
