import { useUiStore } from "../state/uiStore";
import { useEffect, useMemo, useState } from "react";
import { useTopMarkets } from "../services/useTopMarkets";
import { ENABLE_DEBUG_TOOL } from "../debug/debug";
import { DebugPanel } from "./DebugPanel";
import { ReplayPanel } from "./ReplayPanel";

const ALL_TABS = ["Market", "Strategy", "Indicators", "Replay", "Debug"] as const;
type SidebarTabKey = (typeof ALL_TABS)[number];

export function Sidebar({ side = "left" }: { side?: "left" | "right" }) {
  const { activeSidebarTab, setActiveSidebarTab, sidebarCollapsed, toggleSidebarCollapsed } = useUiStore();
  const borderSide = side === "left" ? "border-r" : "border-l";
  const expandGlyph = side === "left" ? ">" : "<";
  const collapseGlyph = side === "left" ? "<" : ">";
  const togglePos = side === "left" ? "right-2" : "left-2";

  const tabs = useMemo(() => {
    const out = [...ALL_TABS] as SidebarTabKey[];
    return ENABLE_DEBUG_TOOL ? out : (out.filter((t) => t !== "Debug") as SidebarTabKey[]);
  }, []);

  useEffect(() => {
    if (tabs.includes(activeSidebarTab as SidebarTabKey)) return;
    setActiveSidebarTab(tabs[0]);
  }, [activeSidebarTab, setActiveSidebarTab, tabs]);

  return (
    <div className={["h-full overflow-hidden border-white/10 bg-white/[0.045] backdrop-blur", borderSide].join(" ")}>
      <div className="relative flex h-14 items-center border-b border-white/10 px-2">
        <div className="w-full text-center text-xs font-semibold tracking-wide text-white/80">
          {sidebarCollapsed ? "TC" : "Panels"}
        </div>
        <button
          className={[
            "absolute top-1/2 -translate-y-1/2 rounded-md border border-white/10 bg-black/25 px-2 py-1 text-xs text-white/80 hover:bg-black/35 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
            togglePos
          ].join(" ")}
          onClick={toggleSidebarCollapsed}
          type="button"
          aria-label={sidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {sidebarCollapsed ? expandGlyph : collapseGlyph}
        </button>
      </div>
      {sidebarCollapsed ? (
        <div className="flex h-[calc(100%-56px)] flex-col items-center gap-2 overflow-auto p-2">
          {tabs.map((tab) => (
            <button
              key={tab}
              type="button"
              title={tab}
              onClick={() => setActiveSidebarTab(tab)}
              data-testid={`sidebar-tab-${tab}`}
              className={[
                "w-full rounded-md border border-white/10 bg-black/20 py-2 text-[11px] font-semibold text-white/80 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                activeSidebarTab === tab ? "bg-white/15" : "hover:bg-white/10"
              ].join(" ")}
            >
              {tab[0]}
            </button>
          ))}
        </div>
      ) : (
        <div className="flex h-[calc(100%-56px)] flex-col gap-3 overflow-auto p-3">
          <div className="flex items-center gap-1 rounded-xl border border-white/10 bg-black/20 p-1">
            {tabs.map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setActiveSidebarTab(tab)}
              data-testid={`sidebar-tab-${tab}`}
                className={[
                  "flex-1 rounded-lg px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                  activeSidebarTab === tab
                    ? "bg-white/15 text-white"
                    : "text-white/70 hover:bg-white/10 hover:text-white/85"
                ].join(" ")}
              >
                {tab}
              </button>
            ))}
          </div>

          {activeSidebarTab === "Market" ? (
            <Section title="Market / Subscriptions">
              <MarketPanel />
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
              <ReplayPanel />
            </Section>
          ) : null}
          {activeSidebarTab === "Debug" ? (
            <Section title="Debug / Logs">
              <DebugPanel />
            </Section>
          ) : null}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-white/10 bg-black/20 p-3 shadow-[0_0_0_1px_rgba(255,255,255,0.03)_inset]">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-white/60">{title}</div>
      {children}
    </div>
  );
}

