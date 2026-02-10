#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_series_ids(db_path: Path) -> list[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT DISTINCT series_id FROM candles ORDER BY series_id ASC").fetchall()
        return [str(r[0]) for r in rows if r and r[0]]
    finally:
        conn.close()


def _split_timeframe(series_id: str) -> str:
    return str(series_id).rsplit(":", 1)[-1]


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="轮测所有币种+周期的自动补齐触发情况。")
    p.add_argument("--db-path", default="backend/data/market.db", help="SQLite path (默认 backend/data/market.db)")
    p.add_argument("--rounds", type=int, default=2, help="轮数（默认 2）")
    p.add_argument("--limit", type=int, default=500, help="每次 /api/market/candles 的 limit（默认 500）")
    p.add_argument(
        "--transport",
        choices=("live", "app"),
        default="app",
        help="live=调用运行中的服务; app=进程内 TestClient（默认 app）",
    )
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="transport=live 时生效")
    p.add_argument("--request-timeout", type=float, default=25.0, help="live 请求超时秒（默认 25）")
    p.add_argument("--max-recent-gaps", type=int, default=1, help="series_health 参数（默认 1）")
    p.add_argument("--recent-base-buckets", type=int, default=2, help="series_health 参数（默认 2）")
    p.add_argument("--series-id", action="append", default=[], help="可重复指定；不传则跑 DB 全部 series")
    p.add_argument(
        "--report-path",
        default="output/market_backfill_rounds_report.json",
        help="报告路径（json）",
    )
    p.add_argument(
        "--enable-ccxt-on-read",
        action="store_true",
        help="app 模式下开启 TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ=1（默认关闭）",
    )
    return p.parse_args(argv)


def _live_get_json(base_url: str, path: str, *, timeout: float) -> dict[str, Any]:
    url = str(base_url).rstrip("/") + str(path)
    with urllib.request.urlopen(url, timeout=float(timeout)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _build_app_get_json(*, root: Path, db_path: Path, enable_ccxt_on_read: bool) -> Callable[[str], dict[str, Any]]:
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "backend"))

    os.environ["TRADE_CANVAS_DB_PATH"] = str(db_path)
    os.environ["TRADE_CANVAS_WHITELIST_PATH"] = str(root / "backend" / "config" / "market_whitelist.json")
    os.environ["TRADE_CANVAS_ENABLE_MARKET_AUTO_TAIL_BACKFILL"] = "1"
    os.environ["TRADE_CANVAS_MARKET_AUTO_TAIL_BACKFILL_MAX_CANDLES"] = "500"
    os.environ["TRADE_CANVAS_ENABLE_CCXT_BACKFILL"] = "1"
    os.environ["TRADE_CANVAS_ENABLE_CCXT_BACKFILL_ON_READ"] = "1" if enable_ccxt_on_read else "0"
    os.environ["TRADE_CANVAS_MARKET_HISTORY_SOURCE"] = "freqtrade"
    os.environ["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"

    from fastapi.testclient import TestClient  # noqa: WPS433
    from backend.app.main import create_app  # noqa: WPS433

    client = TestClient(create_app())

    def _get_json(path: str) -> dict[str, Any]:
        q = urllib.parse.urlparse(path)
        route = q.path
        params = urllib.parse.parse_qs(q.query, keep_blank_values=False)
        flat_params = {k: (v[-1] if v else "") for k, v in params.items()}
        resp = client.get(route, params=flat_params)
        if resp.status_code != 200:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:160]}")
        return resp.json()

    return _get_json


def _health_path(series_id: str, *, max_recent_gaps: int, recent_base_buckets: int) -> str:
    q = urllib.parse.urlencode(
        {
            "series_id": series_id,
            "max_recent_gaps": int(max_recent_gaps),
            "recent_base_buckets": int(recent_base_buckets),
        }
    )
    return f"/api/market/debug/series_health?{q}"


