import type { Page } from "@playwright/test";

type UiSeedArgs = {
  symbol: string;
  timeframe: string;
  overrides?: Record<string, unknown>;
};

type InitStorageArgs = {
  clear?: boolean;
  uiState?: Record<string, unknown>;
  uiVersion?: number;
  factorsState?: Record<string, unknown>;
  factorsVersion?: number;
  extras?: Record<string, string>;
};

export function buildDefaultUiState(args: UiSeedArgs): Record<string, unknown> {
  const { symbol, timeframe, overrides = {} } = args;
  return {
    exchange: "binance",
    market: "futures",
    symbol,
    timeframe,
    toolRailWidth: 52,
    sidebarCollapsed: false,
    sidebarWidth: 280,
    bottomCollapsed: false,
    bottomHeight: 240,
    activeSidebarTab: "Market",
    activeBottomTab: "Ledger",
    activeChartTool: "cursor",
    ...overrides,
  };
}

export function buildFactorsState(visibleFeatures: Record<string, boolean>): Record<string, unknown> {
  return {
    visibleFeatures,
  };
}

export async function initTradeCanvasStorage(page: Page, args: InitStorageArgs = {}): Promise<void> {
  const {
    clear = true,
    uiState,
    uiVersion = 6,
    factorsState,
    factorsVersion = 1,
    extras = {},
  } = args;
  const uiPayload = uiState ? { version: uiVersion, state: uiState } : null;
  const factorsPayload = factorsState ? { version: factorsVersion, state: factorsState } : null;

  await page.addInitScript(
    ({ clearStorage, ui, factors, extraStorage }) => {
      if (clearStorage) {
        localStorage.clear();
      }
      if (ui) {
        localStorage.setItem("trade-canvas-ui", JSON.stringify(ui));
      }
      if (factors) {
        localStorage.setItem("trade-canvas-factors", JSON.stringify(factors));
      }
      for (const [key, value] of Object.entries(extraStorage)) {
        localStorage.setItem(key, value);
      }
    },
    {
      clearStorage: clear,
      ui: uiPayload,
      factors: factorsPayload,
      extraStorage: extras,
    }
  );
}
