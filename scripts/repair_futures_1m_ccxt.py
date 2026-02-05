#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_SERIES_IDS = (
    "binance:futures:BTC/USDT:1m",
    "binance:futures:ETH/USDT:1m",
)


@dataclass(frozen=True)
class BackfillResult:
    series_id: str
    fetched_rows: int
    written_rows: int
    head_time: int | None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _import_backend() -> dict[str, Any]:
    root = _repo_root()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "backend"))

    from backend.app.config import load_settings  # noqa: WPS433
    from backend.app.factor_orchestrator import FactorOrchestrator  # noqa: WPS433
    from backend.app.factor_store import FactorStore  # noqa: WPS433
    from backend.app.overlay_orchestrator import OverlayOrchestrator  # noqa: WPS433
    from backend.app.overlay_store import OverlayStore  # noqa: WPS433
    from backend.app.series_id import parse_series_id  # noqa: WPS433
    from backend.app.schemas import CandleClosed  # noqa: WPS433
    from backend.app.sqlite_util import connect as sqlite_connect  # noqa: WPS433
    from backend.app.store import CandleStore  # noqa: WPS433
    from backend.app.timeframe import timeframe_to_seconds  # noqa: WPS433

    return {
        "load_settings": load_settings,
        "FactorOrchestrator": FactorOrchestrator,
        "FactorStore": FactorStore,
        "OverlayOrchestrator": OverlayOrchestrator,
        "OverlayStore": OverlayStore,
        "CandleStore": CandleStore,
        "CandleClosed": CandleClosed,
        "parse_series_id": parse_series_id,
        "timeframe_to_seconds": timeframe_to_seconds,
        "sqlite_connect": sqlite_connect,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="修复合约 BTC/ETH 1m 数据污染：purge + ccxt 回补（closed-only）+ 重建派生表。")
    p.add_argument("--db-path", default="", help="覆盖 DB 路径（默认读取 backend settings 的 db_path）。")
    p.add_argument("--limit", type=int, default=2000, help="回补 1m closed candles 条数（默认 2000）。")
    p.add_argument("--batch-limit", type=int, default=1000, help="ccxt fetch_ohlcv 批大小（默认 1000）。")
    p.add_argument("--grace-s", type=int, default=5, help="收盘判定 grace window 秒（默认 5）。")
    p.add_argument("--timeout-ms", type=int, default=20000, help="ccxt HTTP timeout ms（默认 20000）。")
    p.add_argument("--max-attempts", type=int, default=5, help="网络重试次数（默认 5）。")
    p.add_argument("--dry-run", action="store_true", help="仅打印将要执行的动作，不修改 DB。")
    p.add_argument("--no-backup", action="store_true", help="不生成 market.db.bak.<ts> 备份（不推荐）。")
    p.add_argument("--series-id", action="append", default=[], help="可重复指定，默认修复 BTC/ETH futures 1m。")
    return p.parse_args(argv)


def _backup_db(db_path: Path) -> Path:
    ts = int(time.time())
    backup_path = db_path.with_name(f"{db_path.name}.bak.{ts}")
    shutil.copy2(db_path, backup_path)
    for suffix in ("-wal", "-shm"):
        p = Path(str(db_path) + suffix)
        if p.exists():
            shutil.copy2(p, Path(str(backup_path) + suffix))
    return backup_path


def _restore_db(backup_path: Path, db_path: Path) -> None:
    shutil.copy2(backup_path, db_path)
    for suffix in ("-wal", "-shm"):
        b = Path(str(backup_path) + suffix)
        if b.exists():
            shutil.copy2(b, Path(str(db_path) + suffix))


def _purge_series_in_conn(conn, *, series_id: str) -> dict[str, int]:
    # 仅做 series 维度清理，避免误伤其它表/数据。
    existing = {
        str(r[0])
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        if r and r[0]
    }
    tables = [
        ("candles", "series_id"),
        ("factor_events", "series_id"),
        ("factor_series_state", "series_id"),
        ("overlay_instruction_versions", "series_id"),
        ("overlay_series_state", "series_id"),
        # historical v0 plot tables (removed from the codebase; delete only if they exist in the DB)
        ("plot_overlay_events", "series_id"),
        ("plot_line_points", "series_id"),
        ("plot_series_state", "series_id"),
    ]
    out: dict[str, int] = {}
    for table, col in tables:
        if table not in existing:
            out[table] = 0
            continue
        cur = conn.execute(f"DELETE FROM {table} WHERE {col} = ?", (str(series_id),))
        out[table] = int(cur.rowcount or 0)
    return out


