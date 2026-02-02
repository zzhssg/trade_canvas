import { ChartView } from "../widgets/ChartView";

export function ChartPanel({ mode }: { mode: "live" | "replay" }) {
  return (
    <div className="h-full w-full p-3">
      <div className="flex h-full w-full flex-col gap-3">
        <div className="flex items-center justify-between rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-xs text-white/70">
          <div className="flex items-center gap-2">
            <span className="rounded bg-white/10 px-2 py-1 font-mono">mode:{mode}</span>
            <span>closed-candle drives indicators (planned)</span>
          </div>
          <div className="font-mono">candle_id: mock</div>
        </div>
        <div
          className="min-h-0 flex-1 overflow-hidden rounded-lg border border-white/10 bg-black/20"
          data-chart-area="true"
        >
          <ChartView />
        </div>
      </div>
    </div>
  );
}
