import { create } from "zustand";
import type { WorktreeInfo } from "../lib/devApi";

type DevState = {
  worktrees: WorktreeInfo[];
  loading: boolean;
  error: string | null;
  selectedWorktreeId: string | null;

  setWorktrees: (worktrees: WorktreeInfo[]) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedWorktreeId: (id: string | null) => void;
  updateWorktree: (id: string, updates: Partial<WorktreeInfo>) => void;
};

export const useDevStore = create<DevState>()((set) => ({
  worktrees: [],
  loading: false,
  error: null,
  selectedWorktreeId: null,

  setWorktrees: (worktrees) => set({ worktrees }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
  setSelectedWorktreeId: (selectedWorktreeId) => set({ selectedWorktreeId }),
  updateWorktree: (id, updates) =>
    set((state) => ({
      worktrees: state.worktrees.map((wt) =>
        wt.id === id ? { ...wt, ...updates } : wt
      ),
    })),
}));
