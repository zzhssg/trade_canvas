import { useEffect } from "react";

import { ChartView } from "../widgets/ChartView";
import { useCenterScrollLock } from "../layout/centerScrollLock";
import { FactorPanel } from "./FactorPanel";
import { useReplayStore } from "../state/replayStore";
import { useUiStore } from "../state/uiStore";
import { useTopMarkets } from "../services/useTopMarkets";

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;
const ENABLE_REPLAY_V1 = String(import.meta.env.VITE_ENABLE_REPLAY_V1 ?? "1") === "1";

export function ChartPanel({ mode }: { mode: "live" | "replay" }) {
  const { market, setMarket, symbol, setSymbol, timeframe, setTimeframe } = useUiStore();
  const replayMode = useReplayStore((s) => s.mode);
  const setReplayMode = useReplayStore((s) => s.setMode);
  const scrollLock = useCenterScrollLock();
  const topMarkets = useTopMarkets({ market, quoteAsset: "USDT", limit: 20, stream: false });
  const symbolOptions = Array.from(new Set([symbol, ...(topMarkets.data?.items ?? []).map((it) => it.symbol)]));
  const timeframeOptions = (TIMEFRAMES as readonly string[]).includes(timeframe)
    ? TIMEFRAMES
    : ([...TIMEFRAMES, timeframe] as const);

  useEffect(() => {
    setReplayMode(mode);
  }, [mode, setReplayMode]);

  return (
    <div className="h-full w-full p-3">
      <div className="flex h-full w-full flex-col gap-3">
        <div className="flex items-center justify-between gap-3 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/70">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <div className="flex items-center gap-1 rounded-md border border-white/10 bg-black/20 p-1">
              <button
                type="button"
                data-testid="market-spot"
                aria-pressed={market === "spot"}
                onClick={() => setMarket("spot")}
                className={[
                  "rounded px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                  market === "spot"
                    ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-500/20"
                    : "text-white/70 hover:bg-white/10"
                ].join(" ")}
              >
                Spot
              </button>
              <button
                type="button"
                data-testid="market-futures"
                aria-pressed={market === "futures"}
                onClick={() => setMarket("futures")}
                className={[
                  "rounded px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                  market === "futures"
                    ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-500/20"
                    : "text-white/70 hover:bg-white/10"
                ].join(" ")}
              >
                Futures
              </button>
            </div>

            <div className="relative">
              <select
                className="min-w-[148px] max-w-[240px] appearance-none rounded-md border border-white/10 bg-black/40 px-2 py-1 pr-7 font-mono text-[11px] text-white/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
                data-testid="symbol-select"
                value={symbol}
                onChange={(e) => setSymbol(e.target.value)}
                title="Symbol"
              >
                {symbolOptions.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
              <div className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-white/45">
                <svg width="12" height="12" viewBox="0 0 20 20" fill="none" aria-hidden="true">
                  <path
                    d="M6 8l4 4 4-4"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>

            <div className="tc-scrollbar-none flex max-w-full items-center gap-1 overflow-x-auto py-0.5">
              {timeframeOptions.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  data-testid={`timeframe-tag-${tf}`}
                  aria-pressed={timeframe === tf}
                  onClick={() => setTimeframe(tf)}
                  className={[
                    "shrink-0 rounded-md border px-2 py-1 font-mono text-[11px] leading-none focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                    timeframe === tf
                      ? "border-sky-500/40 bg-gradient-to-b from-sky-500/20 to-sky-500/10 text-sky-100 shadow-[0_0_0_1px_rgba(56,189,248,0.12)_inset]"
                      : "border-white/10 bg-black/20 text-white/70 hover:bg-white/10"
                  ].join(" ")}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              data-testid="mode-toggle"
              disabled={!ENABLE_REPLAY_V1}
              onClick={() => {
                if (!ENABLE_REPLAY_V1) return;
                setReplayMode(replayMode === "live" ? "replay" : "live");
              }}
              className={[
                "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                ENABLE_REPLAY_V1
                  ? "border-white/10 bg-black/25 text-white/80 hover:bg-white/10"
                  : "border-white/5 bg-black/20 text-white/30"
              ].join(" ")}
              title={ENABLE_REPLAY_V1 ? "切换实盘/复盘" : "Replay disabled (VITE_ENABLE_REPLAY_V1 != 1)"}
            >
              mode:{replayMode}
            </button>
          </div>
        </div>
        <FactorPanel />
        <div
          className="relative z-0 min-h-0 flex-1 overflow-hidden rounded-lg border border-white/10 bg-black/20"
          data-chart-area="true"
          // Wheel/scroll contract:
          // hovering chart locks middle-scroll, so wheel zooms the chart instead of scrolling the page.
          onMouseEnter={() => scrollLock?.lock()}
          onMouseLeave={() => scrollLock?.unlock()}
        >
          <ChartView />
        </div>
      </div>
    </div>
  );
}
