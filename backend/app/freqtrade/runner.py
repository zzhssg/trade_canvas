from __future__ import annotations

import asyncio
import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from ..core.flags import resolve_env_float
from .runner_commands import (
    BacktestCommandRequest,
    build_backtest_command,
    build_list_strategies_command,
    build_runner_env,
)


_STRATEGY_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class FreqtradeExecResult:
    ok: bool
    exit_code: int
    duration_ms: int
    command: list[str]
    stdout: str
    stderr: str


@dataclass(frozen=True)
class BacktestRunRequest:
    freqtrade_bin: str
    userdir: Path | None
    cwd: Path | None = None
    config_path: Path | None = None
    datadir: Path | None = None
    strategy_name: str = ""
    pair: str = ""
    timeframe: str = ""
    timerange: str | None = None
    strategy_path: Path | None = None
    timeout_s: float | None = None
    export_dir: Path | None = None
    export: str | None = None
    extra_env: dict[str, str] | None = None


def validate_strategy_name(strategy_name: str) -> bool:
    return bool(_STRATEGY_NAME_RE.match(strategy_name))


def _default_timeout_s() -> float:
    return resolve_env_float("TRADE_CANVAS_FREQTRADE_SUBPROCESS_TIMEOUT_S", fallback=120.0, minimum=1.0)


async def _run_subprocess(
    command: list[str],
    *,
    cwd: Path | None,
    env: dict[str, str],
    timeout_s: float,
) -> tuple[int, str, str]:
    start_new_session = True
    try:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            start_new_session=start_new_session,
        )
    except TypeError:
        start_new_session = False
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
        )

    async def terminate() -> None:
        if proc.returncode is not None:
            return
        try:
            if start_new_session and proc.pid is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except Exception:
                    proc.terminate()
            else:
                proc.terminate()
        except Exception:
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=2.0)
            return
        except Exception:
            pass
        try:
            if start_new_session and proc.pid is not None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
            else:
                proc.kill()
        except Exception:
            pass

    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        await terminate()
        return 124, "", f"timeout after {timeout_s:.0f}s"
    except asyncio.CancelledError:
        await terminate()
        raise

    stdout = out_b.decode(errors="replace") if isinstance(out_b, (bytes, bytearray)) else str(out_b or "")
    stderr = err_b.decode(errors="replace") if isinstance(err_b, (bytes, bytearray)) else str(err_b or "")
    return int(proc.returncode or 0), stdout, stderr


def list_strategies(
    *,
    freqtrade_bin: str,
    userdir: Path | None,
    cwd: Path | None = None,
    recursive: bool = True,
    strategy_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> FreqtradeExecResult:
    command = build_list_strategies_command(
        userdir=userdir,
        recursive=recursive,
        strategy_path=strategy_path,
    )

    start = time.monotonic()
    env = build_runner_env(cwd=cwd, extra_env=extra_env)
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd is not None else None,
        env=env,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    ok = proc.returncode == 0
    return FreqtradeExecResult(
        ok=ok,
        exit_code=int(proc.returncode),
        duration_ms=duration_ms,
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def parse_strategy_list(stdout: str) -> list[str]:
    strategies: list[str] = []
    for raw in stdout.splitlines():
        line = raw.strip()
        if not line:
            continue
        if validate_strategy_name(line):
            strategies.append(line)
    return sorted(set(strategies))


async def list_strategies_async(
    *,
    freqtrade_bin: str,
    userdir: Path | None,
    cwd: Path | None = None,
    recursive: bool = True,
    strategy_path: Path | None = None,
    timeout_s: float | None = None,
    extra_env: dict[str, str] | None = None,
) -> FreqtradeExecResult:
    command = build_list_strategies_command(
        userdir=userdir,
        recursive=recursive,
        strategy_path=strategy_path,
    )

    start = time.monotonic()
    env = build_runner_env(cwd=cwd, extra_env=extra_env)

    rc, stdout, stderr = await _run_subprocess(
        command,
        cwd=cwd,
        env=env,
        timeout_s=float(timeout_s if timeout_s is not None else _default_timeout_s()),
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    ok = rc == 0
    return FreqtradeExecResult(
        ok=ok,
        exit_code=int(rc),
        duration_ms=duration_ms,
        command=command,
        stdout=stdout,
        stderr=stderr,
    )


def run_backtest(request: BacktestRunRequest) -> FreqtradeExecResult:
    if not validate_strategy_name(request.strategy_name):
        raise ValueError("Invalid strategy name")

    command = build_backtest_command(
        BacktestCommandRequest(
            userdir=request.userdir,
            config_path=request.config_path,
            datadir=request.datadir,
            strategy_name=request.strategy_name,
            pair=request.pair,
            timeframe=request.timeframe,
            timerange=request.timerange,
            strategy_path=request.strategy_path,
            export_dir=request.export_dir,
            export=request.export,
        )
    )

    start = time.monotonic()
    env = build_runner_env(cwd=request.cwd, extra_env=request.extra_env)
    proc = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=str(request.cwd) if request.cwd is not None else None,
        env=env,
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    ok = proc.returncode == 0
    return FreqtradeExecResult(
        ok=ok,
        exit_code=int(proc.returncode),
        duration_ms=duration_ms,
        command=command,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


async def run_backtest_async(request: BacktestRunRequest) -> FreqtradeExecResult:
    if not validate_strategy_name(request.strategy_name):
        raise ValueError("Invalid strategy name")

    command = build_backtest_command(
        BacktestCommandRequest(
            userdir=request.userdir,
            config_path=request.config_path,
            datadir=request.datadir,
            strategy_name=request.strategy_name,
            pair=request.pair,
            timeframe=request.timeframe,
            timerange=request.timerange,
            strategy_path=request.strategy_path,
            export_dir=request.export_dir,
            export=request.export,
        )
    )

    start = time.monotonic()
    env = build_runner_env(cwd=request.cwd, extra_env=request.extra_env)

    rc, stdout, stderr = await _run_subprocess(
        command,
        cwd=request.cwd,
        env=env,
        timeout_s=float(request.timeout_s if request.timeout_s is not None else _default_timeout_s()),
    )
    duration_ms = int((time.monotonic() - start) * 1000)
    ok = rc == 0
    return FreqtradeExecResult(
        ok=ok,
        exit_code=int(rc),
        duration_ms=duration_ms,
        command=command,
        stdout=stdout,
        stderr=stderr,
    )