def _candles_path(series_id: str, *, limit: int) -> str:
    q = urllib.parse.urlencode({"series_id": series_id, "limit": int(limit)})
    return f"/api/market/candles?{q}"


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    root = _repo_root()
    db_path = Path(args.db_path).expanduser().resolve()
    report_path = Path(args.report_path).expanduser().resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)

    all_series_ids = _load_series_ids(db_path=db_path)
    series_ids = list(args.series_id) if args.series_id else all_series_ids

    if args.transport == "live":
        get_json = lambda path: _live_get_json(args.base_url, path, timeout=float(args.request_timeout))
    else:
        get_json = _build_app_get_json(
            root=root,
            db_path=db_path,
            enable_ccxt_on_read=bool(args.enable_ccxt_on_read),
        )

    rounds_payload: list[dict[str, Any]] = []
    for idx in range(1, max(1, int(args.rounds)) + 1):
        started = time.time()
        stats = Counter()
        details: list[dict[str, Any]] = []
        print(f"\n=== round {idx} / {args.rounds} ===")

        for i, series_id in enumerate(series_ids, start=1):
            row: dict[str, Any] = {"series_id": series_id}
            try:
                before = get_json(
                    _health_path(
                        series_id,
                        max_recent_gaps=int(args.max_recent_gaps),
                        recent_base_buckets=int(args.recent_base_buckets),
                    )
                )
                candles = get_json(_candles_path(series_id, limit=int(args.limit)))
                after = get_json(
                    _health_path(
                        series_id,
                        max_recent_gaps=int(args.max_recent_gaps),
                        recent_base_buckets=int(args.recent_base_buckets),
                    )
                )
                before_head = before.get("head_time")
                after_head = after.get("head_time")
                before_count = int(before.get("candle_count") or 0)
                after_count = int(after.get("candle_count") or 0)
                before_lag = before.get("lag_seconds")
                after_lag = after.get("lag_seconds")
                triggered = (int(after_head or 0) > int(before_head or 0)) or (after_count > before_count)
                lag_improved = isinstance(before_lag, int) and isinstance(after_lag, int) and int(after_lag) < int(before_lag)

                row.update(
                    {
                        "ok": True,
                        "returned": len(list(candles.get("candles") or [])),
                        "before_head": before_head,
                        "after_head": after_head,
                        "before_count": before_count,
                        "after_count": after_count,
                        "before_lag": before_lag,
                        "after_lag": after_lag,
                        "triggered": bool(triggered),
                        "lag_improved": bool(lag_improved),
                    }
                )
                stats["ok"] += 1
                stats["triggered" if triggered else "not_triggered"] += 1
                if lag_improved:
                    stats["lag_improved"] += 1
            except Exception as exc:
                row.update({"ok": False, "error": str(exc)})
                stats["error"] += 1
            details.append(row)

            if i % 10 == 0 or i == len(series_ids):
                print(
                    f"  progress {i}/{len(series_ids)} ok={stats['ok']} "
                    f"err={stats['error']} trig={stats['triggered']}"
                )

        by_tf: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for row in details:
            tf = _split_timeframe(row["series_id"])
            if not row.get("ok"):
                by_tf[tf]["error"] += 1
                continue
            by_tf[tf]["ok"] += 1
            by_tf[tf]["triggered" if row.get("triggered") else "not_triggered"] += 1

        summary = {
            "round": idx,
            "elapsed_s": round(time.time() - started, 3),
            "total": len(series_ids),
            **{k: int(v) for k, v in stats.items()},
        }
        print("summary", summary)
        rounds_payload.append(
            {
                "summary": summary,
                "by_timeframe": {k: dict(v) for k, v in sorted(by_tf.items())},
                "details": details,
            }
        )

    payload = {
        "generated_at": int(time.time()),
        "transport": args.transport,
        "base_url": args.base_url if args.transport == "live" else None,
        "db_path": str(db_path),
        "rounds": int(args.rounds),
        "series_total": len(series_ids),
        "series_ids": series_ids,
        "results": rounds_payload,
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report saved: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
