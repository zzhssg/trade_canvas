import { useShallow } from "zustand/shallow";
import { type ReplayState, useReplayStore } from "./replayStore";

export type ReplayControlStateSnapshot = Pick<
  ReplayState,
  "mode" | "playing" | "speedMs" | "index" | "total" | "focusTime" | "prepareStatus" | "preparedAlignedTime"
>;

export type ReplayPackageStateSnapshot = Pick<
  ReplayState,
  "status" | "error" | "coverage" | "coverageStatus" | "metadata" | "windows" | "jobId" | "cacheKey"
>;

export type ReplayActionsSnapshot = Pick<
  ReplayState,
  | "setMode"
  | "setPlaying"
  | "setSpeedMs"
  | "setIndex"
  | "setTotal"
  | "setFocusTime"
  | "setPrepareStatus"
  | "setPrepareError"
  | "setPreparedAlignedTime"
  | "setStatus"
  | "setError"
  | "setJobInfo"
  | "setCoverage"
  | "setCoverageStatus"
  | "setMetadata"
  | "setWindowBundle"
  | "setCurrentSlices"
  | "setCurrentCandle"
  | "setCurrentDrawInstructions"
  | "resetData"
  | "resetPackage"
>;

const replayControlSelector = (state: ReplayState): ReplayControlStateSnapshot => ({
  mode: state.mode,
  playing: state.playing,
  speedMs: state.speedMs,
  index: state.index,
  total: state.total,
  focusTime: state.focusTime,
  prepareStatus: state.prepareStatus,
  preparedAlignedTime: state.preparedAlignedTime
});

const replayPackageSelector = (state: ReplayState): ReplayPackageStateSnapshot => ({
  status: state.status,
  error: state.error,
  coverage: state.coverage,
  coverageStatus: state.coverageStatus,
  metadata: state.metadata,
  windows: state.windows,
  jobId: state.jobId,
  cacheKey: state.cacheKey
});

const replayActionsSelector = (state: ReplayState): ReplayActionsSnapshot => ({
  setMode: state.setMode,
  setPlaying: state.setPlaying,
  setSpeedMs: state.setSpeedMs,
  setIndex: state.setIndex,
  setTotal: state.setTotal,
  setFocusTime: state.setFocusTime,
  setPrepareStatus: state.setPrepareStatus,
  setPrepareError: state.setPrepareError,
  setPreparedAlignedTime: state.setPreparedAlignedTime,
  setStatus: state.setStatus,
  setError: state.setError,
  setJobInfo: state.setJobInfo,
  setCoverage: state.setCoverage,
  setCoverageStatus: state.setCoverageStatus,
  setMetadata: state.setMetadata,
  setWindowBundle: state.setWindowBundle,
  setCurrentSlices: state.setCurrentSlices,
  setCurrentCandle: state.setCurrentCandle,
  setCurrentDrawInstructions: state.setCurrentDrawInstructions,
  resetData: state.resetData,
  resetPackage: state.resetPackage
});

export function useReplayControlState() {
  return useReplayStore(useShallow(replayControlSelector));
}

export function useReplayPackageState() {
  return useReplayStore(useShallow(replayPackageSelector));
}

export function useReplayActions() {
  return useReplayStore(useShallow(replayActionsSelector));
}
