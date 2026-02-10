import { Link, useLocation } from "react-router-dom";

import { useUiStore } from "../state/uiStore";

const ENABLE_TRADE_ORACLE_PAGE = String(import.meta.env.VITE_ENABLE_TRADE_ORACLE_PAGE ?? "1") === "1";

export function TopBar() {
  const location = useLocation();
  const { market, symbol, timeframe } = useUiStore();

  return (
    <div className="flex h-14 items-center justify-between gap-3 border-b border-white/10 bg-white/5 px-3 backdrop-blur">
      <div className="flex items-center gap-2">
        <div className="text-sm font-semibold tracking-wide text-white/90">Trade Canvas</div>
        <div className="ml-3 hidden items-center gap-2 text-xs text-white/50 md:flex">
          <span className="rounded-md border border-white/10 bg-black/25 px-2 py-1 font-mono">
            {market}:{symbol}:{timeframe}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-xs text-white/70">
        <NavLink to="/live" active={location.pathname === "/live"} label="Live" />
        {ENABLE_TRADE_ORACLE_PAGE ? <NavLink to="/oracle" active={location.pathname === "/oracle"} label="Oracle" /> : null}
        <NavLink to="/settings" active={location.pathname === "/settings"} label="Settings" />
      </div>
    </div>
  );
}

function NavLink({ to, label, active }: { to: string; label: string; active: boolean }) {
  return (
    <Link
      to={to}
      className={[
        "rounded px-2 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
        active ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white"
      ].join(" ")}
    >
      {label}
    </Link>
  );
}