function MarketPanel() {
  const { market, setMarket, symbol, setSymbol } = useUiStore();
  const [query, setQuery] = useState("");
  const spot = useTopMarkets({ market: "spot", quoteAsset: "USDT", limit: 20, intervalS: 2 });
  const futures = useTopMarkets({ market: "futures", quoteAsset: "USDT", limit: 20, intervalS: 2 });
  const active = market === "spot" ? spot : futures;
  const activeItems = active.data?.items ?? [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return activeItems;
    return activeItems.filter((m) => String(m.symbol).toLowerCase().includes(q) || String(m.symbol_id).toLowerCase().includes(q));
  }, [activeItems, query]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 rounded-md border border-white/10 bg-black/20 p-1">
          <TabButton active={market === "spot"} onClick={() => setMarket("spot")}>
            Spot
          </TabButton>
          <TabButton active={market === "futures"} onClick={() => setMarket("futures")}>
            Futures
          </TabButton>
        </div>
        <button
          type="button"
          className="ml-auto rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
          onClick={() => void active.refresh()}
        >
          Refresh
        </button>
      </div>

      <div className="flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter (e.g. BTC / BTCUSDT)"
          className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-white/80 placeholder:text-white/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
        />
      </div>

      <div className="text-[11px] text-white/50">
        {active.isLoading ? "Loading Binance top 20..." : null}
        {active.isError ? `Load failed: ${active.error instanceof Error ? active.error.message : String(active.error)}` : null}
        {active.isSuccess ? `Binance 24h quoteVolume (USDT pairs) · stream: ${active.sseState}` : null}
      </div>

      <div className="max-h-[52vh] overflow-auto rounded-xl border border-white/10 bg-black/10 shadow-[0_0_0_1px_rgba(255,255,255,0.02)_inset]">
        {filtered.length === 0 ? (
          <div className="p-2 text-[11px] text-white/50">No matches.</div>
        ) : (
          <div className="divide-y divide-white/10">
            {filtered.map((m, idx) => (
              <button
                key={`${m.market}:${m.symbol_id}`}
                type="button"
                onClick={() => {
                  if (m.market === "spot" || m.market === "futures") setMarket(m.market);
                  setSymbol(m.symbol);
                }}
                className={[
                  "flex w-full items-center gap-2 px-2 py-1.5 text-left text-[11px] hover:bg-white/5 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                  market === m.market && symbol === m.symbol ? "bg-white/10" : ""
                ].join(" ")}
              >
                <div className="w-6 shrink-0 text-white/35">{String(idx + 1).padStart(2, "0")}</div>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-mono text-white/85">{m.symbol}</div>
                  <div className="truncate font-mono text-white/35">{m.symbol_id}</div>
                </div>
                <div className="shrink-0 text-right font-mono">
                  <div className="text-white/80">{m.last_price == null ? "--" : formatPrice(m.last_price)}</div>
                  <div className="text-white/45">{m.quote_volume == null ? "--" : formatCompact(m.quote_volume)}</div>
                </div>
                <div
                  className={[
                    "w-14 shrink-0 text-right font-mono",
                    m.price_change_percent == null
                      ? "text-white/45"
                      : m.price_change_percent >= 0
                        ? "text-green-400"
                        : "text-red-400"
                  ].join(" ")}
                >
                  {m.price_change_percent == null ? "--" : `${m.price_change_percent.toFixed(2)}%`}
                </div>
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="text-[11px] text-white/40">Market list: Binance 24h · K线：backend HTTP+WS</div>
    </div>
  );
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
        active ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
      ].join(" ")}
    >
      {children}
    </button>
  );
}

function formatCompact(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `${(value / 1e3).toFixed(2)}K`;
  return value.toFixed(2);
}

function formatPrice(value: number) {
  if (value === 0) return "0";
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  if (abs >= 1) return value.toLocaleString(undefined, { maximumFractionDigits: 4 });
  return value.toLocaleString(undefined, { maximumFractionDigits: 8 });
}
