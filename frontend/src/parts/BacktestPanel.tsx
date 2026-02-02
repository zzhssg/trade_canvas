import { useMutation, useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { apiJson } from "../lib/api";
import { useUiStore } from "../state/uiStore";

type StrategyListResponse = { strategies: string[] };

type BacktestRunRequest = {
  strategy_name: string;
  pair: string;
  timeframe: string;
  timerange?: string | null;
};

type BacktestRunResponse = {
  ok: boolean;
  exit_code: number;
  duration_ms: number;
  command: string[];
  stdout: string;
  stderr: string;
};

export function BacktestPanel({ containerClassName }: { containerClassName?: string }) {
  const { symbol, timeframe } = useUiStore();
  const [selected, setSelected] = useState<string>("");
  const [timerange, setTimerange] = useState<string>("");

  const strategiesQuery = useQuery({
    queryKey: ["backtest", "strategies"],
    queryFn: () => apiJson<StrategyListResponse>("/api/backtest/strategies")
  });

  const strategies = strategiesQuery.data?.strategies ?? [];

  const defaultStrategy = useMemo(() => strategies[0] ?? "", [strategies]);
  const selectedStrategy = selected || defaultStrategy;

  const runMutation = useMutation({
    mutationFn: (payload: BacktestRunRequest) =>
      apiJson<BacktestRunResponse>("/api/backtest/run", { method: "POST", body: JSON.stringify(payload) })
  });

  const output = useMemo(() => {
    const data = runMutation.data;
    if (!data) return "";
    const parts = [
      `ok=${data.ok} exit_code=${data.exit_code} duration_ms=${data.duration_ms}`,
      `command: ${data.command.join(" ")}`,
      "",
      "----- stdout -----",
      data.stdout || "",
      "",
      "----- stderr -----",
      data.stderr || ""
    ];
    return parts.join("\n");
  }, [runMutation.data]);

  return (
    <div className={["h-full w-full", containerClassName ?? ""].join(" ")} data-testid="backtest-panel">
      <div className="mb-3 rounded-lg border border-white/10 bg-white/5 p-3 text-sm text-white/80">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="font-semibold">Backtest (freqtrade)</div>
          <div className="text-xs text-white/60">
            pair: <span className="font-mono text-white/80">{symbol}</span> · tf:{" "}
            <span className="font-mono text-white/80">{timeframe}</span>
          </div>
        </div>
      </div>

      <div className="grid min-h-0 gap-3 md:grid-cols-[360px,1fr]">
        <div className="rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-white/60">Run</div>

          <label className="mb-2 block text-xs text-white/70">
            Strategy
            <select
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-2 py-2 text-xs"
              value={selectedStrategy}
              onChange={(e) => setSelected(e.target.value)}
              disabled={strategiesQuery.isLoading || strategies.length === 0}
              data-testid="backtest-strategy-select"
            >
              {strategies.length === 0 ? <option value="">(no strategies)</option> : null}
              {strategies.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>

          <label className="mb-2 block text-xs text-white/70">
            Timerange (optional)
            <input
              className="mt-1 w-full rounded border border-white/10 bg-black/40 px-2 py-2 text-xs font-mono"
              placeholder="YYYYMMDD-YYYYMMDD (e.g. 20260130-20260201)"
              value={timerange}
              onChange={(e) => setTimerange(e.target.value)}
              data-testid="backtest-timerange"
            />
          </label>

          <button
            type="button"
            className={[
              "mt-2 w-full rounded border border-white/10 px-3 py-2 text-xs font-semibold",
              runMutation.isPending ? "bg-white/10 text-white/50" : "bg-white/15 text-white hover:bg-white/20"
            ].join(" ")}
            disabled={runMutation.isPending || !selectedStrategy}
            onClick={() =>
              runMutation.mutate({
                strategy_name: selectedStrategy,
                pair: symbol,
                timeframe,
                timerange: timerange.trim() ? timerange.trim() : null
              })
            }
            data-testid="backtest-run"
          >
            {runMutation.isPending ? "Running..." : "Run backtest"}
          </button>

          {strategiesQuery.isError ? (
            <div className="mt-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-200">
              Failed to load strategies: {(strategiesQuery.error as Error).message}
            </div>
          ) : null}

          {runMutation.isError ? (
            <div className="mt-3 rounded border border-red-500/30 bg-red-500/10 p-2 text-xs text-red-200">
              Backtest failed: {(runMutation.error as Error).message}
            </div>
          ) : null}
        </div>

        <div className="flex min-h-[220px] min-w-0 flex-col rounded-lg border border-white/10 bg-black/20 p-3">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-white/60">Output</div>
            <button
              type="button"
              className="rounded border border-white/10 bg-black/30 px-2 py-1 text-[11px] text-white/70 hover:bg-black/40"
              onClick={() => navigator.clipboard.writeText(output)}
              disabled={!output}
              title={!output ? "No output" : "Copy"}
            >
              Copy
            </button>
          </div>
          <pre
            className="min-h-0 w-full flex-1 overflow-auto rounded border border-white/10 bg-black/30 p-2 text-[11px] leading-relaxed text-white/80"
            data-testid="backtest-output"
          >
            {output || "No output yet."}
          </pre>
        </div>
      </div>
    </div>
  );
}

