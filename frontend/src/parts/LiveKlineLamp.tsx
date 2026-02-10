import { useEffect, useMemo, useState } from "react";

import { apiJson } from "../lib/api";

const KLINE_HEALTH_REFRESH_IDLE_MS = 10_000;
const KLINE_HEALTH_REFRESH_ACTIVE_MS = 3_000;

export type KlineHealthTone = "green" | "yellow" | "red" | "gray";

type BackfillStatus = {
  state: string;
  progress_pct: number | null;
  started_at: number | null;
  updated_at: number | null;
  reason: string | null;
  note: string | null;
  error: string | null;
  recent: boolean;
};

type MarketHealthPayload = {
  status: KlineHealthTone;
  status_reason: string;
  missing_seconds: number | null;
  missing_candles: number | null;
  backfill: BackfillStatus;
};

type LampView = {
  tone: KlineHealthTone;
  label: string;
  detail: string;
};

function formatDuration(seconds: number | null): string {
  if (seconds == null || !Number.isFinite(seconds)) return "未知";
  if (seconds <= 0) return "0m";
  const totalMinutes = Math.max(1, Math.ceil(seconds / 60));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours <= 0) return `${totalMinutes}m`;
  if (minutes <= 0) return `${hours}h`;
  return `${hours}h${minutes}m`;
}

function buildView(payload: MarketHealthPayload | null): LampView {
  if (!payload) return { tone: "gray", label: "K线未知", detail: "健康接口不可用" };
  const missingText = `缺 ${formatDuration(payload.missing_seconds)}`;
  if (payload.status === "green") return { tone: "green", label: "最新", detail: "数据已追平最新闭合K线" };
  if (payload.status === "yellow") {
    const pct = payload.backfill.progress_pct;
    const progress = pct == null || !Number.isFinite(pct) ? "回补中" : `回补 ${Math.round(pct)}%`;
    return { tone: "yellow", label: `${progress} · ${missingText}`, detail: payload.status_reason };
  }
  if (payload.status === "red") return { tone: "red", label: `延迟 · ${missingText}`, detail: payload.status_reason };
  return { tone: "gray", label: "K线未知", detail: payload.status_reason };
}

export function LiveKlineLamp({ seriesId }: { seriesId: string }) {
  const [payload, setPayload] = useState<MarketHealthPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const view = useMemo(() => {
    if (error) return { tone: "gray" as KlineHealthTone, label: "K线未知", detail: error };
    return buildView(payload);
  }, [error, payload]);

  useEffect(() => {
    let cancelled = false;
    let timer: number | null = null;

    const scheduleNext = (status: KlineHealthTone | null) => {
      const waitMs = status === "yellow" ? KLINE_HEALTH_REFRESH_ACTIVE_MS : KLINE_HEALTH_REFRESH_IDLE_MS;
      timer = window.setTimeout(() => {
        void load();
      }, waitMs);
    };

    const load = async () => {
      try {
        const next = await apiJson<MarketHealthPayload>(`/api/market/health?series_id=${encodeURIComponent(seriesId)}`);
        if (cancelled) return;
        setPayload(next);
        setError(null);
        scheduleNext(next.status);
      } catch (e: unknown) {
        if (cancelled) return;
        const rawMsg = e instanceof Error ? e.message : "load_failed";
        const msg = rawMsg.includes("not_found")
          ? "后端未开启 K 线健康接口（TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2=1）"
          : rawMsg;
        setError(msg);
        setPayload(null);
        scheduleNext(null);
      }
    };

    void load();
    return () => {
      cancelled = true;
      if (timer != null) window.clearTimeout(timer);
    };
  }, [seriesId]);

  return (
    <div
      className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-black/25 px-2 py-1 font-mono text-[11px]"
      title={view.detail}
      data-testid="kline-health-lamp"
      data-kline-status={view.tone}
    >
      <span
        className={[
          "inline-block h-2 w-2 rounded-full",
          view.tone === "green"
            ? "bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
            : view.tone === "yellow"
              ? "bg-amber-300 shadow-[0_0_8px_rgba(251,191,36,0.6)]"
              : view.tone === "red"
                ? "bg-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.55)]"
                : "bg-gray-400 shadow-[0_0_6px_rgba(148,163,184,0.45)]"
        ].join(" ")}
      />
      <span
        className={[
          view.tone === "green"
            ? "text-emerald-300"
            : view.tone === "yellow"
              ? "text-amber-200"
              : view.tone === "red"
                ? "text-rose-300"
                : "text-white/60"
        ].join(" ")}
      >
        {view.label}
      </span>
    </div>
  );
}
