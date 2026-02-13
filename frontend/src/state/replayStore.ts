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
  /** "live" = 实时行情, "replay" = 回放模式 */
  mode: ReplayMode;
  /** 回放是否正在自动播放 */
  playing: boolean;
  /** 自动播放每帧间隔 (ms) */
  speedMs: number;
  /** 当前回放帧索引 (0-based) */
  index: number;
  /** 回放总帧数 (= total_candles) */
  total: number;
  /** 当前帧对应的 candle open_time (unix seconds), null 表示尚未定位 */
  focusTime: number | null;
  /** 旧版单帧 world-state 快照 (v0 回放), package v1 不使用 */
  frame: WorldStateV1 | null;
  /** 旧版帧加载中标记 */
  frameLoading: boolean;
  /** 旧版帧加载错误 */
  frameError: string | null;
  /** prepare API 调用状态: idle → loading → ready | error */
  prepareStatus: ReplayPrepareStatus;
  /** prepare 阶段错误信息 */
  prepareError: string | null;
  /** prepare 返回的对齐时间 (最近 closed candle 的 open_time) */
  preparedAlignedTime: number | null;
  /** package v1 构建状态机: idle → checking → coverage → building → ready | out_of_sync | error */
  status: ReplayStatus;
  /** package v1 构建错误信息 */
  error: string | null;
  /** 后端 replay build job ID */
  jobId: string | null;
  /** 后端 replay build cache key, 用于判断缓存命中 */
  cacheKey: string | null;
  /** 数据覆盖度信息 (required_candles / candles_ready / time range) */
  coverage: ReplayCoverageV1 | null;
  /** 覆盖度构建轮询状态 */
  coverageStatus: ReplayCoverageStatusResponseV1 | null;
  /** 回放包元数据 (total_candles, window_size, snapshot_interval 等) */
  metadata: ReplayPackageMetadataV1 | null;
  /** 因子历史事件列表, 按 event_id 排序 */
  historyEvents: ReplayHistoryEventV1[];
  /** 已加载的窗口数据, key = windowIndex */
  windows: Record<number, ReplayWindowBundle>;
  /** 当前帧的因子切片 (pen/anchor/zhongshu 等) */
  currentSlices: GetFactorSlicesResponseV1 | null;
  /** 当前帧的 candle_id (series_id:open_time) */
  currentCandleId: string | null;
  /** 当前帧的 open_time (unix seconds) */
  currentAtTime: number | null;
  /** 当前帧激活的 draw overlay ID 列表 */
  currentDrawActiveIds: string[];
  /** 当前帧的 draw overlay 渲染指令 */
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
  /** 完全重置回放状态 (切换 series 或退出回放时调用) */
  resetData: () => void;
  /** 仅重置 package v1 相关状态 (保留 mode/playing/speedMs, 重新触发构建) */
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
