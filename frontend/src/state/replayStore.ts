import { create } from "zustand";

import type {
  GetFactorSlicesResponseV1,
  OverlayInstructionPatchItemV1,
  ReplayCoverageStatusResponseV1,
  ReplayCoverageV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayHistoryEventV1,
  ReplayPackageMetadataV1,
  ReplayWindowV1,
  WorldStateV1
} from "../widgets/chart/types";

export type ReplayMode = "live" | "replay";

export type ReplayPrepareStatus = "idle" | "loading" | "ready" | "error";

export type ReplayStatus = "idle" | "checking" | "coverage" | "building" | "ready" | "out_of_sync" | "error";

export type ReplayWindowBundle = {
  window: ReplayWindowV1;
  headSnapshots: ReplayFactorHeadSnapshotV1[];
  historyDeltas: ReplayHistoryDeltaV1[];
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

type ReplayState = {
  mode: ReplayMode;
  playing: boolean;
  speedMs: number;
  index: number;
  total: number;
  focusTime: number | null;
  frame: WorldStateV1 | null;
  frameLoading: boolean;
  frameError: string | null;
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
  historyEvents: ReplayHistoryEventV1[];
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
  setFrame: (frame: WorldStateV1 | null) => void;
  setFrameLoading: (loading: boolean) => void;
  setFrameError: (error: string | null) => void;
  setPrepareStatus: (status: ReplayPrepareStatus) => void;
  setPrepareError: (error: string | null) => void;
  setPreparedAlignedTime: (time: number | null) => void;
  setStatus: (status: ReplayStatus) => void;
  setError: (error: string | null) => void;
  setJobInfo: (jobId: string | null, cacheKey: string | null) => void;
  setCoverage: (coverage: ReplayCoverageV1 | null) => void;
  setCoverageStatus: (status: ReplayCoverageStatusResponseV1 | null) => void;
  setMetadata: (metadata: ReplayPackageMetadataV1 | null) => void;
  setHistoryEvents: (events: ReplayHistoryEventV1[]) => void;
  setWindowBundle: (windowIndex: number, bundle: ReplayWindowBundle) => void;
  setCurrentSlices: (slices: GetFactorSlicesResponseV1 | null) => void;
  setCurrentCandle: (payload: { candleId: string | null; atTime: number | null; activeIds?: string[] }) => void;
  setCurrentDrawInstructions: (items: OverlayInstructionPatchItemV1[]) => void;
  resetData: () => void;
  resetPackage: () => void;
};

export const useReplayStore = create<ReplayState>((set) => ({
  mode: "live",
  playing: false,
  speedMs: 200,
  index: 0,
  total: 0,
  focusTime: null,
  frame: null,
  frameLoading: false,
  frameError: null,
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
  historyEvents: [],
  windows: {},
  currentSlices: null,
  currentCandleId: null,
  currentAtTime: null,
  currentDrawActiveIds: [],
  currentDrawInstructions: [],
  setMode: (mode) => set({ mode }),
  setPlaying: (playing) => set({ playing }),
  setSpeedMs: (speedMs) => set({ speedMs }),
  setIndex: (index) => set({ index }),
  setTotal: (total) => set({ total }),
  setFocusTime: (focusTime) => set({ focusTime }),
  setFrame: (frame) => set({ frame }),
  setFrameLoading: (frameLoading) => set({ frameLoading }),
  setFrameError: (frameError) => set({ frameError }),
  setPrepareStatus: (prepareStatus) => set({ prepareStatus }),
  setPrepareError: (prepareError) => set({ prepareError }),
  setPreparedAlignedTime: (preparedAlignedTime) => set({ preparedAlignedTime }),
  setStatus: (status) => set({ status }),
  setError: (error) => set({ error }),
  setJobInfo: (jobId, cacheKey) => set({ jobId, cacheKey }),
  setCoverage: (coverage) => set({ coverage }),
  setCoverageStatus: (coverageStatus) => set({ coverageStatus }),
  setMetadata: (metadata) => set({ metadata }),
  setHistoryEvents: (historyEvents) => set({ historyEvents }),
  setWindowBundle: (windowIndex, bundle) =>
    set((state) => ({ windows: { ...state.windows, [windowIndex]: bundle } })),
  setCurrentSlices: (currentSlices) => set({ currentSlices }),
  setCurrentCandle: ({ candleId, atTime, activeIds }) =>
    set((state) => ({
      currentCandleId: candleId,
      currentAtTime: atTime,
      currentDrawActiveIds: activeIds ?? state.currentDrawActiveIds
    })),
  setCurrentDrawInstructions: (currentDrawInstructions) => set({ currentDrawInstructions }),
  resetData: () =>
    set({
      playing: false,
      index: 0,
      total: 0,
      focusTime: null,
      frame: null,
      frameLoading: false,
      frameError: null,
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
      historyEvents: [],
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
      historyEvents: [],
      windows: {},
      currentSlices: null,
      currentCandleId: null,
      currentAtTime: null,
      currentDrawActiveIds: [],
      currentDrawInstructions: []
    })
}));
