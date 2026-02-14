#!/usr/bin/env python3
"""Session context snapshot helper.

Save and restore structured context snapshots for long-running work.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import subprocess
import sys
from typing import Iterable


REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "output" / "context"


def _run(cmd: list[str]) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError as exc:
        return f"(failed to run {' '.join(cmd)}: {exc})"

    text = (result.stdout or "").strip()
    if text:
        return text
    err = (result.stderr or "").strip()
    if err:
        return err
    return "(empty)"


def _normalize_topic(topic: str) -> str:
    cleaned = "-".join(topic.strip().split())
    safe = "".join(ch for ch in cleaned if ch.isalnum() or ch in "-_").strip("-_")
    return safe or "session"


def _split_csv(values: Iterable[str] | None) -> list[str]:
    items: list[str] = []
    if not values:
        return items
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                items.append(part)
    return items


def build_snapshot_markdown(
    *,
    phase: str,
    goal: str,
    next_step: str,
    acceptance: str | None,
    rollback: str | None,
    files: list[str],
    evidence: list[str],
) -> str:
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = _run(["git", "status", "--short"])
    diff_stat = _run(["git", "diff", "--stat"])

    lines = [
        f"# Context Snapshot ({now})",
        "",
        "## 当前阶段",
        f"- {phase}",
        "",
        "## 当前目标",
        f"- {goal}",
        "",
        "## 下一步唯一动作",
        f"- {next_step}",
        "",
        "## 验收命令",
        f"- {acceptance or '待补充'}",
        "",
        "## 回滚方式",
        f"- {rollback or '待补充'}",
        "",
        "## 关键文件路径",
    ]

    if files:
        lines.extend(f"- `{path}`" for path in files)
    else:
        lines.append("- 待补充")

    lines.extend(["", "## 已验证证据"])
    if evidence:
        lines.extend(f"- {item}" for item in evidence)
    else:
        lines.append("- 待补充")

    lines.extend(
        [
            "",
            "## Git Status",
            "```text",
            status,
            "```",
            "",
            "## Git Diff Stat",
            "```text",
            diff_stat,
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def save_snapshot(args: argparse.Namespace) -> int:
    target_dir = pathlib.Path(args.output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    stamp = dt.datetime.now().strftime("%Y-%m-%d-%H%M%S")
    topic = _normalize_topic(args.topic)
    out_path = target_dir / f"{stamp}-{topic}-snapshot.md"

    files = _split_csv(args.files)
    evidence = _split_csv(args.evidence)
    markdown = build_snapshot_markdown(
        phase=args.phase,
        goal=args.goal,
        next_step=args.next_step,
        acceptance=args.acceptance,
        rollback=args.rollback,
        files=files,
        evidence=evidence,
    )
    out_path.write_text(markdown, encoding="utf-8")
    print(out_path)
    return 0


def _latest_snapshot(path: pathlib.Path) -> pathlib.Path | None:
    candidates = sorted(path.glob("*-snapshot.md"))
    return candidates[-1] if candidates else None


def resume_snapshot(args: argparse.Namespace) -> int:
    snapshot = pathlib.Path(args.snapshot) if args.snapshot else _latest_snapshot(pathlib.Path(args.output_dir))
    if snapshot is None:
        print("No snapshot found.", file=sys.stderr)
        return 2
    if not snapshot.exists():
        print(f"Snapshot not found: {snapshot}", file=sys.stderr)
        return 2

    content = snapshot.read_text(encoding="utf-8")
    print(f"Snapshot: {snapshot}")
    print("----")
    max_lines = args.lines
    for idx, line in enumerate(content.splitlines()):
        if idx >= max_lines:
            print("... (truncated)")
            break
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Save/resume context snapshots.")
    sub = parser.add_subparsers(dest="command", required=True)

    save = sub.add_parser("save", help="Save a new context snapshot.")
    save.add_argument("--topic", required=True, help="Short topic label.")
    save.add_argument("--phase", default="执行方案", help="Current workflow phase.")
    save.add_argument("--goal", required=True, help="Current goal.")
    save.add_argument("--next-step", required=True, help="Single next action.")
    save.add_argument("--acceptance", default="", help="Acceptance command or criteria.")
    save.add_argument("--rollback", default="", help="Rollback path.")
    save.add_argument("--files", action="append", help="Key file path(s), repeat or comma separate.")
    save.add_argument("--evidence", action="append", help="Evidence line(s), repeat or comma separate.")
    save.add_argument("--output-dir", default=str(DEFAULT_DIR), help="Snapshot output directory.")
    save.set_defaults(func=save_snapshot)

    resume = sub.add_parser("resume", help="Print snapshot for next-session bootstrap.")
    resume.add_argument("--snapshot", default="", help="Specific snapshot path.")
    resume.add_argument("--output-dir", default=str(DEFAULT_DIR), help="Snapshot directory fallback.")
    resume.add_argument("--lines", type=int, default=60, help="Max lines to print.")
    resume.set_defaults(func=resume_snapshot)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
