#!/usr/bin/env python3
"""Codex 子会话编排：fan-out 执行并汇总 callback 结果。"""
from __future__ import annotations
import argparse
import concurrent.futures
import datetime as dt
import json
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
DEFAULT_OUTPUT_ROOT = Path("output/subagents")
DEFAULT_TEMPLATE = {
    "run_name": "example-subagent-run",
    "max_parallel": 2,
    "defaults": {
        "cwd": ".",
        "model": None,
        "profile": None,
        "sandbox": None,
        "skip_git_repo_check": False,
        "timeout_sec": 1200,
        "extra_args": [],
    },
    "tasks": [
        {
            "id": "docs-agent",
            "prompt": "只更新 docs/core/agent-workflow.md 的 docs 段落，不修改业务代码。",
            "cwd": ".",
            "extra_args": [],
        },
        {
            "id": "test-agent",
            "prompt": "运行 pytest -q 并总结失败用例，不要修改代码。",
            "cwd": ".",
            "extra_args": [],
        },
    ],
}
@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    prompt: str
    cwd: Path
    model: str | None
    profile: str | None
    sandbox: str | None
    skip_git_repo_check: bool
    timeout_sec: int | None
    extra_args: list[str]
def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"spec 文件不存在: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"spec 不是合法 JSON: {path} ({exc})") from exc
    if not isinstance(data, dict):
        raise ValueError("spec 根节点必须是对象")
    return data
def pick(raw: dict[str, Any], defaults: dict[str, Any], key: str) -> Any:
    return raw[key] if key in raw else defaults.get(key)
def parse_task(raw: dict[str, Any], defaults: dict[str, Any]) -> TaskSpec:
    task_id = str(raw.get("id", "")).strip()
    prompt = str(raw.get("prompt", "")).strip()
    if not task_id:
        raise ValueError("task.id 不能为空")
    if not prompt:
        raise ValueError(f"task({task_id}) prompt 不能为空")
    extra_args = pick(raw, defaults, "extra_args") or []
    if not isinstance(extra_args, list) or any(not isinstance(v, str) for v in extra_args):
        raise ValueError(f"task({task_id}) extra_args 必须是 string 数组")
    timeout_raw = pick(raw, defaults, "timeout_sec")
    timeout_sec: int | None = None
    if timeout_raw not in (None, ""):
        timeout_sec = int(timeout_raw)
        if timeout_sec <= 0:
            raise ValueError(f"task({task_id}) timeout_sec 必须 > 0")
    return TaskSpec(
        task_id=task_id,
        prompt=prompt,
        cwd=Path(str(pick(raw, defaults, "cwd") or ".")).expanduser().resolve(),
        model=pick(raw, defaults, "model"),
        profile=pick(raw, defaults, "profile"),
        sandbox=pick(raw, defaults, "sandbox"),
        skip_git_repo_check=bool(pick(raw, defaults, "skip_git_repo_check")),
        timeout_sec=timeout_sec,
        extra_args=list(extra_args),
    )
