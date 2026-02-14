import { useMemo } from "react";

import { apiJson } from "../lib/api";
import { HealthLampBadge, type HealthLampTone, type HealthLampView, formatDuration } from "./HealthLampBadge";
import { useHealthLampPolling } from "./useHealthLampPolling";

const FACTOR_HEALTH_REFRESH_IDLE_MS = 5_000;
const FACTOR_HEALTH_REFRESH_ACTIVE_MS = 2_000;

type FactorDrawHealthTone = HealthLampTone;

type FactorDrawHealthPayload = {
  status: FactorDrawHealthTone;
  status_reason: string;
  store_head_time: number | null;
  factor_head_time: number | null;
  overlay_head_time: number | null;
  factor_delay_seconds: number | null;
  overlay_delay_seconds: number | null;
};

function formatComponentLag(headTime: number | null, delaySeconds: number | null): string {
  if (headTime == null) return "缺失";
  if (delaySeconds == null) return "未知";
  if (delaySeconds <= 0) return "最新";
  return `延迟 ${formatDuration(delaySeconds)}`;
}

function buildView(payload: FactorDrawHealthPayload | null): HealthLampView<FactorDrawHealthTone> {
  if (!payload) return { tone: "gray", label: "因子未知", detail: "健康接口不可用" };
  if (payload.status === "green") {
    return {
      tone: "green",
      label: "因子/绘图 最新",
      detail: "因子与绘图已追平最新K线"
    };
  }
  const factorLag = formatComponentLag(payload.factor_head_time, payload.factor_delay_seconds);
  const overlayLag = formatComponentLag(payload.overlay_head_time, payload.overlay_delay_seconds);
  const detail = `${payload.status_reason} · store=${payload.store_head_time ?? "null"} · factor=${payload.factor_head_time ?? "null"} · overlay=${payload.overlay_head_time ?? "null"}`;
  if (payload.status === "gray") return { tone: "gray", label: "因子未知", detail };
  return {
    tone: payload.status,
    label: `因子 ${factorLag} · 绘图 ${overlayLag}`,
    detail
  };
}

const toneOf = (payload: FactorDrawHealthPayload | null, error: string | null): FactorDrawHealthTone =>
  error != null ? "gray" : payload?.status ?? "gray";
const normalizeError = (cause: unknown): string => {
  const raw = cause instanceof Error ? cause.message : "load_failed";
  return raw.includes("not_found") ? "后端未提供因子/绘图健康接口" : raw;
};
const fetchFactorHealth = (seriesId: string): Promise<FactorDrawHealthPayload> =>
  apiJson<FactorDrawHealthPayload>(`/api/factor/health?series_id=${encodeURIComponent(seriesId)}`);

export function FactorDrawHealthLamp({ seriesId }: { seriesId: string }) {
  const { payload, error } = useHealthLampPolling<FactorDrawHealthPayload, FactorDrawHealthTone>({
    seriesId,
    fetcher: fetchFactorHealth,
    toneOf,
    normalizeError,
    delays: {
      fastMs: FACTOR_HEALTH_REFRESH_ACTIVE_MS,
      idleMs: FACTOR_HEALTH_REFRESH_IDLE_MS
    }
  });
  const view = useMemo(() => {
    if (error) return { tone: "gray" as FactorDrawHealthTone, label: "因子未知", detail: error };
    return buildView(payload);
  }, [error, payload]);

  return <HealthLampBadge view={view} testId="factor-draw-health-lamp" statusAttrName="data-factor-draw-status" />;
}
