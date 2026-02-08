from __future__ import annotations

import asyncio
import os
import queue
import threading
from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class _Job:
    loop: asyncio.AbstractEventLoop
    fut: asyncio.Future
    fn: Callable[[], Any]


_q: queue.Queue[_Job] = queue.Queue()
_started = False
_start_lock = threading.Lock()


def _dispatch_future(
    *,
    loop: asyncio.AbstractEventLoop,
    fut: asyncio.Future,
    value: Any = None,
    error: BaseException | None = None,
) -> None:
    if fut.cancelled() or fut.done() or loop.is_closed():
        return

    def _apply() -> None:
        if fut.cancelled() or fut.done():
            return
        if error is not None:
            fut.set_exception(error)
        else:
            fut.set_result(value)

    try:
        loop.call_soon_threadsafe(_apply)
    except RuntimeError:
        return


def _worker() -> None:
    while True:
        job = _q.get()
        try:
            if job.fut.cancelled():
                continue
            try:
                out = job.fn()
            except BaseException as e:
                _dispatch_future(loop=job.loop, fut=job.fut, error=e)
            else:
                _dispatch_future(loop=job.loop, fut=job.fut, value=out)
        finally:
            _q.task_done()


def _max_workers() -> int:
    raw = (os.environ.get("TRADE_CANVAS_BLOCKING_WORKERS") or "").strip()
    if not raw:
        return 8
    try:
        return max(1, int(raw))
    except ValueError:
        return 8


def _ensure_started() -> None:
    global _started
    if _started:
        return
    with _start_lock:
        if _started:
            return
        for i in range(_max_workers()):
            t = threading.Thread(target=_worker, name=f"tc-blocking-{i}", daemon=True)
            t.start()
        _started = True


async def run_blocking(fn: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    """
    Run a blocking callable without blocking the asyncio event loop.

    - Uses daemon worker threads so that a stuck blocking call won't prevent process exit (Ctrl+C).
    - Bounds concurrency via TRADE_CANVAS_BLOCKING_WORKERS (default 8).
    """
    _ensure_started()
    loop = asyncio.get_running_loop()
    fut = loop.create_future()

    def call() -> Any:
        return fn(*args, **kwargs)

    _q.put(_Job(loop=loop, fut=fut, fn=call))
    return await fut
