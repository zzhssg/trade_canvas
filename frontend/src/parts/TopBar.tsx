import { Link, useLocation } from "react-router-dom";

import { useUiStore } from "../state/uiStore";

const SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT"];
const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

export function TopBar() {
  const location = useLocation();
  const { symbol, timeframe, setSymbol, setTimeframe } = useUiStore();

  return (
    <div className="flex h-14 items-center justify-between gap-3 border-b border-white/10 bg-white/5 px-3">
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold">Trade Canvas</div>
        <div className="ml-3 flex items-center gap-2 text-xs">
          <select
            className="rounded border border-white/10 bg-black/40 px-2 py-1"
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
          >
            {SYMBOLS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-white/10 bg-black/40 px-2 py-1"
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
          >
            {TIMEFRAMES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-white/70">
        <NavLink to="/live" active={location.pathname === "/live"} label="Live" />
        <NavLink to="/replay" active={location.pathname === "/replay"} label="Replay" />
        <NavLink to="/settings" active={location.pathname === "/settings"} label="Settings" />
        <div className="ml-3 rounded border border-white/10 bg-black/30 px-2 py-1 font-mono">
          feed: mock
        </div>
      </div>
    </div>
  );
}

function NavLink({ to, label, active }: { to: string; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={[
        "rounded px-2 py-1",
        active ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white"
      ].join(" ")}
    >
      {label}
    </Link>
  );
}

