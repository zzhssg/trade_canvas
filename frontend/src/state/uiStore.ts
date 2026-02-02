import { create } from "zustand";
import { persist } from "zustand/middleware";

type BottomTab = "Ledger" | "Signals" | "Logs" | "Orders";
type SidebarTab = "Market" | "Strategy" | "Indicators" | "Replay";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

type UiState = {
  symbol: string;
  timeframe: string;

  sidebarCollapsed: boolean;
  sidebarWidth: number;
  bottomCollapsed: boolean;
  bottomHeight: number;

  activeSidebarTab: SidebarTab;
  activeBottomTab: BottomTab;

  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: string) => void;
  toggleSidebarCollapsed: () => void;
  toggleBottomCollapsed: () => void;
  setSidebarWidth: (width: number) => void;
  setBottomHeight: (height: number) => void;
  setActiveSidebarTab: (tab: SidebarTab) => void;
  setActiveBottomTab: (tab: BottomTab) => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      symbol: "BTC/USDT",
      timeframe: "1m",

      sidebarCollapsed: false,
      sidebarWidth: 280,
      bottomCollapsed: false,
      bottomHeight: 240,

      activeSidebarTab: "Market",
      activeBottomTab: "Ledger",

      setSymbol: (symbol) => set({ symbol }),
      setTimeframe: (timeframe) => set({ timeframe }),
      toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleBottomCollapsed: () => set((s) => ({ bottomCollapsed: !s.bottomCollapsed })),
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth: clamp(sidebarWidth, 220, 520) }),
      setBottomHeight: (bottomHeight) => set({ bottomHeight: clamp(bottomHeight, 40, 640) }),
      setActiveSidebarTab: (activeSidebarTab) => set({ activeSidebarTab }),
      setActiveBottomTab: (activeBottomTab) => set({ activeBottomTab })
    }),
    {
      name: "trade-canvas-ui",
      version: 1,
      migrate: (persisted) => {
        const state = persisted as Partial<UiState> | undefined;
        return {
          ...state,
          sidebarWidth: clamp(Number(state?.sidebarWidth ?? 280), 220, 520),
          bottomHeight: clamp(Number(state?.bottomHeight ?? 240), 40, 640)
        } as UiState;
      }
    }
  )
);
