import { useMemo, useState } from "react";

import { oracleJson } from "../lib/oracleApi";
import { useUiStore } from "../state/uiStore";

type AnalyzeResponse = {
  series_id: string;
  generated_at_utc: string;
  bias: string;
  confidence: string;
  total_score: number;
  historical_note: string;
  report_markdown: string;
};

type BacktestResponse = {
  ok: boolean;
  passed: boolean;
  target: {
    win_rate: number;
    reward_risk: number;
  };
  metrics: {
    trades: number;
    win_rate: number;
    reward_risk: number;
    threshold: number | null;
    windows: number;
  };
};

function errorHint(message: string | null): string | null {
  if (!message) return null;
  if (message.includes("oracle_api_unreachable")) {
    return "请先启动 trade_oracle API：uvicorn trade_oracle.apps.api.main:app --reload --port 8091";
  }
  if (message.includes("market_source_unavailable") || message.includes("market_source_error")) {
    return "trade_oracle 已启动，但上游 trade_canvas 市场接口不可用，请先启动 backend：bash scripts/dev_backend.sh";
  }
  return null;
}

export function OraclePage() {
  const { exchange, market, symbol } = useUiStore();
  const defaultSeriesId = useMemo(() => `${exchange}:${market}:${symbol}:1d`, [exchange, market, symbol]);
  const assetSymbol = useMemo(() => symbol.split("/")[0] ?? "BTC", [symbol]);

  const [seriesId, setSeriesId] = useState(defaultSeriesId);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [analyze, setAnalyze] = useState<AnalyzeResponse | null>(null);
  const [backtest, setBacktest] = useState<BacktestResponse | null>(null);
  const hint = errorHint(error);

  async function runAnalyze() {
    setLoading(true);
    setError(null);
    try {
      const data = await oracleJson<AnalyzeResponse>(
        `/api/oracle/analyze/current?series_id=${encodeURIComponent(seriesId)}&symbol=${encodeURIComponent(assetSymbol)}`
      );
      setAnalyze(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  async function runBacktest() {
    setLoading(true);
    setError(null);
    try {
      const data = await oracleJson<BacktestResponse>(
        `/api/oracle/backtest/run?series_id=${encodeURIComponent(seriesId)}&symbol=${encodeURIComponent(assetSymbol)}`
      );
      setBacktest(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full w-full p-4">
      <div className="mb-3 flex items-center justify-between">
        <h1 className="text-sm font-semibold tracking-wide text-white/90">Trade Oracle</h1>
        <div className="text-xs text-white/50">独立页面：八字分析与回测证据</div>
      </div>

      <div className="rounded-lg border border-white/10 bg-white/5 p-4">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-white/80">
          <label className="text-white/60">series_id</label>
          <input
            value={seriesId}
            onChange={(e) => setSeriesId(e.target.value)}
            className="w-[360px] rounded border border-white/15 bg-black/20 px-2 py-1 font-mono text-[11px] text-white outline-none focus:border-sky-500/70"
          />
          <button
            type="button"
            onClick={() => setSeriesId(defaultSeriesId)}
            className="rounded border border-white/15 bg-white/5 px-2 py-1 text-[11px] text-white/80 hover:bg-white/10"
          >
            使用当前市场1d
          </button>
        </div>

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={runAnalyze}
            disabled={loading}
            className="rounded bg-emerald-500/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            生成分析
          </button>
          <button
            type="button"
            onClick={runBacktest}
            disabled={loading}
            className="rounded bg-sky-500/80 px-3 py-1.5 text-xs font-semibold text-white hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
          >
            运行回测
          </button>
        </div>

        {error ? (
          <div className="mb-3 rounded border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
            <div>{error}</div>
            {hint ? <div className="mt-1 text-rose-100/80">{hint}</div> : null}
          </div>
        ) : null}

        {backtest ? (
          <div className="mb-3 rounded border border-white/10 bg-black/20 p-3 text-xs text-white/80">
            <div className="mb-1 font-semibold text-white">回测门槛</div>
            <div>
              目标: 胜率 {backtest.target.win_rate.toFixed(2)} / 盈亏比 {backtest.target.reward_risk.toFixed(2)} ·
              实际: 胜率 {backtest.metrics.win_rate.toFixed(4)} / 盈亏比 {backtest.metrics.reward_risk.toFixed(4)}
            </div>
            <div>
              trades={backtest.metrics.trades} · windows={backtest.metrics.windows} · threshold=
              {backtest.metrics.threshold == null ? "N/A" : backtest.metrics.threshold.toFixed(2)} · pass=
              {String(backtest.passed)}
            </div>
          </div>
        ) : null}

        {analyze ? (
          <div className="rounded border border-white/10 bg-black/20 p-3 text-xs text-white/80">
            <div className="mb-1 flex items-center justify-between">
              <div className="font-semibold text-white">分析摘要</div>
              <div className="text-[11px] text-white/50">{analyze.generated_at_utc}</div>
            </div>
            <div className="mb-2">
              bias={analyze.bias} · confidence={analyze.confidence} · total_score={analyze.total_score.toFixed(2)}
            </div>
            <div className="mb-2 text-white/70">{analyze.historical_note}</div>
            <pre className="max-h-[380px] overflow-auto whitespace-pre-wrap rounded border border-white/10 bg-black/30 p-2 font-mono text-[11px] text-white/75">
              {analyze.report_markdown}
            </pre>
          </div>
        ) : (
          <div className="text-xs text-white/45">
            提示：先启动 `trade_oracle` API（默认 `http://127.0.0.1:8091`），再点击上方按钮。
          </div>
        )}
      </div>
    </div>
  );
}
