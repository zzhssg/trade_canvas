import { useEffect, useMemo, useRef, useState } from "react";

import { apiJson, apiWsBase } from "../lib/api";
import { ENABLE_DEBUG_TOOL, logDebugEvent, type DebugEvent } from "../debug/debug";
import { useDebugLogStore } from "../state/debugLogStore";
import { useUiStore } from "../state/uiStore";

type DebugWsSnapshot = { type: "debug_snapshot"; events: DebugEvent[] };
type DebugWsEvent = { type: "debug_event"; event: DebugEvent };
type SeriesHealthGap = {
  prev_time: number;
  next_time: number;
  delta_seconds: number;
  missing_candles: number;
};
type SeriesHealthBucket = {
  bucket_open_time: number;
  expected_minutes: number;
  actual_minutes: number;
  missing_minutes: number;
};
type SeriesHealth = {
  series_id: string;
  head_time: number | null;
  lag_seconds: number | null;
  candle_count: number;
  gap_count: number;
  max_gap_seconds: number | null;
  recent_gaps: SeriesHealthGap[];
  base_series_id: string;
  base_bucket_completeness: SeriesHealthBucket[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object";
}

function isDebugEvent(value: unknown): value is DebugEvent {
  if (!isRecord(value)) return false;
  if (typeof value.ts_ms !== "number" || !Number.isFinite(value.ts_ms)) return false;
  if (value.source !== "backend" && value.source !== "frontend") return false;
  if (value.pipe !== "read" && value.pipe !== "write") return false;
  if (typeof value.event !== "string" || !value.event) return false;
  if (value.level !== "info" && value.level !== "warn" && value.level !== "error") return false;
  if (typeof value.message !== "string") return false;
  return true;
}

function parseWsPayload(payload: unknown): DebugWsSnapshot | DebugWsEvent | null {
  if (!isRecord(payload)) return null;
  const type = payload.type;
  if (type === "debug_snapshot") {
    const eventsRaw = payload.events;
    if (!Array.isArray(eventsRaw)) return null;
    const events: DebugEvent[] = [];
    for (const e of eventsRaw) {
      if (!isDebugEvent(e)) return null;
      events.push(e);
    }
    return { type, events };
  }
  if (type === "debug_event") {
    if (!isDebugEvent(payload.event)) return null;
    return { type, event: payload.event };
  }
  return null;
}

function formatTs(tsMs: number): string {
  const d = new Date(tsMs);
  if (Number.isNaN(d.getTime())) return String(tsMs);
  return d.toLocaleTimeString(undefined, { hour12: false }) + "." + String(d.getMilliseconds()).padStart(3, "0");
}

export function DebugPanel() {
  const { events, filter, query, autoScroll, clear, setFilter, setQuery, toggleAutoScroll } = useDebugLogStore();
  const { exchange, market, symbol, timeframe } = useUiStore();
  const seriesId = `${exchange}:${market}:${symbol}:${timeframe}`;
  const [wsState, setWsState] = useState<"disconnected" | "connecting" | "connected">("disconnected");
  const [health, setHealth] = useState<SeriesHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState<boolean>(false);
  const [healthError, setHealthError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!ENABLE_DEBUG_TOOL) return;
    let cancelled = false;
    const run = async () => {
      setHealthLoading(true);
      setHealthError(null);
      try {
        const payload = await apiJson<SeriesHealth>(
          `/api/market/debug/series_health?series_id=${encodeURIComponent(seriesId)}&max_recent_gaps=3&recent_base_buckets=4`
        );
        if (cancelled) return;
        setHealth(payload);
      } catch (e: unknown) {
        if (cancelled) return;
        const msg = e instanceof Error ? e.message : "load failed";
        setHealthError(msg);
        setHealth(null);
      } finally {
        if (!cancelled) setHealthLoading(false);
      }
    };
    void run();
    const timer = window.setInterval(() => {
      void run();
    }, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [seriesId]);

  useEffect(() => {
    if (!ENABLE_DEBUG_TOOL) return;
    let ws: WebSocket | null = null;
    let alive = true;
    setWsState("connecting");

    try {
      ws = new WebSocket(`${apiWsBase()}/ws/debug`);
    } catch {
      setWsState("disconnected");
      return;
    }

    ws.onopen = () => {
      if (!alive) return;
      setWsState("connected");
      try {
        ws?.send(JSON.stringify({ type: "subscribe" }));
      } catch {
        // ignore
      }
    };
    ws.onclose = () => {
      if (!alive) return;
      setWsState("disconnected");
    };
    ws.onerror = () => {
      if (!alive) return;
      setWsState("disconnected");
    };
    ws.onmessage = (evt) => {
      if (!alive) return;
      if (typeof evt.data !== "string") return;
      let raw: unknown;
      try {
        raw = JSON.parse(evt.data) as unknown;
      } catch {
        return;
      }
      const parsed = parseWsPayload(raw);
      if (!parsed) return;
      if (parsed.type === "debug_snapshot") {
        for (const e of parsed.events) {
          logDebugEvent({ ...e, source: "backend" });
        }
      } else {
        logDebugEvent({ ...parsed.event, source: "backend" });
      }
    };

    return () => {
      alive = false;
      try {
        ws?.close();
      } catch {
        // ignore
      }
    };
  }, []);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return events.filter((e) => {
      if (filter !== "all" && e.pipe !== filter) return false;
      if (!q) return true;
      const hay = `${e.event} ${e.message} ${e.series_id ?? ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [events, filter, query]);

  useEffect(() => {
    if (!autoScroll) return;
    const el = listRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [autoScroll, filtered.length]);

  const copyText = useMemo(() => {
    return filtered
      .map((e) => {
        const sid = e.series_id ? ` ${e.series_id}` : "";
        return `${formatTs(e.ts_ms)} [${e.source}] [${e.pipe}] ${e.event}${sid} ${e.message}`;
      })
      .join("\n");
  }, [filtered]);

  if (!ENABLE_DEBUG_TOOL) {
    return <div className="text-xs text-white/60">Debug tool disabled (VITE_ENABLE_DEBUG_TOOL != 1)</div>;
  }

  return (
    <div className="flex flex-col gap-2" data-testid="debug-panel">
      <div className="flex flex-wrap items-center gap-2">
        <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1 font-mono text-[11px] text-white/80">
          ws:{wsState}
        </div>
        <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1 font-mono text-[11px] text-white/60">
          series:{seriesId}
        </div>
        <button
          type="button"
          className="ml-auto rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
          onClick={clear}
        >
          Clear
        </button>
        <button
          type="button"
          className="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
          onClick={() => {
            setHealthLoading(true);
            setHealthError(null);
            void apiJson<SeriesHealth>(
              `/api/market/debug/series_health?series_id=${encodeURIComponent(seriesId)}&max_recent_gaps=3&recent_base_buckets=4`
            )
              .then((payload) => setHealth(payload))
              .catch((e: unknown) => setHealthError(e instanceof Error ? e.message : "load failed"))
              .finally(() => setHealthLoading(false));
          }}
          title="Refresh series health"
        >
          Health
        </button>
        <button
          type="button"
          className="rounded-md border border-white/10 bg-black/20 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
          onClick={() => void navigator.clipboard.writeText(copyText)}
          disabled={filtered.length === 0}
          title={filtered.length === 0 ? "No logs" : "Copy filtered logs"}
        >
          Copy
        </button>
      </div>

      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1 rounded-md border border-white/10 bg-black/20 p-1">
          {(["all", "read", "write"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setFilter(k)}
              data-testid={`debug-filter-${k}`}
              className={[
                "rounded px-2 py-1 text-[11px] focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                filter === k ? "bg-white/15 text-white" : "text-white/70 hover:bg-white/10 hover:text-white/85"
              ].join(" ")}
            >
              {k}
            </button>
          ))}
        </div>

        <label className="ml-auto flex items-center gap-2 text-[11px] text-white/70">
          <input type="checkbox" checked={autoScroll} onChange={toggleAutoScroll} />
          Auto-scroll
        </label>
      </div>

      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Search (event / message / series_id)"
        className="w-full rounded-md border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-white/80 placeholder:text-white/30 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
      />

      <div className="rounded-xl border border-white/10 bg-black/10 p-2 text-[11px] text-white/75">
        {healthLoading ? (
          <div>health: loading...</div>
        ) : healthError ? (
          <div className="text-rose-300">health error: {healthError}</div>
        ) : health ? (
          <div className="flex flex-col gap-1">
            <div className="font-mono text-white/85">
              head:{health.head_time ?? "null"} lag_s:{health.lag_seconds ?? "null"} count:{health.candle_count}
            </div>
            <div className="font-mono text-white/70">
              gaps:{health.gap_count} max_gap_s:{health.max_gap_seconds ?? "null"} base:{health.base_series_id}
            </div>
            {health.recent_gaps.length > 0 ? (
              <div className="font-mono text-white/65">
                recent gaps:
                {health.recent_gaps.map((g) => (
                  <span key={`${g.prev_time}:${g.next_time}`} className="ml-2">
                    {`[${g.prev_time}->${g.next_time} miss=${g.missing_candles}]`}
                  </span>
                ))}
              </div>
            ) : null}
            {health.base_bucket_completeness.length > 0 ? (
              <div className="font-mono text-white/65">
                base buckets:
                {health.base_bucket_completeness.map((b) => (
                  <span key={b.bucket_open_time} className="ml-2">
                    {`[${b.bucket_open_time} ${b.actual_minutes}/${b.expected_minutes}]`}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        ) : (
          <div>health: no data</div>
        )}
      </div>

      <div
        ref={listRef}
        className="tc-scrollbar-none max-h-[54vh] overflow-auto rounded-xl border border-white/10 bg-black/10 shadow-[0_0_0_1px_rgba(255,255,255,0.02)_inset]"
        data-testid="debug-drawer"
      >
        {filtered.length === 0 ? (
          <div className="p-2 text-[11px] text-white/50">No logs.</div>
        ) : (
          <div className="divide-y divide-white/10">
            {filtered.map((e, idx) => (
              <div
                key={`${e.ts_ms}:${idx}`}
                className="px-2 py-1.5 text-[11px] text-white/80"
                data-testid="debug-log-row"
                data-event={e.event}
                data-pipe={e.pipe}
                data-source={e.source}
              >
                <div className="flex items-center gap-2">
                  <div className="w-[82px] shrink-0 font-mono text-white/55">{formatTs(e.ts_ms)}</div>
                  <div className="w-[62px] shrink-0 rounded-md border border-white/10 bg-black/20 px-1.5 py-0.5 text-center font-mono text-white/70">
                    {e.source}
                  </div>
                  <div
                    className={[
                      "w-[52px] shrink-0 rounded-md border px-1.5 py-0.5 text-center font-mono",
                      e.pipe === "read"
                        ? "border-sky-500/25 bg-sky-500/10 text-sky-200"
                        : "border-amber-500/25 bg-amber-500/10 text-amber-200"
                    ].join(" ")}
                  >
                    {e.pipe}
                  </div>
                  <div className="min-w-0 flex-1 truncate font-mono text-white/85">{e.event}</div>
                </div>
                <div className="mt-1 flex flex-col gap-1">
                  <div className="text-white/80">{e.message}</div>
                  {e.series_id ? <div className="font-mono text-white/40">{e.series_id}</div> : null}
                  {e.data ? (
                    <details className="rounded-md border border-white/10 bg-black/20 p-2 text-white/70">
                      <summary className="cursor-pointer select-none font-mono text-[11px] text-white/60">data</summary>
                      <pre className="mt-2 whitespace-pre-wrap break-words font-mono text-[10px] leading-snug">
                        {JSON.stringify(e.data, null, 2)}
                      </pre>
                    </details>
                  ) : null}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
