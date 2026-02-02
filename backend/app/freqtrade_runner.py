from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
import os


_STRATEGY_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class FreqtradeExecResult:
    ok: bool
    exit_code: int
    duration_ms: int
    command: list[str]
    stdout: str
    stderr: str


def validate_strategy_name(strategy_name: str) -> bool:
    return bool(_STRATEGY_NAME_RE.match(strategy_name))


def list_strategies(
    *,
    freqtrade_bin: str,
    userdir: Path | None,
    cwd: Path | None = None,
    recursive: bool = True,
    strategy_path: Path | None = None,
) -> FreqtradeExecResult:
    command = [
        freqtrade_bin,
        "list-strategies",
        "-1",
        "--logfile",
        "/dev/null",
        "--no-color",
    ]
    if userdir is not None:
        command.extend(["--userdir", str(userdir)])
    if strategy_path is not None:
        command.extend(["--strategy-path", str(strategy_path)])
    if recursive:
        command.append("--recursive-strategy-search")

    start = time.monotonic()
    env = os.environ.copy()
    if cwd is not None:
        env["PYTHONPATH"] = f"{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
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


def run_backtest(
    *,
    freqtrade_bin: str,
    userdir: Path | None,
    cwd: Path | None = None,
    config_path: Path | None,
    strategy_name: str,
    pair: str,
    timeframe: str,
    timerange: str | None = None,
    strategy_path: Path | None = None,
) -> FreqtradeExecResult:
    if not validate_strategy_name(strategy_name):
        raise ValueError("Invalid strategy name")

    command = [
        freqtrade_bin,
        "backtesting",
        "--strategy",
        strategy_name,
        "--logfile",
        "/dev/null",
        "--no-color",
        "--timeframe",
        timeframe,
        "--pairs",
        pair,
    ]
    if userdir is not None:
        command.extend(["--userdir", str(userdir)])
    if strategy_path is not None:
        command.extend(["--strategy-path", str(strategy_path)])
    if config_path is not None:
        command.extend(["-c", str(config_path)])
    if timerange:
        command.extend(["--timerange", timerange])

    start = time.monotonic()
    env = os.environ.copy()
    if cwd is not None:
        env["PYTHONPATH"] = f"{cwd}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)
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
