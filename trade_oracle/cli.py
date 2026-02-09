from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from trade_oracle.config import load_settings
from trade_oracle.packages.calendar_engine.audit import build_sample_times, crosscheck_samples, write_report
from trade_oracle.service import OracleService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run trade_oracle BTC analysis and audits")
    parser.add_argument("--task", choices=["analyze", "backtest-live", "calendar-audit"], default="analyze")
    parser.add_argument("--series-id", default="binance:futures:BTC/USDT:1d")
    parser.add_argument("--symbol", default="BTC")
    parser.add_argument("--output-dir", default="trade_oracle/output")
    parser.add_argument("--backtest-output", default="backtest_evidence.json")
    parser.add_argument("--audit-output", default="calendar_crosscheck.json")
    parser.add_argument("--audit-start-utc", default="2009-01-03T16:15:00+00:00")
    parser.add_argument("--audit-end-utc", default="2026-01-01T00:00:00+00:00")
    parser.add_argument("--audit-step-days", type=int, default=30)
    return parser


def _parse_iso_utc(raw: str) -> datetime:
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _run_analyze(args: argparse.Namespace, *, out_dir: Path) -> int:
    settings = load_settings()
    svc = OracleService(settings)
    payload, report_md = svc.analyze_current(series_id=args.series_id, symbol=args.symbol)

    report_path = out_dir / "report.md"
    evidence_path = out_dir / "evidence.json"

    report_path.write_text(report_md, encoding="utf-8")
    evidence_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"report={report_path}")
    print(f"evidence={evidence_path}")
    return 0


def _run_backtest_live(args: argparse.Namespace, *, out_dir: Path) -> int:
    settings = load_settings()
    svc = OracleService(settings)
    result = svc.run_market_backtest(series_id=args.series_id, symbol=args.symbol)
    output_path = out_dir / args.backtest_output
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"backtest={output_path}")
    print(
        "pass="
        f"{result['passed']} "
        f"win_rate={result['metrics']['win_rate']:.4f} "
        f"reward_risk={result['metrics']['reward_risk']:.4f}"
    )
    return 0


def _run_calendar_audit(args: argparse.Namespace, *, out_dir: Path) -> int:
    start_utc = _parse_iso_utc(args.audit_start_utc)
    end_utc = _parse_iso_utc(args.audit_end_utc)
    sample_times = build_sample_times(start_utc=start_utc, end_utc=end_utc, step_days=args.audit_step_days)
    report = crosscheck_samples(sample_times=sample_times)
    output_path = out_dir / args.audit_output
    write_report(report=report, path=output_path)
    print(f"calendar_audit={output_path}")
    print(f"samples={report.samples} mismatches={report.mismatches} mismatch_rate={report.mismatch_rate:.4f}")
    return 0


def main() -> int:
    args = build_parser().parse_args()
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.task == "analyze":
        return _run_analyze(args, out_dir=out_dir)
    if args.task == "backtest-live":
        return _run_backtest_live(args, out_dir=out_dir)
    if args.task == "calendar-audit":
        return _run_calendar_audit(args, out_dir=out_dir)
    raise ValueError(f"unsupported task: {args.task}")


if __name__ == "__main__":
    raise SystemExit(main())
