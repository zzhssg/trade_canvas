#!/usr/bin/env python3
"""Checkpointed eval runner with pass@k / pass^k reporting."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess
from dataclasses import dataclass
from typing import Iterable


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL_ROOT = REPO_ROOT / "output" / "evals"


@dataclass
class Attempt:
    timestamp: str
    checkpoint: str
    command: str
    exit_code: int
    duration_ms: int
    passed: bool
    log_path: str
    label: str

    @staticmethod
    def from_dict(data: dict[str, object]) -> "Attempt":
        return Attempt(
            timestamp=str(data.get("timestamp", "")),
            checkpoint=str(data.get("checkpoint", "")),
            command=str(data.get("command", "")),
            exit_code=int(data.get("exit_code", 1)),
            duration_ms=int(data.get("duration_ms", 0)),
            passed=bool(data.get("passed", False)),
            log_path=str(data.get("log_path", "")),
            label=str(data.get("label", "")),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "timestamp": self.timestamp,
            "checkpoint": self.checkpoint,
            "command": self.command,
            "exit_code": self.exit_code,
            "duration_ms": self.duration_ms,
            "passed": self.passed,
            "log_path": self.log_path,
            "label": self.label,
        }


def _checkpoint_dir(name: str) -> pathlib.Path:
    return EVAL_ROOT / name


def _attempts_file(name: str) -> pathlib.Path:
    return _checkpoint_dir(name) / "attempts.jsonl"


def _parse_k(values: str) -> list[int]:
    out: list[int] = []
    for raw in values.split(","):
        raw = raw.strip()
        if not raw:
            continue
        number = int(raw)
        if number <= 0:
            raise ValueError("k must be > 0")
        out.append(number)
    if not out:
        raise ValueError("empty k list")
    return sorted(set(out))


def _read_attempts(name: str) -> list[Attempt]:
    file = _attempts_file(name)
    if not file.exists():
        return []
    attempts: list[Attempt] = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        attempts.append(Attempt.from_dict(json.loads(line)))
    return attempts


def _append_attempt(name: str, attempt: Attempt) -> None:
    directory = _checkpoint_dir(name)
    directory.mkdir(parents=True, exist_ok=True)
    with _attempts_file(name).open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(attempt.to_dict(), ensure_ascii=False) + "\n")


def _window_metric(flags: list[bool], k: int, *, require_all: bool) -> float:
    if len(flags) < k:
        return -1.0
    total = 0
    good = 0
    for idx in range(0, len(flags) - k + 1):
        window = flags[idx : idx + k]
        passed = all(window) if require_all else any(window)
        total += 1
        if passed:
            good += 1
    return good / total if total else -1.0


def _format_ratio(ratio: float) -> str:
    if ratio < 0:
        return "N/A"
    return f"{ratio * 100:.1f}%"


def _report_lines(attempts: list[Attempt], ks: Iterable[int]) -> list[str]:
    flags = [a.passed for a in attempts]
    lines = [
        f"Attempts: {len(attempts)}",
        f"Passed: {sum(1 for f in flags if f)}",
        f"Failed: {sum(1 for f in flags if not f)}",
        "",
        "Metrics:",
    ]
    for k in ks:
        lines.append(f"- pass@{k}: {_format_ratio(_window_metric(flags, k, require_all=False))}")
        lines.append(f"- pass^{k}: {_format_ratio(_window_metric(flags, k, require_all=True))}")
    return lines


def cmd_run(args: argparse.Namespace) -> int:
    checkpoint = args.checkpoint
    directory = _checkpoint_dir(checkpoint)
    directory.mkdir(parents=True, exist_ok=True)

    started = dt.datetime.now()
    stamp = started.strftime("%Y-%m-%d-%H%M%S")
    log_path = directory / f"{stamp}.log"
    command = args.command

    proc = subprocess.run(
        command,
        cwd=REPO_ROOT,
        shell=True,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    ended = dt.datetime.now()
    duration_ms = int((ended - started).total_seconds() * 1000)

    log_content = [
        f"$ {command}",
        "",
        "## stdout",
        proc.stdout or "(empty)",
        "",
        "## stderr",
        proc.stderr or "(empty)",
        "",
        f"exit_code={proc.returncode}",
        f"duration_ms={duration_ms}",
    ]
    log_path.write_text("\n".join(log_content), encoding="utf-8")

    attempt = Attempt(
        timestamp=ended.isoformat(timespec="seconds"),
        checkpoint=checkpoint,
        command=command,
        exit_code=proc.returncode,
        duration_ms=duration_ms,
        passed=proc.returncode == 0,
        log_path=str(log_path.relative_to(REPO_ROOT)),
        label=args.label or "",
    )
    _append_attempt(checkpoint, attempt)

    attempts = _read_attempts(checkpoint)
    ks = _parse_k(args.k)

    print(f"Checkpoint: {checkpoint}")
    print(f"Command: {command}")
    print(f"Result: {'PASS' if attempt.passed else 'FAIL'} (exit={attempt.exit_code})")
    print(f"Log: {attempt.log_path}")
    print("")
    for line in _report_lines(attempts, ks):
        print(line)

    return proc.returncode


def cmd_report(args: argparse.Namespace) -> int:
    attempts = _read_attempts(args.checkpoint)
    ks = _parse_k(args.k)
    print(f"Checkpoint: {args.checkpoint}")
    print("")
    for line in _report_lines(attempts, ks):
        print(line)
    if attempts:
        latest = attempts[-1]
        print("")
        print(f"Latest: {latest.timestamp} | {'PASS' if latest.passed else 'FAIL'} | {latest.log_path}")
    return 0


def cmd_list(_: argparse.Namespace) -> int:
    EVAL_ROOT.mkdir(parents=True, exist_ok=True)
    items = sorted(p for p in EVAL_ROOT.iterdir() if p.is_dir())
    if not items:
        print("No checkpoints.")
        return 0
    for item in items:
        attempts = _read_attempts(item.name)
        passed = sum(1 for a in attempts if a.passed)
        print(f"- {item.name}: attempts={len(attempts)} passed={passed}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run/report checkpointed eval metrics.")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run command and append one attempt.")
    run.add_argument("--checkpoint", required=True, help="Checkpoint name.")
    run.add_argument("--command", required=True, help="Shell command to execute.")
    run.add_argument("--label", default="", help="Optional attempt label.")
    run.add_argument("--k", default="1,3,5", help="k set for pass@k/pass^k.")
    run.set_defaults(func=cmd_run)

    report = sub.add_parser("report", help="Report pass metrics for a checkpoint.")
    report.add_argument("--checkpoint", required=True, help="Checkpoint name.")
    report.add_argument("--k", default="1,3,5", help="k set for pass@k/pass^k.")
    report.set_defaults(func=cmd_report)

    listing = sub.add_parser("list", help="List all checkpoints.")
    listing.set_defaults(func=cmd_list)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
