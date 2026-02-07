import { create } from "zustand";

import type {
  GetFactorSlicesResponseV1,
  ReplayCoverageStatusResponseV1,
  ReplayCoverageV1,
  ReplayFactorHeadSnapshotV1,
  ReplayHistoryDeltaV1,
  ReplayHistoryEventV1,
  ReplayPackageMetadataV1,
  ReplayWindowV1
} from "../widgets/chart/types";

const ENABLE_REPLAY_V1 = import.meta.env.VITE_ENABLE_REPLAY_V1 === "1";

export type ReplayStatus =
  | "idle"
  | "checking"
  | "coverage"
  | "building"
  | "ready"
  | "out_of_sync"
  | "error";

export type ReplayWindowBundle = {
  window: ReplayWindowV1;
  headSnapshots: ReplayFactorHeadSnapshotV1[];
  historyDeltas: ReplayHistoryDeltaV1[];
  headByTime: Record<number, Record<string, ReplayFactorHeadSnapshotV1>>;
  historyDeltaByIdx: Record<number, ReplayHistoryDeltaV1>;
};

type ReplayState = {
  enabled: boolean;
  playing: boolean;
  speedMs: number;
  index: number;
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
  setEnabled: (enabled: boolean) => void;
  setPlaying: (playing: boolean) => void;
  setSpeedMs: (speedMs: number) => void;
  setIndex: (index: number) => void;
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
  resetPackage: () => void;
};

export const useReplayStore = create<ReplayState>((set) => ({
  enabled: ENABLE_REPLAY_V1,
  playing: ENABLE_REPLAY_V1,
  speedMs: 200,
  index: 0,
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
  setEnabled: (enabled) => set({ enabled }),
  setPlaying: (playing) => set({ playing }),
  setSpeedMs: (speedMs) => set({ speedMs }),
  setIndex: (index) => set({ index }),
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
      currentDrawActiveIds: []
    })
}));
