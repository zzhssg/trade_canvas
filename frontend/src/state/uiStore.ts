import { create } from "zustand";
import { persist } from "zustand/middleware";

type BottomTab = "Ledger" | "Signals" | "Logs" | "Orders" | "Backtest";
type SidebarTab = "Market" | "Strategy" | "Indicators" | "Replay" | "Debug";
export type MarketMode = "spot" | "futures";
export type ChartToolKey = "cursor" | "measure" | "fib" | "position_long" | "position_short";

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
  activeChartTool: ChartToolKey;

  setMarket: (market: MarketMode) => void;
  setSymbol: (symbol: string) => void;
  setTimeframe: (timeframe: string) => void;
  setToolRailWidth: (width: number) => void;
  toggleSidebarCollapsed: () => void;
  toggleBottomCollapsed: () => void;
  setSidebarWidth: (width: number) => void;
  setActiveSidebarTab: (tab: SidebarTab) => void;
  setActiveBottomTab: (tab: BottomTab) => void;
  setActiveChartTool: (tool: ChartToolKey) => void;
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
      activeChartTool: "cursor",

      setMarket: (market) => set({ market }),
      setSymbol: (symbol) => set({ symbol }),
      setTimeframe: (timeframe) => set({ timeframe }),
      setToolRailWidth: (toolRailWidth) => set({ toolRailWidth: clamp(toolRailWidth, 44, 96) }),
      toggleSidebarCollapsed: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
      toggleBottomCollapsed: () => set((s) => ({ bottomCollapsed: !s.bottomCollapsed })),
      setSidebarWidth: (sidebarWidth) => set({ sidebarWidth: clamp(sidebarWidth, 220, 520) }),
      setActiveSidebarTab: (activeSidebarTab) => set({ activeSidebarTab }),
      setActiveBottomTab: (activeBottomTab) => set({ activeBottomTab }),
      setActiveChartTool: (activeChartTool) => set({ activeChartTool })
    }),
    {
      name: "trade-canvas-ui",
      version: 6,
      // Persist only stable UI preferences. Chart tools are intentionally in-memory only.
      partialize: (s) => ({
        exchange: s.exchange,
        market: s.market,
        symbol: s.symbol,
        timeframe: s.timeframe,
        toolRailWidth: s.toolRailWidth,
        sidebarCollapsed: s.sidebarCollapsed,
        sidebarWidth: s.sidebarWidth,
        bottomCollapsed: s.bottomCollapsed,
        activeSidebarTab: s.activeSidebarTab,
        activeBottomTab: s.activeBottomTab
      }),
      migrate: (persisted) => {
        const state = persisted as Partial<UiState> | undefined;
        return {
          ...state,
          exchange: "binance",
          market: (state?.market as MarketMode | undefined) ?? "futures",
          toolRailWidth: clamp(Number(state?.toolRailWidth ?? 52), 44, 96),
          sidebarWidth: clamp(Number(state?.sidebarWidth ?? 280), 220, 520),
          sidebarCollapsed: Boolean(state?.sidebarCollapsed ?? false),
          bottomCollapsed: Boolean(state?.bottomCollapsed ?? false),
          activeSidebarTab: ((state?.activeSidebarTab as SidebarTab | undefined) ?? "Market"),
          activeBottomTab: ((state?.activeBottomTab as BottomTab | undefined) ?? "Ledger"),
          activeChartTool: "cursor"
        } as UiState;
      }
    }
  )
);
