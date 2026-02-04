import { useEffect, useMemo, useState } from "react";

import { ENABLE_DEBUG_TOOL, getDebugSnapshot, TC_DEBUG_EVENT_NAME, type DebugEvent } from "../debug/debug";
import { useUiStore } from "../state/uiStore";

export function DebugPanel() {
  const { exchange, market, symbol, timeframe } = useUiStore();
  const [items, setItems] = useState<DebugEvent[]>(() => getDebugSnapshot().slice(-200));

  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);

  useEffect(() => {
    if (!ENABLE_DEBUG_TOOL) return;
    const onEvt = (evt: Event) => {
      const ce = evt as CustomEvent<DebugEvent>;
      const detail = ce.detail;
      if (!detail) return;
      setItems((prev) => [...prev, detail].slice(-200));
    };
    window.addEventListener(TC_DEBUG_EVENT_NAME, onEvt);
    return () => window.removeEventListener(TC_DEBUG_EVENT_NAME, onEvt);
  }, []);

  if (!ENABLE_DEBUG_TOOL) {
    return <div className="text-xs text-white/60">Debug disabled (set VITE_ENABLE_DEBUG_TOOL=1).</div>;
  }

  return (
    <div className="flex flex-col gap-2 text-[11px] text-white/70">
      <div className="rounded-lg border border-white/10 bg-black/25 p-2">
        <div className="mb-1 font-semibold text-white/80">Context</div>
        <div className="font-mono text-white/70">series_id: {seriesId}</div>
      </div>

      <div className="max-h-[42vh] overflow-auto rounded-lg border border-white/10 bg-black/25 p-2 font-mono text-[10px] text-white/70">
        {items.length === 0 ? (
          <div className="text-white/50">(no events)</div>
        ) : (
          items
            .slice()
            .reverse()
            .map((e, idx) => (
              <div key={`${e.ts_ms}-${idx}`} className="border-b border-white/10 py-1 last:border-b-0">
                <div className="text-white/50">
                  {new Date(e.ts_ms).toLocaleTimeString()} · {e.level} · {e.pipe} · {e.event}
                </div>
                <div className="text-white/80">{e.message}</div>
                {e.data ? <div className="whitespace-pre-wrap text-white/60">{JSON.stringify(e.data)}</div> : null}
              </div>
            ))
        )}
      </div>
    </div>
  );
}