def _ccxt_exchange(series, *, timeout_ms: int):
    import ccxt

    opts = {"enableRateLimit": True, "timeout": max(1000, int(timeout_ms))}
    if series.market == "spot":
        return ccxt.binance(opts)
    if series.market == "futures":
        return ccxt.binanceusdm(opts)
    raise ValueError(f"unsupported market: {series.market!r}")


def _ccxt_symbol(series) -> str:
    if series.market != "futures":
        return series.symbol
    if ":" in series.symbol:
        return series.symbol
    if "/" not in series.symbol:
        return series.symbol
    base, quote = series.symbol.split("/", 1)
    base = base.strip()
    quote = quote.strip()
    return f"{base}/{quote}:{quote}" if base and quote else series.symbol


def _rows_to_closed(
    rows: list,
    *,
    timeframe_s: int,
    now_s: int,
    grace_s: int,
    CandleClosed,
) -> tuple[list, int | None]:
    max_open_s: int | None = None
    out: list = []
    tf_s = int(timeframe_s)
    for row in rows or []:
        try:
            open_s = int(int(row[0]) // 1000)
        except Exception:
            continue
        if open_s <= 0:
            continue
        max_open_s = open_s if max_open_s is None else max(max_open_s, open_s)

        if open_s + tf_s > int(now_s) - int(grace_s):
            continue

        try:
            o, h, l, c, v = float(row[1]), float(row[2]), float(row[3]), float(row[4]), float(row[5])
        except Exception:
            continue
        out.append(CandleClosed(candle_time=open_s, open=o, high=h, low=l, close=c, volume=v))

    if not out:
        return [], max_open_s
    out.sort(key=lambda x: int(x.candle_time))
    deduped: list = []
    last_t: int | None = None
    for c in out:
        t = int(c.candle_time)
        if last_t is not None and t == last_t:
            deduped[-1] = c
        else:
            deduped.append(c)
            last_t = t
    return deduped, max_open_s


def _merge_tail(existing: list, incoming: list, *, limit: int) -> list:
    out = list(existing)
    last_time = int(out[-1].candle_time) if out else None
    for c in incoming:
        t = int(c.candle_time)
        if last_time is not None and t < last_time:
            continue
        if out and int(out[-1].candle_time) == t:
            out[-1] = c
        else:
            out.append(c)
            last_time = t
    if limit > 0 and len(out) > limit:
        out = out[-limit:]
    return out


def _fetch_with_retry(exchange, *, symbol: str, timeframe: str, since_ms: int | None, limit: int, max_attempts: int) -> list:
    backoff_s = 0.5
    last_err: Exception | None = None
    for attempt in range(1, max(1, int(max_attempts)) + 1):
        try:
            return list(exchange.fetch_ohlcv(symbol, timeframe, since_ms, int(limit)) or [])
        except Exception as e:
            last_err = e
            if attempt >= int(max_attempts):
                break
            time.sleep(backoff_s)
            backoff_s = min(5.0, backoff_s * 1.8)
    raise last_err if last_err is not None else RuntimeError("fetch_ohlcv_failed")


def backfill_via_ccxt(
    *,
    series_id: str,
    db_path: Path,
    limit: int,
    batch_limit: int,
    grace_s: int,
    timeout_ms: int,
    max_attempts: int,
    backend: dict[str, Any],
) -> BackfillResult:
    parse_series_id = backend["parse_series_id"]
    timeframe_to_seconds = backend["timeframe_to_seconds"]
    CandleClosed = backend["CandleClosed"]
    CandleStore = backend["CandleStore"]

    series = parse_series_id(series_id)
    tf_s = int(timeframe_to_seconds(series.timeframe))
    if tf_s <= 0:
        raise ValueError("invalid timeframe")

    store = CandleStore(db_path=db_path)
    exchange = _ccxt_exchange(series, timeout_ms=int(timeout_ms))
    symbol = _ccxt_symbol(series)

    now_s = int(time.time())
    since_ms: int | None = int((now_s - (int(limit) + 10) * tf_s) * 1000)
    cursor_ms = since_ms

    fetched = 0
    tail: list = []

    try:
        while True:
            now_s = int(time.time())
            rows = _fetch_with_retry(
                exchange,
                symbol=symbol,
                timeframe=series.timeframe,
                since_ms=cursor_ms,
                limit=int(batch_limit),
                max_attempts=int(max_attempts),
            )
            fetched += len(rows)

            closed, max_open_s = _rows_to_closed(
                rows,
                timeframe_s=tf_s,
                now_s=now_s,
                grace_s=grace_s,
                CandleClosed=CandleClosed,
            )
            if closed:
                tail = _merge_tail(tail, closed, limit=int(limit))

            if not rows:
                break
            if max_open_s is None:
                break
            next_ms = int(max_open_s * 1000)
            if cursor_ms is not None and next_ms <= int(cursor_ms):
                break
            cursor_ms = next_ms
            if len(rows) < int(batch_limit) and len(tail) >= int(limit):
                break
    finally:
        try:
            close = getattr(exchange, "close", None)
            if callable(close):
                close()
        except Exception:
            pass

    if tail:
        with store.connect() as conn:
            store.upsert_many_closed_in_conn(conn, series_id, tail)
            conn.commit()

    head = store.head_time(series_id)
    return BackfillResult(series_id=str(series_id), fetched_rows=int(fetched), written_rows=int(len(tail)), head_time=head)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    backend = _import_backend()
    settings = backend["load_settings"]()

    series_ids = list(args.series_id) if args.series_id else list(DEFAULT_SERIES_IDS)
    db_path = Path(args.db_path).expanduser().resolve() if args.db_path else settings.db_path.resolve()

    print(f"db_path={db_path}")
    print(f"series_ids={series_ids}")
    print(
        f"limit={args.limit} batch_limit={args.batch_limit} grace_s={args.grace_s} "
        f"timeout_ms={args.timeout_ms} max_attempts={args.max_attempts} dry_run={args.dry_run}"
    )

    if args.dry_run:
        print("[dry-run] would backup db (unless --no-backup)")
        print("[dry-run] would purge series rows (candles/factor/overlay/plot)")
        print("[dry-run] would ccxt backfill and rebuild orchestrators")
        return 0

    if not db_path.exists():
        print(f"ERROR: db not found: {db_path}", file=sys.stderr)
        return 2

    backup_path: Path | None = None
    if not args.no_backup:
        backup_path = _backup_db(db_path)
        print(f"backup={backup_path}")

    sqlite_connect = backend["sqlite_connect"]
    CandleStore = backend["CandleStore"]
    FactorStore = backend["FactorStore"]
    OverlayStore = backend["OverlayStore"]
    FactorOrchestrator = backend["FactorOrchestrator"]
    OverlayOrchestrator = backend["OverlayOrchestrator"]

    try:
        with sqlite_connect(db_path) as conn:
            for sid in series_ids:
                print(f"\n== purge series_id={sid} ==")
                purged = _purge_series_in_conn(conn, series_id=str(sid))
                print(f"purged={purged}")
            conn.commit()

        for sid in series_ids:
            print(f"\n== ccxt backfill series_id={sid} ==")
            result = backfill_via_ccxt(
                series_id=str(sid),
                db_path=db_path,
                limit=int(args.limit),
                batch_limit=int(args.batch_limit),
                grace_s=int(args.grace_s),
                timeout_ms=int(args.timeout_ms),
                max_attempts=int(args.max_attempts),
                backend=backend,
            )
            print(f"backfill:fetched_rows={result.fetched_rows} written_rows={result.written_rows} head_time={result.head_time}")
            if result.head_time is None:
                raise RuntimeError(f"backfill_empty:{sid}")

            candle_store = CandleStore(db_path=db_path)
            factor_store = FactorStore(db_path=db_path)
            overlay_store = OverlayStore(db_path=db_path)

            factor_orchestrator = FactorOrchestrator(candle_store=candle_store, factor_store=factor_store)
            overlay_orchestrator = OverlayOrchestrator(
                candle_store=candle_store,
                factor_store=factor_store,
                overlay_store=overlay_store,
            )

            up_to = int(result.head_time)
            print(f"rebuild:series_id={sid} up_to={up_to}")
            factor_orchestrator.ingest_closed(series_id=str(sid), up_to_candle_time=up_to)
            overlay_orchestrator.ingest_closed(series_id=str(sid), up_to_candle_time=up_to)

        print("\nDONE")
        if backup_path is not None:
            print(f"rollback: restore {backup_path} -> {db_path}")
        return 0
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        if backup_path is not None:
            print("rollback: restoring db from backup...", file=sys.stderr)
            _restore_db(backup_path, db_path)
            print(f"rollback: restored {backup_path} -> {db_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
