import { useUiStore } from "../state/uiStore";

const TABS = ["Market", "Strategy", "Indicators", "Replay"] as const;

export function Sidebar() {
  const { activeSidebarTab, setActiveSidebarTab, sidebarCollapsed, toggleSidebarCollapsed } = useUiStore();

  return (
    <div className="h-full overflow-hidden border-r border-white/10 bg-white/5">
      <div className="relative flex h-14 items-center border-b border-white/10 px-2">
        <div className="w-full text-center text-xs font-semibold text-white/80">{sidebarCollapsed ? "TC" : "Panels"}</div>
        <button
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded border border-white/10 bg-black/30 px-2 py-1 text-xs text-white/80 hover:bg-black/40"
          onClick={toggleSidebarCollapsed}
          type="button"
        >
          {sidebarCollapsed ? ">" : "<"}
        </button>
      </div>
      {sidebarCollapsed ? (
        <div className="flex h-[calc(100%-56px)] flex-col items-center gap-2 overflow-auto p-2">
          {TABS.map((tab) => (
            <button
              key={tab}
              type="button"
              title={tab}
              onClick={() => setActiveSidebarTab(tab)}
              className={[
                "w-full rounded border border-white/10 bg-black/20 py-2 text-[11px] font-semibold text-white/80",
                activeSidebarTab === tab ? "bg-white/15" : "hover:bg-white/10"
              ].join(" ")}
            >
              {tab[0]}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex h-[calc(100%-56px)] flex-col gap-3 overflow-auto p-3">
          <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-black/20 p-1">
            {TABS.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveSidebarTab(tab)}
                className={[
                  "flex-1 rounded px-2 py-1 text-[11px]",
                  activeSidebarTab === tab ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
                ].join(" ")}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeSidebarTab === "Market" ? (
            <Section title="Market / Subscriptions">
              <div className="text-xs text-white/60">WS status: mock</div>
              <div className="text-xs text-white/60">closed candle source: planned</div>
            </Section>
          ) : null}
          {activeSidebarTab === "Strategy" ? (
            <Section title="Strategy">
              <div className="text-xs text-white/60">active strategy: (todo)</div>
            </Section>
          ) : null}
          {activeSidebarTab === "Indicators" ? (
            <Section title="Indicators">
              <div className="text-xs text-white/60">pivot / bi / anchor / zhongshu (todo)</div>
            </Section>
          ) : null}
          {activeSidebarTab === "Replay" ? (
            <Section title="Replay">
              <div className="text-xs text-white/60">load replay package (todo)</div>
            </Section>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/60">{title}</div>
      {children}
    </div>
  );
}
