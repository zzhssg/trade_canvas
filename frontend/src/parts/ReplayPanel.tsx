import { useMemo } from "react";

import { useReplayStore } from "../state/replayStore";
import { useUiStore } from "../state/uiStore";

const SPEED_OPTIONS = [50, 100, 200, 400, 800];

function formatJson(value: unknown) {
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? "");
  }
}

export function ReplayPanel() {
  const { exchange, market, symbol, timeframe } = useUiStore();
  const mode = useReplayStore((s) => s.mode);
  const playing = useReplayStore((s) => s.playing);
  const speedMs = useReplayStore((s) => s.speedMs);
  const index = useReplayStore((s) => s.index);
  const total = useReplayStore((s) => s.total);
  const focusTime = useReplayStore((s) => s.focusTime);
  const frame = useReplayStore((s) => s.frame);
  const frameLoading = useReplayStore((s) => s.frameLoading);
  const frameError = useReplayStore((s) => s.frameError);
  const prepareStatus = useReplayStore((s) => s.prepareStatus);
  const prepareError = useReplayStore((s) => s.prepareError);
  const status = useReplayStore((s) => s.status);
  const coverage = useReplayStore((s) => s.coverage);
  const coverageStatus = useReplayStore((s) => s.coverageStatus);
  const metadata = useReplayStore((s) => s.metadata);
  const currentSlices = useReplayStore((s) => s.currentSlices);
  const currentCandleId = useReplayStore((s) => s.currentCandleId);
  const currentAtTime = useReplayStore((s) => s.currentAtTime);
  const currentDrawActiveIds = useReplayStore((s) => s.currentDrawActiveIds);
  const currentDrawInstructions = useReplayStore((s) => s.currentDrawInstructions);
  const setPlaying = useReplayStore((s) => s.setPlaying);
  const setSpeedMs = useReplayStore((s) => s.setSpeedMs);
  const setIndex = useReplayStore((s) => s.setIndex);

  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);
  const drawPayload = currentDrawInstructions.length > 0 ? currentDrawInstructions : frame?.draw_state ?? null;
  const factorPayload = currentSlices?.snapshots ?? frame?.factor_slices?.snapshots ?? null;
  const drawJson = useMemo(() => (drawPayload ? formatJson(drawPayload) : ""), [drawPayload]);
  const factorJson = useMemo(() => (factorPayload ? formatJson(factorPayload) : ""), [factorPayload]);

  const disabled = mode !== "replay" || total === 0 || prepareStatus === "loading" || prepareStatus === "error";
  const sliderMax = Math.max(0, total - 1);
  const candleId = currentCandleId ?? frame?.time?.candle_id ?? "—";
  const atTime = currentAtTime ?? focusTime ?? frame?.time?.aligned_time ?? null;

  return (
    <div className="flex flex-col gap-3 text-[11px] text-white/70">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Replay</div>
        <div className="font-mono text-[10px] text-white/45">{seriesId}</div>
      </div>

      {mode !== "replay" ? (
        <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-white/50">切换到 replay 模式后可用。</div>
      ) : null}

      <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-white/60">
        <div className="flex items-center justify-between">
          <span>prepare</span>
          <span className="font-mono">{prepareStatus}</span>
        </div>
        {prepareError ? <div className="mt-1 text-rose-200">{prepareError}</div> : null}
        <div className="mt-2 flex items-center justify-between">
          <span>package</span>
          <span className="font-mono">{status}</span>
        </div>
        {coverage ? (
          <div className="mt-1 text-[10px] text-white/55">
            coverage {coverage.candles_ready}/{coverage.required_candles}
          </div>
        ) : null}
        {coverageStatus ? (
          <div className="mt-1 text-[10px] text-white/45">
            {coverageStatus.status}
            {coverageStatus.head_time ? ` · head=${coverageStatus.head_time}` : ""}
          </div>
        ) : null}
        {metadata ? (
          <div className="mt-1 text-[10px] text-white/45">
            window={metadata.window_size} · snapshot={metadata.snapshot_interval}
          </div>
        ) : null}
        <div className="mt-2 flex items-center justify-between">
          <span>frame</span>
          <span className="font-mono">{frameLoading ? "loading" : frame ? "ready" : "idle"}</span>
        </div>
        {frameError ? <div className="mt-1 text-rose-200">{frameError}</div> : null}
        <div className="mt-2 flex items-center justify-between">
          <span>focus_time</span>
          <span className="font-mono">{atTime ?? "—"}</span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span>candle_id</span>
          <span className="font-mono">{candleId}</span>
        </div>
        <div className="mt-1 text-[10px] text-white/45">draw_active: {currentDrawActiveIds.length}</div>
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-2">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/60">Playback</div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            data-testid="replay-play"
            disabled={disabled}
            onClick={() => setPlaying(!playing)}
            className={[
              "rounded border px-2 py-1 text-[11px] transition-colors",
              disabled
                ? "border-white/10 bg-white/5 text-white/30"
                : "border-white/10 bg-white/10 text-white/80 hover:bg-white/15"
            ].join(" ")}
          >
            {playing ? "Pause" : "Play"}
          </button>

          <select
            data-testid="replay-speed"
            disabled={disabled}
            value={speedMs}
            onChange={(e) => setSpeedMs(Number(e.target.value))}
            className="rounded border border-white/10 bg-black/40 px-2 py-1 text-[11px] text-white/80"
          >
            {SPEED_OPTIONS.map((ms) => (
              <option key={ms} value={ms}>
                {Math.round(1000 / ms)}x
              </option>
            ))}
          </select>

          <span className="font-mono text-white/60">{total ? `${index + 1}/${total}` : "0/0"}</span>
        </div>

        <input
          data-testid="replay-seek"
          className="mt-2 w-full"
          type="range"
          min={0}
          max={sliderMax}
          value={Math.min(index, sliderMax)}
          onChange={(e) => setIndex(Number(e.target.value))}
          disabled={disabled}
        />
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-2">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/60">Draw Instructions</div>
        <pre className="tc-scrollbar-none max-h-56 overflow-auto whitespace-pre-wrap break-words text-[10px] text-white/70">
          {drawJson || "暂无绘图指令"}
        </pre>
      </div>

      <div className="rounded-lg border border-white/10 bg-black/20 p-2">
        <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/60">Factor Slices</div>
        <pre className="tc-scrollbar-none max-h-56 overflow-auto whitespace-pre-wrap break-words text-[10px] text-white/70">
          {factorJson || "暂无因子数据"}
        </pre>
      </div>
    </div>
  );
}
