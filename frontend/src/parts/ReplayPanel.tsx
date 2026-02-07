import { useMemo } from "react";

import { useReplayStore } from "../state/replayStore";

const ENABLE_REPLAY_V1 = import.meta.env.VITE_ENABLE_REPLAY_V1 === "1";

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

export function ReplayPanel() {
  const enabled = useReplayStore((s) => s.enabled);
  const status = useReplayStore((s) => s.status);
  const error = useReplayStore((s) => s.error);
  const coverage = useReplayStore((s) => s.coverage);
  const coverageStatus = useReplayStore((s) => s.coverageStatus);
  const metadata = useReplayStore((s) => s.metadata);
  const currentSlices = useReplayStore((s) => s.currentSlices);
  const currentCandleId = useReplayStore((s) => s.currentCandleId);
  const currentAtTime = useReplayStore((s) => s.currentAtTime);
  const currentDrawActiveIds = useReplayStore((s) => s.currentDrawActiveIds);
  const setEnabled = useReplayStore((s) => s.setEnabled);

  const factorsJson = useMemo(() => {
    return formatJson(currentSlices?.snapshots ?? {});
  }, [currentSlices]);

  return (
    <div className="flex flex-col gap-2 text-xs text-white/70">
      <div className="flex items-center justify-between">
        <div className="font-semibold uppercase tracking-wider text-white/60">Replay</div>
        <button
          type="button"
          onClick={() => setEnabled(!enabled)}
          disabled={!ENABLE_REPLAY_V1}
          className={[
            "rounded-md border px-2 py-1 font-mono text-[11px] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
            enabled
              ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-200"
              : "border-white/10 bg-black/30 text-white/70 hover:bg-white/10"
          ].join(" ")}
        >
          {enabled ? "Replay ON" : "Replay OFF"}
        </button>
      </div>
      {!ENABLE_REPLAY_V1 ? (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-200">
          VITE_ENABLE_REPLAY_V1=0 (replay disabled)
        </div>
      ) : null}

      <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1">
        <div className="flex items-center justify-between">
          <span className="text-white/50">status</span>
          <span className="font-mono text-[11px] text-white/80">{status}</span>
        </div>
        {error ? <div className="mt-1 text-[11px] text-rose-300">error: {error}</div> : null}
      </div>

      <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1">
        <div className="flex items-center justify-between">
          <span className="text-white/50">coverage</span>
          <span className="font-mono text-[11px] text-white/80">
            {coverage ? `${coverage.candles_ready}/${coverage.required_candles}` : "—"}
          </span>
        </div>
        {coverageStatus ? (
          <div className="mt-1 text-[11px] text-white/50">
            {coverageStatus.status}
            {coverageStatus.head_time ? ` · head=${coverageStatus.head_time}` : ""}
          </div>
        ) : null}
      </div>

      <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1">
        <div className="text-white/50">current</div>
        <div className="mt-1 font-mono text-[11px] text-white/80">
          {currentCandleId ?? "candle_id: —"}
        </div>
        <div className="mt-1 text-[11px] text-white/50">
          at_time: {currentAtTime != null ? currentAtTime : "—"} · draw_active: {currentDrawActiveIds.length}
        </div>
      </div>

      <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1">
        <div className="text-white/50">package</div>
        <div className="mt-1 text-[11px] text-white/60">
          {metadata
            ? `candles=${metadata.total_candles} · window=${metadata.window_size} · snapshot=${metadata.snapshot_interval}`
            : "—"}
        </div>
      </div>

      <div className="rounded-md border border-white/10 bg-black/20 px-2 py-1">
        <div className="text-white/50">factors (json)</div>
        <pre className="mt-1 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 text-[10px] text-white/80">
          {factorsJson || "{}"}
        </pre>
      </div>
    </div>
  );
}
