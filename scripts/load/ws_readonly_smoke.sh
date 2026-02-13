#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/load/ws_readonly_smoke.sh

Environment overrides (optional):
  WS_SMOKE_BACKEND_BASE=http://127.0.0.1:8000
  WS_SMOKE_WS_URL=ws://127.0.0.1:8000/ws/market
  WS_SMOKE_SERIES_ID=binance:futures:BTC/USDT:1m
  WS_SMOKE_CLIENTS=200
  WS_SMOKE_CONNECT_CONCURRENCY=100
  WS_SMOKE_SINCE=0
  WS_SMOKE_RECEIVE_TIMEOUT_S=8
  WS_SMOKE_HTTP_TIMEOUT_S=8
  WS_SMOKE_MIN_DELIVERY_RATIO=0.95
  WS_SMOKE_TRIGGER_CANDLE_TIME=<epoch-seconds>
  WS_SMOKE_ARTIFACT_ROOT=output/capacity
  WS_SMOKE_RUN_ID=2026-02-13-ws-readonly-smoke

Output artifacts:
  output/capacity/<run_id>/
    - summary.json
    - clients.jsonl
    - metrics_snapshot.json
    - connect_latency_histogram.txt
    - delivery_latency_histogram.txt
    - run.log
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

backend_base="${WS_SMOKE_BACKEND_BASE:-http://127.0.0.1:8000}"
ws_url="${WS_SMOKE_WS_URL:-${backend_base/http/ws}/ws/market}"
series_id="${WS_SMOKE_SERIES_ID:-binance:futures:BTC/USDT:1m}"
clients="${WS_SMOKE_CLIENTS:-200}"
connect_concurrency="${WS_SMOKE_CONNECT_CONCURRENCY:-100}"
since="${WS_SMOKE_SINCE:-0}"
receive_timeout_s="${WS_SMOKE_RECEIVE_TIMEOUT_S:-8}"
http_timeout_s="${WS_SMOKE_HTTP_TIMEOUT_S:-8}"
min_delivery_ratio="${WS_SMOKE_MIN_DELIVERY_RATIO:-0.95}"
artifact_root="${WS_SMOKE_ARTIFACT_ROOT:-output/capacity}"
default_run_id="$(date +%Y-%m-%d-%H%M%S)-ws-readonly-smoke"
run_id="${WS_SMOKE_RUN_ID:-$default_run_id}"
trigger_candle_time="${WS_SMOKE_TRIGGER_CANDLE_TIME:-}"

if [[ -z "$trigger_candle_time" ]]; then
  trigger_candle_time="$(python3 - <<'PY'
import time
now = int(time.time())
print(now - (now % 60))
PY
)"
fi

run_dir="${artifact_root}/${run_id}"
mkdir -p "$run_dir"

cat >"${run_dir}/run_config.env" <<EOF
WS_SMOKE_BACKEND_BASE=${backend_base}
WS_SMOKE_WS_URL=${ws_url}
WS_SMOKE_SERIES_ID=${series_id}
WS_SMOKE_CLIENTS=${clients}
WS_SMOKE_CONNECT_CONCURRENCY=${connect_concurrency}
WS_SMOKE_SINCE=${since}
WS_SMOKE_RECEIVE_TIMEOUT_S=${receive_timeout_s}
WS_SMOKE_HTTP_TIMEOUT_S=${http_timeout_s}
WS_SMOKE_MIN_DELIVERY_RATIO=${min_delivery_ratio}
WS_SMOKE_TRIGGER_CANDLE_TIME=${trigger_candle_time}
WS_SMOKE_ARTIFACT_ROOT=${artifact_root}
WS_SMOKE_RUN_ID=${run_id}
EOF

python3 - "$backend_base" "$ws_url" "$series_id" "$clients" "$connect_concurrency" "$since" "$receive_timeout_s" "$http_timeout_s" "$min_delivery_ratio" "$trigger_candle_time" "$run_dir" <<'PY' | tee "${run_dir}/run.log"
from __future__ import annotations

import asyncio
import json
import math
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import websockets
except Exception as exc:
    raise SystemExit(f"missing_dependency:websockets:{exc}") from exc


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = max(0.0, min(1.0, float(pct))) * float(len(ordered) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return float(ordered[lower])
    weight = rank - float(lower)
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _histogram_text(values: list[float], *, title: str) -> str:
    if not values:
        return f"{title}\n(no data)\n"
    buckets = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000]
    counts: list[tuple[str, int]] = []
    remain = list(values)
    last = 0
    for upper in buckets:
        c = sum(1 for v in remain if last < v <= upper)
        counts.append((f"({last},{upper}]ms", c))
        last = upper
    c_tail = sum(1 for v in remain if v > buckets[-1])
    counts.append((f">{buckets[-1]}ms", c_tail))
    peak = max(c for _, c in counts) or 1
    lines = [title]
    for label, count in counts:
        bar = "#" * max(0, int(round((count / peak) * 40)))
        lines.append(f"{label:>12} | {bar} ({count})")
    return "\n".join(lines) + "\n"