def load_spec(spec_path: Path) -> tuple[str, int, list[TaskSpec]]:
    data = load_json(spec_path)
    run_name = str(data.get("run_name", spec_path.stem)).strip() or spec_path.stem
    max_parallel = int(data.get("max_parallel", 1))
    if max_parallel <= 0:
        raise ValueError("max_parallel 必须 > 0")
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ValueError("defaults 必须是对象")
    raw_tasks = data.get("tasks")
    if not isinstance(raw_tasks, list) or not raw_tasks:
        raise ValueError("tasks 必须是非空数组")
    if any(not isinstance(item, dict) for item in raw_tasks):
        raise ValueError("tasks 中每个元素都必须是对象")
    tasks = [parse_task(item, defaults) for item in raw_tasks]
    ids = [t.task_id for t in tasks]
    if len(ids) != len(set(ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"task.id 不允许重复: {dup}")
    return run_name, max_parallel, tasks
def parse_usage(events_path: Path) -> dict[str, int]:
    usage: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    if not events_path.exists():
        return usage
    for line in events_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("type") != "turn.completed":
            continue
        raw_usage = payload.get("usage") or {}
        for key in usage:
            value = raw_usage.get(key)
            if isinstance(value, int) and value >= 0:
                usage[key] = value
    return usage
def build_command(codex_bin: str, task: TaskSpec, last_message_path: Path) -> list[str]:
    cmd = [codex_bin, "exec", "--json", "-o", str(last_message_path), "--cd", str(task.cwd)]
    if task.model:
        cmd.extend(["--model", str(task.model)])
    if task.profile:
        cmd.extend(["--profile", str(task.profile)])
    if task.sandbox:
        cmd.extend(["--sandbox", str(task.sandbox)])
    if task.skip_git_repo_check:
        cmd.append("--skip-git-repo-check")
    cmd.extend(task.extra_args)
    cmd.append(task.prompt)
    return cmd
def run_task(codex_bin: str, task: TaskSpec, run_dir: Path) -> dict[str, Any]:
    task_dir = run_dir / task.task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    events_path = task_dir / "events.jsonl"
    stderr_path = task_dir / "stderr.log"
    message_path = task_dir / "last_message.txt"
    command = build_command(codex_bin, task, message_path)
    (task_dir / "command.sh").write_text(" ".join(shlex.quote(p) for p in command) + "\n", encoding="utf-8")
    started = time.monotonic()
    started_at = utc_now()
    timed_out = False
    exit_code = -1
    with events_path.open("w", encoding="utf-8") as out, stderr_path.open("w", encoding="utf-8") as err:
        proc = subprocess.Popen(command, stdout=out, stderr=err, text=True)
        try:
            exit_code = proc.wait(timeout=task.timeout_sec)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            proc.wait()
            exit_code = 124
    preview = ""
    if message_path.exists():
        preview = message_path.read_text(encoding="utf-8", errors="ignore").strip()
    result = {
        "task_id": task.task_id,
        "status": "success" if exit_code == 0 and not timed_out else "failed",
        "exit_code": exit_code,
        "timed_out": timed_out,
        "started_at": started_at,
        "ended_at": utc_now(),
        "duration_sec": round(time.monotonic() - started, 3),
        "cwd": str(task.cwd),
        "paths": {
            "task_dir": str(task_dir),
            "events": str(events_path),
            "stderr": str(stderr_path),
            "last_message": str(message_path),
            "command": str(task_dir / "command.sh"),
        },
        "usage": parse_usage(events_path),
        "last_message_preview": preview[:400],
    }
    (task_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result
def write_report(summary: dict[str, Any], report_path: Path) -> None:
    lines = [
        f"# Subagent Run Report: {summary['run_name']}",
        "",
        f"- run_id: `{summary['run_id']}`",
        f"- started_at: `{summary['started_at']}`",
        f"- ended_at: `{summary['ended_at']}`",
        f"- duration_sec: `{summary['duration_sec']}`",
        f"- max_parallel: `{summary['max_parallel']}`",
        f"- success: `{summary['success_count']}` / `{summary['task_count']}`",
        "",
        "| task_id | status | exit_code | duration_sec | last_message_preview |",
        "|---|---:|---:|---:|---|",
    ]
    for item in summary["tasks"]:
        preview = str(item.get("last_message_preview", "")).replace("|", " ").replace("\n", " ").strip()
        if len(preview) > 80:
            preview = preview[:77] + "..."
        lines.append(
            f"| {item['task_id']} | {item['status']} | {item['exit_code']} | {item['duration_sec']} | {preview} |"
        )
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
def run_orchestrator(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec).expanduser().resolve()
    run_name, spec_parallel, tasks = load_spec(spec_path)
    max_parallel = max(1, int(args.max_parallel if args.max_parallel is not None else spec_parallel))
    run_id = args.run_id or dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.output_root).expanduser().resolve() / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    started_at = utc_now()
    started = time.monotonic()
    results: list[dict[str, Any]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = {pool.submit(run_task, args.codex_bin, task, run_dir): task.task_id for task in tasks}
        for future in concurrent.futures.as_completed(futures):
            task_id = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "task_id": task_id,
                    "status": "failed",
                    "exit_code": -1,
                    "duration_sec": 0.0,
                    "last_message_preview": f"orchestrator error: {exc}",
                }
            results.append(result)
            print(f"[callback] task={result['task_id']} status={result['status']} exit={result.get('exit_code', -1)} duration={result.get('duration_sec', 0.0)}s")
    results.sort(key=lambda x: x["task_id"])
    ok = sum(1 for r in results if r.get("status") == "success")
    summary = {
        "run_id": run_id,
        "run_name": run_name,
        "spec_path": str(spec_path),
        "output_root": str(Path(args.output_root).expanduser().resolve()),
        "started_at": started_at,
        "ended_at": utc_now(),
        "duration_sec": round(time.monotonic() - started, 3),
        "max_parallel": max_parallel,
        "task_count": len(results),
        "success_count": ok,
        "failed_count": len(results) - ok,
        "tasks": results,
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report_path = run_dir / "summary.md"
    write_report(summary, report_path)
    print(f"[report] summary_json={summary_path}")
    print(f"[report] summary_md={report_path}")
    print(f"[report] overall={'success' if ok == len(results) else 'failed'}")
    return 0 if ok == len(results) else 1
def write_template(path: Path) -> int:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(DEFAULT_TEMPLATE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"template written: {path}")
    return 0
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Subagent orchestration for Codex sessions")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run child codex sessions from spec")
    run.add_argument("--spec", required=True, help="JSON spec path")
    run.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help="directory for run artifacts")
    run.add_argument("--run-id", default=None, help="override run id")
    run.add_argument("--max-parallel", type=int, default=None, help="override parallelism")
    run.add_argument("--codex-bin", default="codex", help="codex executable path")
    tmpl = sub.add_parser("template", help="write a starter JSON spec")
    tmpl.add_argument("--output", required=True, help="output file for template")
    return parser
def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "template":
        return write_template(Path(args.output))
    if args.command == "run":
        return run_orchestrator(args)
    raise ValueError(f"unknown command: {args.command}")
if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
