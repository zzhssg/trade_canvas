from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STATUS_ALIASES = {
    "draft": "draft",
    "草稿": "draft",
    "in_progress": "in_progress",
    "开发中": "in_progress",
    "pending_acceptance": "pending_acceptance",
    "待验收": "pending_acceptance",
    "测试中": "pending_acceptance",
    "done": "online",
    "已完成": "online",
    "online": "online",
    "已上线": "online",
}

STATUS_LABELS = {
    "draft": "草稿",
    "in_progress": "开发中",
    "pending_acceptance": "待验收",
    "online": "已上线",
}


@dataclass
class ProjectRow:
    worktree_id: str
    path: str
    branch: str
    commit: str
    is_main: bool
    description: str | None
    plan_path: str | None
    plan_title: str | None
    plan_status: str
    plan_status_label: str
    ports: dict[str, int]


@dataclass
class ServiceState:
    backend_running: bool
    frontend_running: bool
    backend_port: int
    frontend_port: int
    backend_pid: int | None
    frontend_pid: int | None


def _worktree_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:8]


def _parse_porcelain(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    cur: dict[str, Any] = {}
    for raw in output.splitlines():
        line = raw.strip()
        if not line:
            if cur:
                rows.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            if cur:
                rows.append(cur)
            cur = {"path": line[9:]}
        elif line.startswith("HEAD "):
            cur["commit"] = line[5:]
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif line == "detached":
            cur["detached"] = True
    if cur:
        rows.append(cur)
    return rows


def _read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8").splitlines()
    if not text or text[0].strip() != "---":
        return {}
    out: dict[str, str] = {}
    for line in text[1:]:
        s = line.strip()
        if s == "---":
            break
        if ":" not in s:
            continue
        k, v = s.split(":", 1)
        out[k.strip()] = v.strip()
    return out


def _read_metadata(repo_root: Path, worktree_id: str) -> dict[str, Any]:
    p = repo_root / ".worktree-meta" / f"{worktree_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_metadata(repo_root: Path, worktree_id: str, data: dict[str, Any]) -> None:
    d = repo_root / ".worktree-meta"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{worktree_id}.json"
    payload = {
        "id": worktree_id,
        "description": data.get("description", ""),
        "plan_path": data.get("plan_path"),
        "created_at": data.get("created_at", ""),
        "owner": data.get("owner"),
        "ports": data.get("ports", {}),
    }
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_index(repo_root: Path) -> dict[str, Any]:
    p = repo_root / ".worktree-meta" / "index.json"
    if not p.exists():
        return {"version": 1, "allocations": {}, "active_services": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "allocations": {}, "active_services": {}}


def _write_index(repo_root: Path, index: dict[str, Any]) -> None:
    d = repo_root / ".worktree-meta"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "index.json"
    p.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_process_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _kill_process_group(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except Exception:
            pass


def _kill_port(port: int) -> None:
    res = subprocess.run(
        ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return
    for raw in res.stdout.strip().splitlines():
        try:
            _kill_process_group(int(raw.strip()))
        except Exception:
            continue


def _is_port_listening(port: int) -> bool:
    res = subprocess.run(
        ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0 and bool(res.stdout.strip())


def list_projects(repo_root: Path) -> list[ProjectRow]:
    res = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        raise RuntimeError(res.stderr.strip() or "failed to list worktrees")

    rows: list[ProjectRow] = []
    for wt in _parse_porcelain(res.stdout):
        path = str(wt.get("path", ""))
        wid = _worktree_id(path)
        meta = _read_metadata(repo_root, wid)
        plan_path = (meta.get("plan_path") or "").strip() or None
        plan_title = None
        status = "draft"
        label = STATUS_LABELS[status]
        if plan_path:
            plan_abs = Path(path) / plan_path if not Path(plan_path).is_absolute() else Path(plan_path)
            if plan_abs.exists():
                fm = _read_frontmatter(plan_abs)
                plan_title = (fm.get("title") or "").strip() or None
                status = STATUS_ALIASES.get((fm.get("status") or "").strip(), "draft")
                label = STATUS_LABELS.get(status, "草稿")
        rows.append(
            ProjectRow(
                worktree_id=wid,
                path=path,
                branch=str(wt.get("branch", "")),
                commit=str(wt.get("commit", ""))[:8],
                is_main=Path(path).resolve() == repo_root.resolve(),
                description=meta.get("description"),
                plan_path=plan_path,
                plan_title=plan_title,
                plan_status=status,
                plan_status_label=label,
                ports=meta.get("ports") or {},
            )
        )
    rows.sort(key=lambda r: (r.plan_status, r.path))
    return rows


def _find_project(repo_root: Path, worktree_id: str) -> ProjectRow:
    for row in list_projects(repo_root):
        if row.worktree_id == worktree_id:
            return row
    raise ValueError(f"worktree not found: {worktree_id}")


def _ensure_ports(repo_root: Path, worktree_id: str, worktree_path: str) -> tuple[int, int]:
    project = _find_project(repo_root, worktree_id)
    if project.is_main or project.branch == "main":
        return 8000, 5173
    meta = _read_metadata(repo_root, worktree_id)
    ports = meta.get("ports") or {}
    b = int(ports.get("backend") or 0)
    f = int(ports.get("frontend") or 0)
    if b > 0 and f > 0:
        return b, f
    index = _read_index(repo_root)
    used_b = {int(v.get("backend_port", 0)) for v in (index.get("allocations") or {}).values()}
    used_f = {int(v.get("frontend_port", 0)) for v in (index.get("allocations") or {}).values()}
    b = 18080
    while b in used_b or _is_port_listening(b):
        b += 1
    f = 15180
    while f in used_f or _is_port_listening(f):
        f += 1
    meta.setdefault("ports", {})
    meta["ports"]["backend"] = b
    meta["ports"]["frontend"] = f
    if not meta.get("created_at"):
        meta["created_at"] = datetime.now(timezone.utc).isoformat()
    if not meta.get("owner"):
        meta["owner"] = os.environ.get("USER")
    _write_metadata(repo_root, worktree_id, meta)
    index.setdefault("allocations", {})
    index["allocations"][worktree_id] = {"backend_port": b, "frontend_port": f}
    _write_index(repo_root, index)
    return b, f


def bind_plan(repo_root: Path, worktree_id: str, plan_path: str) -> ProjectRow:
    project = _find_project(repo_root, worktree_id)
    cleaned = plan_path.strip()
    if not cleaned:
        raise ValueError("plan_path cannot be empty")
    if os.path.isabs(cleaned):
        raise ValueError("plan_path must be workspace-relative")
    for row in list_projects(repo_root):
        if row.worktree_id != worktree_id and (row.plan_path or "").strip() == cleaned:
            raise ValueError(f"plan_path already bound: {cleaned}")
    plan_abs = Path(project.path) / cleaned
    if not plan_abs.exists():
        raise ValueError(f"plan file not found: {cleaned}")
    meta = _read_metadata(repo_root, worktree_id)
    if not meta:
        meta = {
            "description": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "owner": os.environ.get("USER"),
            "ports": {},
        }
    meta["plan_path"] = cleaned
    _write_metadata(repo_root, worktree_id, meta)
    return _find_project(repo_root, worktree_id)


def update_plan_status(repo_root: Path, worktree_id: str, status: str) -> ProjectRow:
    project = _find_project(repo_root, worktree_id)
    if not project.plan_path:
        raise ValueError("project has no plan_path bound")
    target = STATUS_ALIASES.get(status.strip())
    if not target:
        raise ValueError(f"invalid status: {status}")
    allow = {
        "draft": {"draft", "in_progress"},
        "in_progress": {"in_progress", "pending_acceptance"},
        "pending_acceptance": {"pending_acceptance", "online", "in_progress"},
        "online": {"online"},
    }
    if target not in allow.get(project.plan_status, set()):
        raise ValueError(f"invalid transition: {project.plan_status} -> {target}")
    label = STATUS_LABELS.get(target, "草稿")
    subprocess.run(
        ["bash", "docs/scripts/doc_set_status.sh", label, project.plan_path],
        cwd=project.path,
        check=True,
    )
    return _find_project(repo_root, worktree_id)


def get_service_state(repo_root: Path, worktree_id: str) -> ServiceState:
    project = _find_project(repo_root, worktree_id)
    b_port, f_port = _ensure_ports(repo_root, worktree_id, project.path)
    index = _read_index(repo_root)
    active = (index.get("active_services") or {}).get(worktree_id) or {}
    b_pid = active.get("backend_pid")
    f_pid = active.get("frontend_pid")
    b_run = _is_process_running(b_pid)
    f_run = _is_process_running(f_pid)
    return ServiceState(
        backend_running=b_run,
        frontend_running=f_run,
        backend_port=b_port,
        frontend_port=f_port,
        backend_pid=b_pid if b_run else None,
        frontend_pid=f_pid if f_run else None,
    )


def start_test_services(repo_root: Path, worktree_id: str, restart: bool = False) -> ServiceState:
    project = _find_project(repo_root, worktree_id)
    is_main_project = project.is_main or project.branch == "main"
    if not is_main_project and project.plan_status != "pending_acceptance":
        raise ValueError("only pending_acceptance projects can start test services")
    b_port, f_port = _ensure_ports(repo_root, worktree_id, project.path)
    index = _read_index(repo_root)
    active = (index.get("active_services") or {}).get(worktree_id) or {}
    b_pid = active.get("backend_pid")
    f_pid = active.get("frontend_pid")
    if restart:
        _kill_process_group(b_pid)
        _kill_process_group(f_pid)
        _kill_port(b_port)
        _kill_port(f_port)
        b_pid = None
        f_pid = None
    if not _is_process_running(b_pid):
        proc = subprocess.Popen(
            ["bash", "scripts/dev_backend.sh", "--no-reload", "--host", "127.0.0.1", "--port", str(b_port)],
            cwd=project.path,
            env=os.environ.copy(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        b_pid = proc.pid
        time.sleep(0.5)
    if not _is_process_running(f_pid):
        env = os.environ.copy()
        env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{b_port}"
        proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(f_port)],
            cwd=Path(project.path) / "frontend",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        f_pid = proc.pid
        time.sleep(0.5)
    index.setdefault("active_services", {})
    index["active_services"][worktree_id] = {"backend_pid": b_pid, "frontend_pid": f_pid}
    _write_index(repo_root, index)
    return get_service_state(repo_root, worktree_id)


def stop_test_services(repo_root: Path, worktree_id: str) -> ServiceState:
    project = _find_project(repo_root, worktree_id)
    index = _read_index(repo_root)
    active = (index.get("active_services") or {}).get(worktree_id) or {}
    _kill_process_group(active.get("backend_pid"))
    _kill_process_group(active.get("frontend_pid"))
    s = get_service_state(repo_root, worktree_id)
    if project.is_main or project.branch == "main":
        _kill_port(s.backend_port)
        _kill_port(s.frontend_port)
    if worktree_id in (index.get("active_services") or {}):
        del index["active_services"][worktree_id]
        _write_index(repo_root, index)
    return get_service_state(repo_root, worktree_id)
