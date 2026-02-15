import { create } from "zustand";

import type {
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  ReplayCoverageStatusResponseV1,
  ReplayCoverageV1,
  ReplayFactorSnapshotV1,
  ReplayPackageMetadataV1,
  ReplayWindowV1
} from "../widgets/chart/types";

export type ReplayMode = "live" | "replay";

export type ReplayPrepareStatus = "idle" | "loading" | "ready" | "error";

export type ReplayStatus = "idle" | "checking" | "coverage" | "building" | "ready" | "out_of_sync" | "error";

export type ReplayWindowBundle = {
  window: ReplayWindowV1;
  factorSnapshots: ReplayFactorSnapshotV1[];
  factorSnapshotByTime: Record<number, Record<string, ReplayFactorSnapshotV1>>;
};

export type ReplayState = {
  mode: ReplayMode;
  playing: boolean;
  speedMs: number;
  index: number;
  total: number;
  focusTime: number | null;
  prepareStatus: ReplayPrepareStatus;
  prepareError: string | null;
  preparedAlignedTime: number | null;
  status: ReplayStatus;
  error: string | null;
  jobId: string | null;
  cacheKey: string | null;
  coverage: ReplayCoverageV1 | null;
  coverageStatus: ReplayCoverageStatusResponseV1 | null;
  metadata: ReplayPackageMetadataV1 | null;
  windows: Record<number, ReplayWindowBundle>;
  currentSlices: GetFactorSlicesResponseV1 | null;
  currentCandleId: string | null;
  currentAtTime: number | null;
  currentDrawActiveIds: string[];
  currentDrawInstructions: OverlayInstructionPatchItemV1[];
  setMode: (mode: ReplayMode) => void;
  setPlaying: (playing: boolean) => void;
  setSpeedMs: (speedMs: number) => void;
  setIndex: (index: number) => void;
  setTotal: (total: number) => void;
  setFocusTime: (time: number | null) => void;
  setPrepareStatus: (status: ReplayPrepareStatus) => void;
  setPrepareError: (error: string | null) => void;
  setPreparedAlignedTime: (time: number | null) => void;
  setStatus: (status: ReplayStatus) => void;
  setError: (error: string | null) => void;
  setJobInfo: (jobId: string | null, cacheKey: string | null) => void;
  setCoverage: (coverage: ReplayCoverageV1 | null) => void;
  setCoverageStatus: (status: ReplayCoverageStatusResponseV1 | null) => void;
  setMetadata: (metadata: ReplayPackageMetadataV1 | null) => void;
  setWindowBundle: (windowIndex: number, bundle: ReplayWindowBundle) => void;
  setCurrentSlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setCurrentCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setCurrentDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  resetData: () => void;
  resetPackage: () => void;
};

function areStringArraysEqual(left: string[], right: string[]) {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    if (left[i] !== right[i]) return false;
  }
  return true;
}

function areDrawInstructionsEquivalent(
  left: OverlayInstructionPatchItemV1[],
  right: OverlayInstructionPatchItemV1[]
) {
  if (left === right) return true;
  if (left.length !== right.length) return false;
  for (let i = 0; i < left.length; i += 1) {
    const current = left[i];
    const next = right[i];
    if (!current || !next) return false;
    if (current.instruction_id !== next.instruction_id) return false;
    if (current.version_id !== next.version_id) return false;
    if (current.visible_time !== next.visible_time) return false;
  }
  return true;
}

export const useReplayStore = create<ReplayState>((set) => {
  const setIfChanged = <K extends keyof ReplayState>(key: K, value: ReplayState[K]) => {
    set((state) => (Object.is(state[key], value) ? state : ({ [key]: value } as Pick<ReplayState, K>)));
  };

  return {
    mode: "live",
    playing: false,
    speedMs: 200,
    index: 0,
    total: 0,
    focusTime: null,
    prepareStatus: "idle",
    prepareError: null,
    preparedAlignedTime: null,
    status: "idle",
    error: null,
    jobId: null,
    cacheKey: null,
    coverage: null,
    coverageStatus: null,
    metadata: null,
    windows: {},
    currentSlices: null,
    currentCandleId: null,
    currentAtTime: null,
    currentDrawActiveIds: [],
    currentDrawInstructions: [],
    setMode: (mode) => setIfChanged("mode", mode),
    setPlaying: (playing) => setIfChanged("playing", playing),
    setSpeedMs: (speedMs) => setIfChanged("speedMs", speedMs),
    setIndex: (index) => setIfChanged("index", index),
    setTotal: (total) => setIfChanged("total", total),
    setFocusTime: (focusTime) => setIfChanged("focusTime", focusTime),
    setPrepareStatus: (prepareStatus) => setIfChanged("prepareStatus", prepareStatus),
    setPrepareError: (prepareError) => setIfChanged("prepareError", prepareError),
    setPreparedAlignedTime: (preparedAlignedTime) => setIfChanged("preparedAlignedTime", preparedAlignedTime),
    setStatus: (status) => setIfChanged("status", status),
    setError: (error) => setIfChanged("error", error),
    setJobInfo: (jobId, cacheKey) =>
      set((state) => (state.jobId === jobId && state.cacheKey === cacheKey ? state : { jobId, cacheKey })),
    setCoverage: (coverage) => setIfChanged("coverage", coverage),
    setCoverageStatus: (coverageStatus) => setIfChanged("coverageStatus", coverageStatus),
    setMetadata: (metadata) => setIfChanged("metadata", metadata),
    setWindowBundle: (windowIndex, bundle) =>
      set((state) =>
        state.windows[windowIndex] === bundle ? state : { windows: { ...state.windows, [windowIndex]: bundle } }
      ),
    setCurrentSlices: (currentSlices) => setIfChanged("currentSlices", currentSlices),
    setCurrentCandle: ({ candleId, atTime, activeIds }) =>
      set((state) => {
        const nextActiveIds = activeIds ?? state.currentDrawActiveIds;
        if (
          state.currentCandleId === candleId &&
          state.currentAtTime === atTime &&
          areStringArraysEqual(state.currentDrawActiveIds, nextActiveIds)
        ) {
          return state;
        }
        return {
          currentCandleId: candleId,
          currentAtTime: atTime,
          currentDrawActiveIds: nextActiveIds
        };
      }),
    setCurrentDrawInstructions: (currentDrawInstructions) =>
      set((state) =>
        areDrawInstructionsEquivalent(state.currentDrawInstructions, currentDrawInstructions)
          ? state
          : { currentDrawInstructions }
      ),
    resetData: () =>
      set({
        playing: false,
        index: 0,
        total: 0,
        focusTime: null,
        prepareStatus: "idle",
        prepareError: null,
        preparedAlignedTime: null,
        status: "idle",
        error: null,
        jobId: null,
        cacheKey: null,
        coverage: null,
        coverageStatus: null,
        metadata: null,
        windows: {},
        currentSlices: null,
        currentCandleId: null,
        currentAtTime: null,
        currentDrawActiveIds: [],
        currentDrawInstructions: []
      }),
    resetPackage: () =>
      set({
        status: "idle",
        error: null,
        jobId: null,
        cacheKey: null,
        coverage: null,
        coverageStatus: null,
        metadata: null,
        windows: {},
        currentSlices: null,
        currentCandleId: null,
        currentAtTime: null,
        currentDrawActiveIds: [],
        currentDrawInstructions: []
      })
  };
});
