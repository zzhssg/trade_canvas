import { create } from "zustand";

import type { WorldStateV1 } from "../widgets/chart/types";

export type ReplayMode = "live" | "replay";

type ReplayPrepareStatus = "idle" | "loading" | "ready" | "error";

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
  resetData: () => void;
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
      preparedAlignedTime: null
    })
}));
