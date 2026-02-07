import { useMemo } from "react";

import { useReplayStore } from "../state/replayStore";
import { useUiStore } from "../state/uiStore";

const SPEED_OPTIONS = [50, 100, 200, 400, 800];

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
  const setPlaying = useReplayStore((s) => s.setPlaying);
  const setSpeedMs = useReplayStore((s) => s.setSpeedMs);
  const setIndex = useReplayStore((s) => s.setIndex);

  const seriesId = useMemo(() => `${exchange}:${market}:${symbol}:${timeframe}`, [exchange, market, symbol, timeframe]);
  const drawJson = useMemo(() => (frame ? JSON.stringify(frame.draw_state, null, 2) : ""), [frame]);
  const factorJson = useMemo(() => (frame ? JSON.stringify(frame.factor_slices, null, 2) : ""), [frame]);

  const disabled = mode !== "replay" || total === 0;
  const sliderMax = Math.max(0, total - 1);

  return (
    <div className="flex flex-col gap-3 text-[11px] text-white/70">
      <div className="flex items-center justify-between">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-white/60">Replay</div>
        <div className="font-mono text-[10px] text-white/45">{seriesId}</div>
      </div>

      {mode !== "replay" ? (
        <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-white/50">
          切换到 replay 模式后可用。
        </div>
      ) : null}

      <div className="rounded-lg border border-white/10 bg-black/20 p-2 text-white/60">
        <div className="flex items-center justify-between">
          <span>prepare</span>
          <span className="font-mono">{prepareStatus}</span>
        </div>
        {prepareError ? <div className="mt-1 text-rose-200">{prepareError}</div> : null}
        <div className="mt-2 flex items-center justify-between">
          <span>frame</span>
          <span className="font-mono">{frameLoading ? "loading" : frame ? "ready" : "idle"}</span>
        </div>
        {frameError ? <div className="mt-1 text-rose-200">{frameError}</div> : null}
        <div className="mt-2 flex items-center justify-between">
          <span>focus_time</span>
          <span className="font-mono">{focusTime ?? "—"}</span>
        </div>
        <div className="mt-1 flex items-center justify-between">
          <span>candle_id</span>
          <span className="font-mono">{frame?.time.candle_id ?? "—"}</span>
        </div>
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

          <span className="font-mono text-white/60">
            {total ? `${index + 1}/${total}` : "0/0"}
          </span>
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
