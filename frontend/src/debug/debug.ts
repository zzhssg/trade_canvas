import { useDebugLogStore } from "../state/debugLogStore";

export type DebugPipe = "read" | "write";
export type DebugLevel = "info" | "warn" | "error";

export type DebugEvent = {
  ts_ms: number;
  source: "frontend" | "backend";
  pipe: DebugPipe;
  event: string;
  series_id?: string | null;
  level: DebugLevel;
  message: string;
  data?: Record<string, unknown>;
};

// Dev default ON (prod default OFF).
export const ENABLE_DEBUG_TOOL =
  String(import.meta.env.VITE_ENABLE_DEBUG_TOOL ?? (import.meta.env.DEV ? "1" : "0")) === "1";

export function logDebugEvent(
  e: Omit<DebugEvent, "ts_ms" | "source"> & { ts_ms?: number; source?: "frontend" | "backend" }
) {
  if (!ENABLE_DEBUG_TOOL) return;
  const ts_ms = typeof e.ts_ms === "number" && Number.isFinite(e.ts_ms) ? e.ts_ms : Date.now();
  const source = e.source ?? "frontend";
  useDebugLogStore.getState().append({
    ts_ms,
    source,
    pipe: e.pipe,
    event: e.event,
    series_id: e.series_id,
    level: e.level,
    message: e.message,
    data: e.data
  });
}
