import { useUiStore } from "../state/uiStore";
import { BacktestPanel } from "./BacktestPanel";

const TABS = ["Ledger", "Signals", "Logs", "Orders", "Backtest"] as const;

export function BottomTabs() {
  const { bottomCollapsed, toggleBottomCollapsed, activeBottomTab, setActiveBottomTab } = useUiStore();

  return (
    <div className="h-full overflow-hidden border-t border-white/10 bg-white/5" data-testid="bottom-tabs">
      <div className="flex h-10 items-center justify-between border-b border-white/10 px-2">
        <div className="flex items-center gap-1">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              onClick={() => setActiveBottomTab(tab)}
              data-testid={`bottom-tab-${tab}`}
              className={[
                "rounded px-2 py-1 text-xs",
                activeBottomTab === tab ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
              ].join(" ")}
            >
              {tab}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={toggleBottomCollapsed}
          className="rounded border border-white/10 bg-black/30 px-2 py-1 text-xs text-white/80 hover:bg-black/40"
        >
          {bottomCollapsed ? "Expand" : "Collapse"}
        </button>
      </div>
      {bottomCollapsed ? null : (
        <div className="h-[calc(100%-40px)] overflow-auto p-3">
          {activeBottomTab === "Backtest" ? (
            <BacktestPanel />
          ) : (
            <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm text-white/80">
              {activeBottomTab} (MVP placeholder)
            </div>
          )}
        </div>
      )}
    </div>
  );
}
