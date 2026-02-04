export const ENABLE_DEBUG_TOOL = import.meta.env.VITE_ENABLE_DEBUG_TOOL === "1";

export type DebugEvent = {
  ts_ms: number;
  source: "frontend" | "backend";
  pipe: "read" | "write";
  event: string;
  series_id: string | null;
  level: "info" | "warn" | "error";
  message: string;
  data?: Record<string, unknown> | null;
};

const MAX_EVENTS = 2000;
const events: DebugEvent[] = [];

export const TC_DEBUG_EVENT_NAME = "tc:debug_event";

export function logDebugEvent(input: Omit<DebugEvent, "ts_ms" | "source"> & { ts_ms?: number; source?: DebugEvent["source"] }) {
  if (!ENABLE_DEBUG_TOOL) return;
  const e: DebugEvent = {
    ts_ms: input.ts_ms ?? Date.now(),
    source: input.source ?? "frontend",
    pipe: input.pipe,
    event: input.event,
    series_id: input.series_id ?? null,
    level: input.level,
    message: input.message,
    data: input.data ?? null
  };

  events.push(e);
  if (events.length > MAX_EVENTS) events.splice(0, events.length - MAX_EVENTS);

  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(TC_DEBUG_EVENT_NAME, { detail: e }));
  }
}

export function getDebugSnapshot(): DebugEvent[] {
  return [...events];
}