def _post_closed_candle(
    *,
    backend_base: str,
    series_id: str,
    candle_time: int,
    timeout_s: float,
) -> tuple[int, str]:
    payload = {
        "series_id": str(series_id),
        "candle": {
            "candle_time": int(candle_time),
            "open": 100.0,
            "high": 101.0,
            "low": 99.0,
            "close": 100.5,
            "volume": 10.0,
        },
    }
    req = urllib.request.Request(
        f"{backend_base.rstrip('/')}/api/market/ingest/candle_closed",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return int(resp.status), body


def _fetch_metrics_snapshot(*, backend_base: str, timeout_s: float) -> dict:
    url = f"{backend_base.rstrip('/')}/api/market/debug/metrics"
    try:
        with urllib.request.urlopen(url, timeout=float(timeout_s)) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            payload = json.loads(body) if body else {}
            return {"ok": True, "status": int(resp.status), "payload": payload}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": int(exc.code), "error": str(body or exc.reason)}
    except Exception as exc:
        return {"ok": False, "status": None, "error": str(exc)}


async def _run(
    *,
    backend_base: str,
    ws_url: str,
    series_id: str,
    clients: int,
    connect_concurrency: int,
    since: int,
    receive_timeout_s: float,
    http_timeout_s: float,
    min_delivery_ratio: float,
    trigger_candle_time: int,
    run_dir: Path,
) -> int:
    sem = asyncio.Semaphore(max(1, int(connect_concurrency)))
    snapshots: list[dict] = []
    live_sockets: list[tuple[int, object, float]] = []
    opened_at = time.perf_counter()

    async def open_one(client_id: int) -> None:
        started = time.perf_counter()
        try:
            async with sem:
                ws = await websockets.connect(  # type: ignore[attr-defined]
                    ws_url,
                    max_queue=32,
                    ping_interval=20,
                    ping_timeout=20,
                    close_timeout=5,
                )
                await ws.send(
                    json.dumps(
                        {
                            "type": "subscribe",
                            "series_id": str(series_id),
                            "since": int(since),
                            "supports_batch": False,
                        },
                        separators=(",", ":"),
                    )
                )
            connect_ms = (time.perf_counter() - started) * 1000.0
            snapshots.append(
                {
                    "client_id": int(client_id),
                    "connected": True,
                    "connect_ms": round(connect_ms, 3),
                    "deliver_ms": None,
                    "delivered": False,
                    "messages_seen": 0,
                    "error": None,
                }
            )
            live_sockets.append((int(client_id), ws, float(connect_ms)))
        except Exception as exc:
            snapshots.append(
                {
                    "client_id": int(client_id),
                    "connected": False,
                    "connect_ms": None,
                    "deliver_ms": None,
                    "delivered": False,
                    "messages_seen": 0,
                    "error": str(exc),
                }
            )

    await asyncio.gather(*(open_one(i) for i in range(int(clients))))
    connected = len(live_sockets)
    print(f"[ws_readonly_smoke] requested={clients} connected={connected} ws={ws_url}")

    ingest_started = time.perf_counter()
    ingest_status = 0
    ingest_response = ""
    ingest_error = None
    try:
        ingest_status, ingest_response = await asyncio.to_thread(
            _post_closed_candle,
            backend_base=str(backend_base),
            series_id=str(series_id),
            candle_time=int(trigger_candle_time),
            timeout_s=float(http_timeout_s),
        )
    except Exception as exc:
        ingest_error = str(exc)

    async def wait_delivery(client_id: int, ws: object, connect_ms: float) -> dict:
        deadline = time.perf_counter() + float(receive_timeout_s)
        seen = 0
        try:
            while True:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)  # type: ignore[union-attr]
                seen += 1
                if isinstance(raw, bytes):
                    payload = json.loads(raw.decode("utf-8", errors="replace"))
                else:
                    payload = json.loads(str(raw))
                msg_type = str(payload.get("type") or "")
                if msg_type == "error":
                    return {
                        "client_id": int(client_id),
                        "connected": True,
                        "connect_ms": round(connect_ms, 3),
                        "deliver_ms": None,
                        "delivered": False,
                        "messages_seen": int(seen),
                        "error": f"ws_error:{payload.get('code')}:{payload.get('message')}",
                    }
                if msg_type == "candle_closed":
                    candle = payload.get("candle") or {}
                    if int(candle.get("candle_time") or -1) == int(trigger_candle_time):
                        deliver_ms = (time.perf_counter() - ingest_started) * 1000.0
                        return {
                            "client_id": int(client_id),
                            "connected": True,
                            "connect_ms": round(connect_ms, 3),
                            "deliver_ms": round(deliver_ms, 3),
                            "delivered": True,
                            "messages_seen": int(seen),
                            "error": None,
                        }
                if msg_type == "candles_batch":
                    candles = payload.get("candles") or []
                    for item in candles:
                        if int((item or {}).get("candle_time") or -1) == int(trigger_candle_time):
                            deliver_ms = (time.perf_counter() - ingest_started) * 1000.0
                            return {
                                "client_id": int(client_id),
                                "connected": True,
                                "connect_ms": round(connect_ms, 3),
                                "deliver_ms": round(deliver_ms, 3),
                                "delivered": True,
                                "messages_seen": int(seen),
                                "error": None,
                            }
        except Exception as exc:
            return {
                "client_id": int(client_id),
                "connected": True,
                "connect_ms": round(connect_ms, 3),
                "deliver_ms": None,
                "delivered": False,
                "messages_seen": int(seen),
                "error": str(exc),
            }
        return {
            "client_id": int(client_id),
            "connected": True,
            "connect_ms": round(connect_ms, 3),
            "deliver_ms": None,
            "delivered": False,
            "messages_seen": int(seen),
            "error": "timeout_waiting_trigger",
        }

    delivery_results: list[dict] = []
    if connected > 0:
        delivery_results = await asyncio.gather(
            *(wait_delivery(client_id, ws, connect_ms) for client_id, ws, connect_ms in live_sockets)
        )
    by_id: dict[int, dict] = {int(item["client_id"]): item for item in snapshots}
    for item in delivery_results:
        by_id[int(item["client_id"])] = item
    snapshots = [by_id[k] for k in sorted(by_id.keys())]

    for _, ws, _ in live_sockets:
        try:
            await ws.close()  # type: ignore[union-attr]
        except Exception:
            pass

    connect_latencies = [float(item["connect_ms"]) for item in snapshots if item.get("connect_ms") is not None]
    deliver_latencies = [float(item["deliver_ms"]) for item in snapshots if item.get("deliver_ms") is not None]
    delivered = sum(1 for item in snapshots if bool(item.get("delivered")))
    delivery_ratio = (float(delivered) / float(connected)) if connected > 0 else 0.0

    metrics_snapshot = await asyncio.to_thread(
        _fetch_metrics_snapshot,
        backend_base=str(backend_base),
        timeout_s=float(http_timeout_s),
    )

    summary = {
        "backend_base": str(backend_base),
        "ws_url": str(ws_url),
        "series_id": str(series_id),
        "trigger_candle_time": int(trigger_candle_time),
        "requested_clients": int(clients),
        "connected_clients": int(connected),
        "delivered_clients": int(delivered),
        "delivery_ratio": round(float(delivery_ratio), 6),
        "min_delivery_ratio": round(float(min_delivery_ratio), 6),
        "connect_latency_ms": {
            "p50": _percentile(connect_latencies, 0.50),
            "p95": _percentile(connect_latencies, 0.95),
            "max": max(connect_latencies) if connect_latencies else None,
        },
        "delivery_latency_ms": {
            "p50": _percentile(deliver_latencies, 0.50),
            "p95": _percentile(deliver_latencies, 0.95),
            "max": max(deliver_latencies) if deliver_latencies else None,
        },
        "ingest": {
            "status": int(ingest_status),
            "response": str(ingest_response)[:2000],
            "error": ingest_error,
        },
        "metrics_snapshot": {
            "ok": bool(metrics_snapshot.get("ok")),
            "status": metrics_snapshot.get("status"),
        },
        "duration_s": round(time.perf_counter() - opened_at, 3),
    }
    gate_ok = bool(
        int(ingest_status) == 200
        and ingest_error is None
        and float(delivery_ratio) >= float(min_delivery_ratio)
    )
    summary["gate_ok"] = gate_ok

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (run_dir / "clients.jsonl").open("w", encoding="utf-8") as fh:
        for item in snapshots:
            fh.write(json.dumps(item, ensure_ascii=True, sort_keys=True) + "\n")
    (run_dir / "metrics_snapshot.json").write_text(
        json.dumps(metrics_snapshot, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (run_dir / "connect_latency_histogram.txt").write_text(
        _histogram_text(connect_latencies, title="connect latency histogram"),
        encoding="utf-8",
    )
    (run_dir / "delivery_latency_histogram.txt").write_text(
        _histogram_text(deliver_latencies, title="delivery latency histogram"),
        encoding="utf-8",
    )

    print(f"[ws_readonly_smoke] ingest_status={ingest_status} delivery={delivered}/{connected} ratio={delivery_ratio:.4f}")
    print(f"[ws_readonly_smoke] artifacts={run_dir}")
    return 0 if gate_ok else 1


def main() -> int:
    backend_base = str(sys.argv[1])
    ws_url = str(sys.argv[2])
    series_id = str(sys.argv[3])
    clients = int(sys.argv[4])
    connect_concurrency = int(sys.argv[5])
    since = int(sys.argv[6])
    receive_timeout_s = float(sys.argv[7])
    http_timeout_s = float(sys.argv[8])
    min_delivery_ratio = float(sys.argv[9])
    trigger_candle_time = int(sys.argv[10])
    run_dir = Path(sys.argv[11])

    return asyncio.run(
        _run(
            backend_base=backend_base,
            ws_url=ws_url,
            series_id=series_id,
            clients=clients,
            connect_concurrency=connect_concurrency,
            since=since,
            receive_timeout_s=receive_timeout_s,
            http_timeout_s=http_timeout_s,
            min_delivery_ratio=min_delivery_ratio,
            trigger_candle_time=trigger_candle_time,
            run_dir=run_dir,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
PY

