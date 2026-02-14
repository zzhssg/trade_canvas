import { useMemo } from "react";

import { apiJson } from "../lib/api";
import { HealthLampBadge, type HealthLampTone, type HealthLampView, formatDuration } from "./HealthLampBadge";
import { useHealthLampPolling } from "./useHealthLampPolling";

const KLINE_HEALTH_REFRESH_IDLE_MS = 5_000;
const KLINE_HEALTH_REFRESH_ACTIVE_MS = 2_000;

export type KlineHealthTone = HealthLampTone;

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
  lag_seconds: number | null;
  missing_seconds: number | null;
  missing_candles: number | null;
  backfill: BackfillStatus;
};

function buildView(payload: MarketHealthPayload | null): HealthLampView<KlineHealthTone> {
  if (!payload) return { tone: "gray", label: "K线未知", detail: "健康接口不可用" };
  const missingText = `缺 ${formatDuration(payload.missing_seconds ?? payload.lag_seconds)}`;
  if (payload.status === "green") return { tone: "green", label: "最新", detail: "数据已追平最新闭合K线" };
  if (payload.status === "yellow") {
    const pct = payload.backfill.progress_pct;
    const progress = pct == null || !Number.isFinite(pct) ? "回补中" : `回补 ${Math.round(pct)}%`;
    return { tone: "yellow", label: `${progress} · ${missingText}`, detail: payload.status_reason };
  }
  if (payload.status === "red") return { tone: "red", label: `延迟 · ${missingText}`, detail: payload.status_reason };
  return { tone: "gray", label: "K线未知", detail: payload.status_reason };
}

const toneOf = (payload: MarketHealthPayload | null, nextError: string | null): KlineHealthTone =>
  nextError != null ? "gray" : payload?.status ?? "gray";

const normalizeError = (cause: unknown): string => {
  const raw = cause instanceof Error ? cause.message : "load_failed";
  return raw.includes("not_found") ? "后端未开启 K 线健康接口（TRADE_CANVAS_ENABLE_KLINE_HEALTH_V2=1）" : raw;
};

const fetchMarketHealth = (nextSeriesId: string): Promise<MarketHealthPayload> =>
  apiJson<MarketHealthPayload>(`/api/market/health?series_id=${encodeURIComponent(nextSeriesId)}`);

const isFastTone = (tone: KlineHealthTone): boolean => tone === "yellow" || tone === "red";

export function LiveKlineLamp({ seriesId }: { seriesId: string }) {
  const { payload, error } = useHealthLampPolling<MarketHealthPayload, KlineHealthTone>({
    seriesId,
    fetcher: fetchMarketHealth,
    toneOf,
    normalizeError,
    isFastTone,
    delays: {
      fastMs: KLINE_HEALTH_REFRESH_ACTIVE_MS,
      idleMs: KLINE_HEALTH_REFRESH_IDLE_MS
    }
  });
  const view = useMemo(() => {
    if (error) return { tone: "gray" as KlineHealthTone, label: "K线未知", detail: error };
    return buildView(payload);
  }, [error, payload]);

  return <HealthLampBadge view={view} testId="kline-health-lamp" statusAttrName="data-kline-status" />;
}
