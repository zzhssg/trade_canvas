import { create } from "zustand";

import type { DebugEvent, DebugPipe } from "../debug/debug";

const MAX_DEFAULT = 2000;

type DebugFilter = "all" | DebugPipe;

type DebugLogState = {
  events: DebugEvent[];
  filter: DebugFilter;
  query: string;
  autoScroll: boolean;
  maxEntries: number;

  append: (e: DebugEvent) => void;
  clear: () => void;
  setFilter: (filter: DebugFilter) => void;
  setQuery: (query: string) => void;
  toggleAutoScroll: () => void;
  setMaxEntries: (n: number) => void;
};

export const useDebugLogStore = create<DebugLogState>()((set, get) => ({
  events: [],
  filter: "all",
  query: "",
  autoScroll: true,
  maxEntries: MAX_DEFAULT,

  append: (e) => {
    const maxEntries = Math.max(100, Math.min(10000, Number(get().maxEntries) || MAX_DEFAULT));
    set((s) => {
      const next = [...s.events, e];
      if (next.length <= maxEntries) return { events: next };
      return { events: next.slice(next.length - maxEntries) };
    });
  },
  clear: () => set({ events: [] }),
  setFilter: (filter) => set({ filter }),
  setQuery: (query) => set({ query }),
  toggleAutoScroll: () => set((s) => ({ autoScroll: !s.autoScroll })),
  setMaxEntries: (n) => set({ maxEntries: Math.max(100, Math.min(10000, Number(n) || MAX_DEFAULT)) })
}));
