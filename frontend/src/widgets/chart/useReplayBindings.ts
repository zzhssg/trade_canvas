import { useReplayStore } from "../../state/replayStore";

export function useReplayBindings() {
  const replayMode = useReplayStore((s) => s.mode);
  const replayPlaying = useReplayStore((s) => s.playing);
  const replaySpeedMs = useReplayStore((s) => s.speedMs);
  const replayIndex = useReplayStore((s) => s.index);
  const replayTotal = useReplayStore((s) => s.total);
  const replayFocusTime = useReplayStore((s) => s.focusTime);
  const replayPrepareStatus = useReplayStore((s) => s.prepareStatus);
  const replayPreparedAlignedTime = useReplayStore((s) => s.preparedAlignedTime);
  const setReplayPlaying = useReplayStore((s) => s.setPlaying);
  const setReplayIndex = useReplayStore((s) => s.setIndex);
  const setReplayTotal = useReplayStore((s) => s.setTotal);
  const setReplayFocusTime = useReplayStore((s) => s.setFocusTime);
  const setReplayFrame = useReplayStore((s) => s.setFrame);
  const setReplayFrameLoading = useReplayStore((s) => s.setFrameLoading);
  const setReplayFrameError = useReplayStore((s) => s.setFrameError);
  const setReplayPrepareStatus = useReplayStore((s) => s.setPrepareStatus);
  const setReplayPrepareError = useReplayStore((s) => s.setPrepareError);
  const setReplayPreparedAlignedTime = useReplayStore((s) => s.setPreparedAlignedTime);
  const setReplaySlices = useReplayStore((s) => s.setCurrentSlices);
  const setReplayCandle = useReplayStore((s) => s.setCurrentCandle);
  const setReplayDrawInstructions = useReplayStore((s) => s.setCurrentDrawInstructions);
  const resetReplayData = useReplayStore((s) => s.resetData);

  return {
    replayMode,
    replayPlaying,
    replaySpeedMs,
    replayIndex,
    replayTotal,
    replayFocusTime,
    replayPrepareStatus,
    replayPreparedAlignedTime,
    setReplayPlaying,
    setReplayIndex,
    setReplayTotal,
    setReplayFocusTime,
    setReplayFrame,
    setReplayFrameLoading,
    setReplayFrameError,
    setReplayPrepareStatus,
    setReplayPrepareError,
    setReplayPreparedAlignedTime,
    setReplaySlices,
    setReplayCandle,
    setReplayDrawInstructions,
    resetReplayData
  };
}
