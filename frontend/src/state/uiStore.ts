import { create } from "zustand";
import { persist } from "zustand/middleware";

type BottomTab = "Ledger" | "Signals" | "Logs" | "Orders" | "Backtest";
type SidebarTab = "Market" | "Strategy" | "Indicators" | "Replay";
export type MarketMode = "spot" | "futures";

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

type UiState = {
  exchange: "binance";
  market: MarketMode;
  symbol: string;
  timeframe: string;

  toolRailWidth: number;
  sidebarCollapsed: boolean;
  sidebarWidth: number;
  bottomCollapsed: boolean;

  activeSidebarTab: SidebarTab;
  activeBottomTab: BottomTab;

  setMarket: (market: MarketMode) => void;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: string) => void;
  setToolRailWidth: (width: number) => void;
  toggleSidebarCollapsed: () => void;
  toggleBottomCollapsed: () => void;
  setSidebarWidth: (width: number) => void;
  setActiveSidebarTab: (tab: SidebarTab) => void;
  setActiveBottomTab: (tab: BottomTab) => void;
};

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      exchange: "binance",
      market: "futures",
      symbol: "BTC/USDT",
      timeframe: "1m",

      toolRailWidth: 52,
      sidebarCollapsed: false,
      sidebarWidth: 280,
      bottomCollapsed: false,

      activeSidebarTab: "Market",
      activeBottomTab: "Ledger",

      setMarket: (market) => set({ market }),
      setSymbol: (symbol) => set({ symbol }),
      setTimeframe: (timeframe) => set({ timeframe }),
      setToolRailWidth: (toolRailWidth) => set({ toolRailWidth: clamp(toolRailWidth, 44, 96) }),
      toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleBottomCollapsed: () => set((s) => ({ bottomCollapsed: !s.bottomCollapsed })),
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth: clamp(sidebarWidth, 220, 520) }),
      setActiveSidebarTab: (activeSidebarTab) => set({ activeSidebarTab }),
      setActiveBottomTab: (activeBottomTab) => set({ activeBottomTab })
    }),
    {
      name: "trade-canvas-ui",
      version: 4,
      migrate: (persisted) => {
        const state = persisted as Partial<UiState> | undefined;
        return {
          ...state,
          exchange: "binance",
          market: (state?.market as MarketMode | undefined) ?? "futures",
          toolRailWidth: clamp(Number(state?.toolRailWidth ?? 52), 44, 96),
          sidebarWidth: clamp(Number(state?.sidebarWidth ?? 280), 220, 520)
        } as UiState;
      }
    }
  )
);
