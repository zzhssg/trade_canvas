import { ChartView } from "../widgets/ChartView";
import { FactorPanel } from "./FactorPanel";
import { useUiStore } from "../state/uiStore";

const DEFAULT_SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"] as const;
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"] as const;

export function ChartPanel({ mode }: { mode: "live" | "replay" }) {
  const { market, setMarket, symbol, setSymbol, timeframe, setTimeframe } = useUiStore();
  const symbolOptions = Array.from(new Set([symbol, ...DEFAULT_SYMBOLS]));
  const timeframeOptions = (TIMEFRAMES as readonly string[]).includes(timeframe)
    ? TIMEFRAMES
    : ([...TIMEFRAMES, timeframe] as const);

  return (
    <div className="h-full w-full p-3">
      <div className="flex h-full w-full flex-col gap-3">
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/70">
          <div className="flex min-w-0 flex-wrap items-center gap-2">
            <span className="rounded bg-white/10 px-2 py-1 font-mono">mode:{mode}</span>

            <div className="flex items-center gap-1 rounded border border-white/10 bg-black/20 p-1">
              <button
                type="button"
                data-testid="market-spot"
                aria-pressed={market === "spot"}
                onClick={() => setMarket("spot")}
                className={[
                  "rounded px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                  market === "spot" ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
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
                  market === "futures" ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10"
                ].join(" ")}
              >
                Futures
              </button>
            </div>

            <select
              className="min-w-[140px] max-w-[220px] rounded border border-white/10 bg-black/40 px-2 py-1 font-mono text-[11px] text-white/90 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
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

            <div className="flex flex-wrap items-center gap-1">
              {timeframeOptions.map((tf) => (
                <button
                  key={tf}
                  type="button"
                  data-testid={`timeframe-tag-${tf}`}
                  aria-pressed={timeframe === tf}
                  onClick={() => setTimeframe(tf)}
                  className={[
                    "rounded border px-2 py-1 font-mono text-[11px] leading-none focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                    timeframe === tf
                      ? "border-sky-500/40 bg-sky-500/15 text-sky-200"
                      : "border-white/10 bg-black/20 text-white/70 hover:bg-white/10"
                  ].join(" ")}
                >
                  {tf}
                </button>
              ))}
            </div>
          </div>
          <div className="shrink-0 font-mono text-white/60">candle_id: —</div>
        </div>
        <FactorPanel />
        <div
          className="min-h-0 flex-1 overflow-hidden rounded-lg border border-white/10 bg-black/20"
          data-chart-area="true"
        >
          <ChartView />
        </div>
      </div>
    </div>
  );
}
