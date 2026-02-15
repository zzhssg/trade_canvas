import { useReplayActions, useReplayControlState } from "../../state/replayStoreSelectors";

export function useReplayBindings() {
  const replayState = useReplayControlState();
  const replayActions = useReplayActions();

  return {
    replayMode: replayState.mode,
    replayPlaying: replayState.playing,
    replaySpeedMs: replayState.speedMs,
    replayIndex: replayState.index,
    replayTotal: replayState.total,
    replayFocusTime: replayState.focusTime,
    replayPrepareStatus: replayState.prepareStatus,
    replayPreparedAlignedTime: replayState.preparedAlignedTime,
    setReplayPlaying: replayActions.setPlaying,
    setReplayIndex: replayActions.setIndex,
    setReplayTotal: replayActions.setTotal,
    setReplayFocusTime: replayActions.setFocusTime,
    setReplayPrepareStatus: replayActions.setPrepareStatus,
    setReplayPrepareError: replayActions.setPrepareError,
    setReplayPreparedAlignedTime: replayActions.setPreparedAlignedTime,
    setReplaySlices: replayActions.setCurrentSlices,
    setReplayCandle: replayActions.setCurrentCandle,
    setReplayDrawInstructions: replayActions.setCurrentDrawInstructions,
    resetReplayData: replayActions.resetData
  };
}
