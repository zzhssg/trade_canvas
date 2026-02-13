#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_SERIES_IDS = (
    "binance:futures:BTC/USDT:1m",
    "binance:futures:BTC/USDT:5m",
    "binance:futures:BTC/USDT:15m",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _imports() -> dict[str, Any]:
    root = _repo_root()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "backend"))

    from backend.app.core.config import load_settings  # noqa: WPS433
    from backend.app.market_data import StoreBackfillService  # noqa: WPS433
    from backend.app.market_kline_health import analyze_series_health  # noqa: WPS433
    from backend.app.storage.candle_store import CandleStore  # noqa: WPS433

    return {
        "load_settings": load_settings,
        "StoreBackfillService": StoreBackfillService,
        "analyze_series_health": analyze_series_health,
        "CandleStore": CandleStore,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="检查 market K 线新鲜度、连续性、派生桶完整度。")
    p.add_argument(
        "--series-id",
        action="append",
        default=[],
        help="可重复指定。默认检查 BTC futures 1m/5m/15m。",
    )
    p.add_argument("--db-path", default="", help="覆盖 DB 路径（默认读取 settings db_path）。")
    p.add_argument("--max-recent-gaps", type=int, default=5, help="输出最近 gap 条数（默认 5）。")
    p.add_argument("--recent-base-buckets", type=int, default=8, help="输出最近基准桶数（默认 8）。")
    p.add_argument(
        "--repair-derived-from-base",
        action="store_true",
        help="对非 1m 周期执行一次 ensure_tail_coverage（可触发 1m->派生回填）。",
    )
    p.add_argument("--repair-target-candles", type=int, default=2000, help="repair 目标窗口（默认 2000）。")
    p.add_argument("--json", action="store_true", help="输出 JSON。")
    return p.parse_args(argv)


def _print_human(payload: dict[str, Any]) -> None:
    print(
        f"[{payload['series_id']}] head={payload['head_time']} lag_s={payload['lag_seconds']} "
        f"count={payload['candle_count']} gaps={payload['gap_count']} max_gap={payload['max_gap_seconds']}"
    )
    for g in payload.get("recent_gaps", []):
        print(
            "  gap "
            f"prev={g['prev_time']} next={g['next_time']} delta={g['delta_seconds']} missing={g['missing_candles']}"
        )
    buckets = payload.get("base_bucket_completeness", [])
    if buckets:
        print(f"  base={payload['base_series_id']} recent buckets:")
        for b in buckets:
            print(
                "    "
                f"open={b['bucket_open_time']} actual={b['actual_minutes']}/{b['expected_minutes']} "
                f"missing={b['missing_minutes']}"
            )


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    mods = _imports()

    settings = mods["load_settings"]()
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else settings.db_path
    store = mods["CandleStore"](db_path=db_path)

    if args.repair_derived_from_base:
        backfill = mods["StoreBackfillService"](store=store)
    else:
        backfill = None

    series_ids = tuple(args.series_id) if args.series_id else DEFAULT_SERIES_IDS
    out: list[dict[str, Any]] = []
    for sid in series_ids:
        if backfill is not None and not sid.endswith(":1m"):
            backfill.ensure_tail_coverage(
                series_id=sid,
                target_candles=max(1, int(args.repair_target_candles)),
                to_time=None,
            )
        payload = mods["analyze_series_health"](
            store=store,
            series_id=sid,
            max_recent_gaps=max(1, int(args.max_recent_gaps)),
            recent_base_buckets=max(1, int(args.recent_base_buckets)),
        )
        out.append(payload)

    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        for item in out:
            _print_human(item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
