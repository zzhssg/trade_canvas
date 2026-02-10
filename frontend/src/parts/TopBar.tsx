import { Link, useLocation } from "react-router-dom";
import { useEffect, useMemo, useState } from "react";

import { apiJson } from "../lib/api";
import { useUiStore } from "../state/uiStore";

const ENABLE_TRADE_ORACLE_PAGE = String(import.meta.env.VITE_ENABLE_TRADE_ORACLE_PAGE ?? "1") === "1";
const KLINE_HEALTH_REFRESH_MS = 10_000;

type BaseBucketCompleteness = {
  missing_minutes: number;
};

type SeriesHealthPayload = {
  lag_seconds: number | null;
  gap_count: number;
  base_bucket_completeness: BaseBucketCompleteness[];
};

type KlineStatusView = {
  tone: "green" | "red" | "gray";
  label: string;
  detail: string;
};

function timeframeToSeconds(timeframe: string): number {
  const m = String(timeframe).trim().match(/^(\d+)([mhdw])$/i);
  if (!m) return 60;
  const n = Number(m[1]);
  if (!Number.isFinite(n) || n <= 0) return 60;
  const unit = m[2]!.toLowerCase();
  if (unit === "m") return n * 60;
  if (unit === "h") return n * 3600;
  if (unit === "d") return n * 86400;
  if (unit === "w") return n * 604800;
  return 60;
}

function buildKlineStatusView({
  timeframe,
  payload
}: {
  timeframe: string;
  payload: SeriesHealthPayload | null;
}): KlineStatusView {
  if (!payload) {
    return { tone: "gray", label: "K线未知", detail: "状态接口不可用" };
  }
  const tfSeconds = timeframeToSeconds(timeframe);
  const lag = payload.lag_seconds ?? Number.POSITIVE_INFINITY;
  const lagMinutes = Number.isFinite(lag) ? Math.max(0, Math.floor(lag / 60)) : null;
  const baseBucketMissing = payload.base_bucket_completeness.some((b) => Number(b.missing_minutes) > 0);
  const hasGap = Number(payload.gap_count) > 0 || baseBucketMissing;
  const freshEnough = Number.isFinite(lag) && lag <= tfSeconds * 2;
  const healthy = freshEnough && !hasGap;
  if (healthy) {
    return {
      tone: "green",
      label: "K线正常",
      detail: lagMinutes == null ? "实时" : `实时 · 延迟 ${lagMinutes}m`
    };
  }
  return {
    tone: "red",
    label: "K线异常",
    detail: lagMinutes == null ? "滞后/缺口" : `延迟 ${lagMinutes}m · gap ${payload.gap_count}`
  };
}

export function TopBar() {
  const location = useLocation();
  const { exchange, market, symbol, timeframe } = useUiStore();
  const [seriesHealth, setSeriesHealth] = useState<SeriesHealthPayload | null>(null);
  const seriesId = `${exchange}:${market}:${symbol}:${timeframe}`;

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const payload = await apiJson<SeriesHealthPayload>(
          `/api/market/debug/series_health?series_id=${encodeURIComponent(seriesId)}&max_recent_gaps=1&recent_base_buckets=2`
        );
        if (cancelled) return;
        setSeriesHealth(payload);
      } catch {
        if (cancelled) return;
        setSeriesHealth(null);
      }
    };
    void load();
    const timer = window.setInterval(() => void load(), KLINE_HEALTH_REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [seriesId]);

  const klineStatus = useMemo(
    () => buildKlineStatusView({ timeframe, payload: seriesHealth }),
    [timeframe, seriesHealth]
  );

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
        <div
          className="ml-3 flex items-center gap-1.5 rounded-md border border-white/10 bg-black/25 px-2 py-1 font-mono text-[11px]"
          title={klineStatus.detail}
        >
          <span
            className={[
              "inline-block h-2 w-2 rounded-full",
              klineStatus.tone === "green"
                ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
                : klineStatus.tone === "red"
                  ? "bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.55)]"
                  : "bg-gray-400 shadow-[0_0_6px_rgba(148,163,184,0.45)]"
            ].join(" ")}
          />
          <span
            className={[
              klineStatus.tone === "green"
                ? "text-emerald-300"
                : klineStatus.tone === "red"
                  ? "text-rose-300"
                  : "text-white/60"
            ].join(" ")}
          >
            {klineStatus.label}
          </span>
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
        "rounded px-2 py-1 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
        active ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white"
      ].join(" ")}
    >
      {label}
    </Link>
  );
}
