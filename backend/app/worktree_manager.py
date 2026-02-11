"""Git worktree management with service lifecycle."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .port_allocator import allocate_ports, get_main_ports, is_port_available

logger = logging.getLogger(__name__)


@dataclass
class ServiceState:
    running: bool
    port: int
    pid: int | None = None
    url: str | None = None


@dataclass
class ServiceStatus:
    backend: ServiceState
    frontend: ServiceState


@dataclass
class WorktreeMetadata:
    description: str
    plan_path: str | None = None
    created_at: str = ""
    owner: str | None = None
    ports: dict[str, int] = field(default_factory=dict)


@dataclass
class WorktreeInfo:
    id: str
    path: str
    branch: str
    commit: str
    is_detached: bool
    is_main: bool
    metadata: WorktreeMetadata | None = None
    services: ServiceStatus | None = None


def _worktree_id(path: str) -> str:
    """Generate a short ID from worktree path."""
    return hashlib.sha256(path.encode()).hexdigest()[:8]


def _parse_worktree_list(output: str) -> list[dict[str, Any]]:
    """Parse `git worktree list --porcelain` output."""
    worktrees = []
    current: dict[str, Any] = {}

    for line in output.strip().split("\n"):
        line = line.strip()
        if not line:
            if current:
                worktrees.append(current)
                current = {}
            continue

        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[9:]}
        elif line.startswith("HEAD "):
            current["commit"] = line[5:]
        elif line.startswith("branch "):
            current["branch"] = line[7:].replace("refs/heads/", "")
        elif line == "detached":
            current["detached"] = True

    if current:
        worktrees.append(current)

    return worktrees


class WorktreeManager:
    """Manages git worktrees and their associated services."""

    def __init__(self, repo_root: Path, metadata_dir: Path | None = None):
        self.repo_root = repo_root.resolve()
        self.metadata_dir = metadata_dir or (self.repo_root / ".worktree-meta")
        self._ensure_metadata_dir()

    def _ensure_metadata_dir(self) -> None:
        """Ensure metadata directory exists."""
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        archive_dir = self.metadata_dir / "archive"
        archive_dir.mkdir(exist_ok=True)

        # Create index.json if not exists
        index_path = self.metadata_dir / "index.json"
        if not index_path.exists():
            self._write_index({"version": 1, "allocations": {}, "active_services": {}})

    def _resolve_main_worktree_root(self) -> Path:
        """Resolve the canonical main worktree path from git common dir."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return self.repo_root
            raw = result.stdout.strip()
            if not raw:
                return self.repo_root
            common_dir = Path(raw)
            if not common_dir.is_absolute():
                common_dir = (self.repo_root / common_dir).resolve()
            return common_dir.parent.resolve()
        except Exception:
            return self.repo_root

    def _read_index(self) -> dict[str, Any]:
        """Read the index file."""
        index_path = self.metadata_dir / "index.json"
        if index_path.exists():
            return json.loads(index_path.read_text(encoding="utf-8"))
        return {"version": 1, "allocations": {}, "active_services": {}}

    def read_index(self) -> dict[str, Any]:
        """Public readonly view of worktree index metadata."""
        return self._read_index()

    def _write_index(self, data: dict[str, Any]) -> None:
        """Write the index file."""
        index_path = self.metadata_dir / "index.json"
        index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _read_metadata(self, worktree_id: str) -> WorktreeMetadata | None:
        """Read metadata for a worktree."""
        meta_path = self.metadata_dir / f"{worktree_id}.json"
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return WorktreeMetadata(
                description=data.get("description", ""),
                plan_path=data.get("plan_path"),
                created_at=data.get("created_at", ""),
                owner=data.get("owner"),
                ports=data.get("ports", {}),
            )
        except Exception:
            return None

    def _write_metadata(self, worktree_id: str, metadata: WorktreeMetadata) -> None:
        """Write metadata for a worktree."""
        meta_path = self.metadata_dir / f"{worktree_id}.json"
        data = {
            "id": worktree_id,
            "description": metadata.description,
            "plan_path": metadata.plan_path,
            "created_at": metadata.created_at,
            "owner": metadata.owner,
            "ports": metadata.ports,
        }
        meta_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_worktrees(self) -> list[WorktreeInfo]:
        """List all worktrees with metadata and service status."""
        main_worktree_root = self._resolve_main_worktree_root()
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Failed to list worktrees: %s", result.stderr)
            return []

        parsed = _parse_worktree_list(result.stdout)
        worktrees = []

        for wt in parsed:
            path = wt.get("path", "")
            wt_id = _worktree_id(path)
            is_main = Path(path).resolve() == main_worktree_root

            # Get metadata
            metadata = self._read_metadata(wt_id)

            # Determine ports
            if is_main:
                backend_port, frontend_port = get_main_ports()
            elif metadata and metadata.ports:
                backend_port = metadata.ports.get("backend", 0)
                frontend_port = metadata.ports.get("frontend", 0)
            else:
                backend_port, frontend_port = 0, 0

            # Check service status
            index = self._read_index()
            active = index.get("active_services", {}).get(wt_id, {})
            backend_pid = active.get("backend_pid")
            frontend_pid = active.get("frontend_pid")

            backend_running = backend_pid is not None and self._is_process_running(backend_pid)
            frontend_running = frontend_pid is not None and self._is_process_running(frontend_pid)

            services = ServiceStatus(
                backend=ServiceState(
                    running=backend_running,
                    port=backend_port,
                    pid=backend_pid if backend_running else None,
                    url=f"http://127.0.0.1:{backend_port}" if backend_running else None,
                ),
                frontend=ServiceState(
                    running=frontend_running,
                    port=frontend_port,
                    pid=frontend_pid if frontend_running else None,
                    url=f"http://127.0.0.1:{frontend_port}" if frontend_running else None,
                ),
            )

            worktrees.append(
                WorktreeInfo(
                    id=wt_id,
                    path=path,
                    branch=wt.get("branch", ""),
                    commit=wt.get("commit", "")[:8],
                    is_detached=wt.get("detached", False),
                    is_main=is_main,
                    metadata=metadata,
                    services=services,
                )
            )

        return worktrees

    def get_worktree(self, worktree_id: str) -> WorktreeInfo | None:
        """Get a specific worktree by ID."""
        for wt in self.list_worktrees():
            if wt.id == worktree_id:
                return wt
        return None

    def _is_process_running(self, pid: int) -> bool:
        """Check if a process is running."""
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def start_services(
        self,
        worktree_id: str,
        backend_port: int | None = None,
        frontend_port: int | None = None,
    ) -> ServiceStatus:
        """Start backend and frontend services for a worktree."""
        wt = self.get_worktree(worktree_id)
        if wt is None:
            raise ValueError(f"Worktree not found: {worktree_id}")

        # Determine ports
        if wt.is_main:
            backend_port, frontend_port = get_main_ports()
        elif backend_port is None or frontend_port is None:
            # Check if we have saved ports
            if wt.metadata and wt.metadata.ports:
                backend_port = backend_port or wt.metadata.ports.get("backend")
                frontend_port = frontend_port or wt.metadata.ports.get("frontend")

            # Allocate new ports if needed
            if backend_port is None or frontend_port is None:
                index = self._read_index()
                used_backend = {
                    v.get("backend_port", 0)
                    for v in index.get("allocations", {}).values()
                }
                used_frontend = {
                    v.get("frontend_port", 0)
                    for v in index.get("allocations", {}).values()
                }
                backend_port, frontend_port = allocate_ports(used_backend, used_frontend)

        # Save port allocation
        if not wt.is_main:
            index = self._read_index()
            index["allocations"][worktree_id] = {
                "backend_port": backend_port,
                "frontend_port": frontend_port,
            }
            self._write_index(index)

            # Update metadata
            if wt.metadata:
                wt.metadata.ports = {"backend": backend_port, "frontend": frontend_port}
                self._write_metadata(worktree_id, wt.metadata)

        # Start backend
        backend_pid = self._start_backend(wt.path, backend_port, frontend_port)

        # Start frontend
        frontend_pid = self._start_frontend(wt.path, frontend_port, backend_port)

        # Save active services
        index = self._read_index()
        index["active_services"][worktree_id] = {
            "backend_pid": backend_pid,
            "frontend_pid": frontend_pid,
            "backend_port": backend_port,
            "frontend_port": frontend_port,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_index(index)

        return ServiceStatus(
            backend=ServiceState(
                running=True,
                port=backend_port,
                pid=backend_pid,
                url=f"http://127.0.0.1:{backend_port}",
            ),
            frontend=ServiceState(
                running=True,
                port=frontend_port,
                pid=frontend_pid,
                url=f"http://127.0.0.1:{frontend_port}",
            ),
        )

    def _start_backend(self, worktree_path: str, port: int, frontend_port: int) -> int:
        """Start backend service."""
        wt_path = Path(worktree_path)
        script_path = wt_path / "scripts" / "dev_backend.sh"

        if not script_path.exists():
            raise FileNotFoundError(f"Backend script not found: {script_path}")

        # Kill existing process on port if any
        self._kill_port(port)

        env = os.environ.copy()
        env["TRADE_CANVAS_ENABLE_DEBUG_API"] = "1"
        env["TRADE_CANVAS_ENABLE_ONDEMAND_INGEST"] = "1"
        cors_origins_raw = env.get(
            "TRADE_CANVAS_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
        origins = [o.strip() for o in cors_origins_raw.split(",") if o.strip()]
        dynamic_origins = [
            f"http://localhost:{frontend_port}",
            f"http://127.0.0.1:{frontend_port}",
        ]
        for origin in dynamic_origins:
            if origin not in origins:
                origins.append(origin)
        env["TRADE_CANVAS_CORS_ORIGINS"] = ",".join(origins)

        proc = subprocess.Popen(
            ["bash", str(script_path), "--port", str(port), "--no-access-log"],
            cwd=wt_path,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait a bit for startup
        time.sleep(1)
        return proc.pid

    def _start_frontend(self, worktree_path: str, port: int, backend_port: int) -> int:
        """Start frontend service."""
        wt_path = Path(worktree_path)
        frontend_path = wt_path / "frontend"

        if not frontend_path.exists():
            raise FileNotFoundError(f"Frontend directory not found: {frontend_path}")

        # Kill existing process on port if any
        self._kill_port(port)

        env = os.environ.copy()
        env["VITE_API_BASE_URL"] = f"http://127.0.0.1:{backend_port}"

        proc = subprocess.Popen(
            ["npm", "run", "dev", "--", "--port", str(port)],
            cwd=frontend_path,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Wait a bit for startup
        time.sleep(1)
        return proc.pid

    def _kill_port(self, port: int) -> None:
        """Kill process using a specific port."""
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                pids = result.stdout.strip().split("\n")
                for pid in pids:
                    try:
                        os.kill(int(pid), signal.SIGTERM)
                    except (OSError, ValueError):
                        pass
                time.sleep(0.5)
        except Exception:
            pass

    def stop_services(self, worktree_id: str) -> bool:
        """Stop services for a worktree."""
        index = self._read_index()
        active = index.get("active_services", {}).get(worktree_id)
        if not active:
            return False

        backend_pid = active.get("backend_pid")
        frontend_pid = active.get("frontend_pid")

        # Stop backend
        if backend_pid:
            try:
                os.killpg(os.getpgid(backend_pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        # Stop frontend
        if frontend_pid:
            try:
                os.killpg(os.getpgid(frontend_pid), signal.SIGTERM)
            except (OSError, ProcessLookupError):
                pass

        # Remove from active services
        if worktree_id in index.get("active_services", {}):
            del index["active_services"][worktree_id]
            self._write_index(index)

        return True

    def create_worktree(
        self,
        branch: str,
        description: str,
        plan_path: str | None = None,
        base_branch: str = "main",
    ) -> WorktreeInfo:
        """Create a new worktree with metadata."""
        if len(description) < 20:
            raise ValueError("Description must be at least 20 characters")

        # Create branch if it doesn't exist
        result = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=self.repo_root,
            capture_output=True,
        )
        if result.returncode != 0:
            # Create new branch from base
            subprocess.run(
                ["git", "branch", branch, base_branch],
                cwd=self.repo_root,
                check=True,
            )

        # Create worktree
        worktree_path = self.repo_root.parent / f"worktree-{branch.replace('/', '-')}"
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch],
            cwd=self.repo_root,
            check=True,
        )

        wt_id = _worktree_id(str(worktree_path))

        # Allocate ports
        index = self._read_index()
        used_backend = {v.get("backend_port", 0) for v in index.get("allocations", {}).values()}
        used_frontend = {v.get("frontend_port", 0) for v in index.get("allocations", {}).values()}
        backend_port, frontend_port = allocate_ports(used_backend, used_frontend)

        # Save metadata
        metadata = WorktreeMetadata(
            description=description,
            plan_path=plan_path,
            created_at=datetime.now(timezone.utc).isoformat(),
            owner=os.environ.get("USER"),
            ports={"backend": backend_port, "frontend": frontend_port},
        )
        self._write_metadata(wt_id, metadata)

        # Save allocation
        index["allocations"][wt_id] = {
            "backend_port": backend_port,
            "frontend_port": frontend_port,
        }
        self._write_index(index)

        return WorktreeInfo(
            id=wt_id,
            path=str(worktree_path),
            branch=branch,
            commit="",
            is_detached=False,
            is_main=False,
            metadata=metadata,
            services=None,
        )

    def delete_worktree(self, worktree_id: str, force: bool = False) -> bool:
        """Delete a worktree and archive its metadata."""
        wt = self.get_worktree(worktree_id)
        if wt is None:
            return False

        if wt.is_main:
            raise ValueError("Cannot delete main worktree")

        # Stop services first
        self.stop_services(worktree_id)

        # Archive metadata
        meta_path = self.metadata_dir / f"{worktree_id}.json"
        if meta_path.exists():
            archive_path = self.metadata_dir / "archive" / f"{worktree_id}_{int(time.time())}.json"
            meta_path.rename(archive_path)

        # Remove from index
        index = self._read_index()
        if worktree_id in index.get("allocations", {}):
            del index["allocations"][worktree_id]
        if worktree_id in index.get("active_services", {}):
            del index["active_services"][worktree_id]
        self._write_index(index)

        # Remove worktree
        cmd = ["git", "worktree", "remove", wt.path]
        if force:
            cmd.append("--force")
        subprocess.run(cmd, cwd=self.repo_root, check=True)

        return True

    def update_metadata(
        self,
        worktree_id: str,
        description: str | None = None,
        plan_path: str | None = None,
    ) -> WorktreeMetadata | None:
        """Update worktree metadata."""
        metadata = self._read_metadata(worktree_id)
        if metadata is None:
            return None

        if description is not None:
            metadata.description = description
        if plan_path is not None:
            metadata.plan_path = plan_path

        self._write_metadata(worktree_id, metadata)
        return metadata
