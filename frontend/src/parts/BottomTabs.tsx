import { Suspense, lazy } from "react";

import { useUiStore } from "../state/uiStore";

const TABS = ["Ledger", "Signals", "Logs", "Orders", "Backtest"] as const;
const BacktestPanel = lazy(async () => {
  const module = await import("./BacktestPanel");
  return { default: module.BacktestPanel };
});

export function BottomTabs() {
  const { bottomCollapsed, toggleBottomCollapsed, activeBottomTab, setActiveBottomTab } = useUiStore();

  return (
    <div
      className="w-full border-t border-white/10 bg-white/[0.045] backdrop-blur"
      data-testid="bottom-tabs"
    >
      <div className="flex h-10 items-center justify-between border-b border-white/10 px-2">
        <div className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveBottomTab(tab)}
              data-testid={`bottom-tab-${tab}`}
              className={[
                "rounded-md px-2 py-1 text-xs focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                activeBottomTab === tab ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white/85"
              ].join(" ")}
            >
              {tab}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={toggleBottomCollapsed}
          className="rounded-md border border-white/10 bg-black/25 px-2 py-1 text-xs text-white/80 hover:bg-black/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
        >
          {bottomCollapsed ? "Expand" : "Collapse"}
        </button>
      </div>
      {bottomCollapsed ? null : (
        <div className="p-3">
          {activeBottomTab === "Backtest" ? (
            <Suspense fallback={<div className="text-xs text-white/60">Loading backtest panel...</div>}>
              <BacktestPanel />
            </Suspense>
          ) : (
            <div className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset]">
              {activeBottomTab} (MVP placeholder)
            </div>
          )}
        </div>
      )}
    </div>
  );
}
