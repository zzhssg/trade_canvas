"""Git worktree management with service lifecycle."""
from __future__ import annotations

import logging
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .port_allocator import allocate_ports, get_main_ports
from .metadata_store import WorktreeMetadataStore
from .models import ServiceState, ServiceStatus, WorktreeInfo, WorktreeMetadata, parse_worktree_list, worktree_id
from .process_runtime import WorktreeProcessRuntime

logger = logging.getLogger(__name__)


class WorktreeManager:
    """Manages git worktrees and their associated services."""

    def __init__(self, repo_root: Path, metadata_dir: Path | None = None):
        self.repo_root = repo_root.resolve()
        self._metadata_store = WorktreeMetadataStore(repo_root=self.repo_root, metadata_dir=metadata_dir)
        self._metadata_store.ensure_storage()
        self._process_runtime = WorktreeProcessRuntime()

    @property
    def metadata_dir(self) -> Path:
        return self._metadata_store.metadata_dir

    def read_index(self) -> dict:
        return self._metadata_store.read_index()

    def list_worktrees(self) -> list[WorktreeInfo]:
        main_worktree_root = self._metadata_store.resolve_main_worktree_root()
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error("Failed to list worktrees: %s", result.stderr)
            return []

        parsed = parse_worktree_list(result.stdout)
        index = self._metadata_store.read_index()
        allocations = index.get("allocations", {})
        active_services = index.get("active_services", {})
        worktrees: list[WorktreeInfo] = []

        for wt in parsed:
            path = str(wt.get("path", ""))
            wt_id = worktree_id(path)
            is_main = Path(path).resolve() == main_worktree_root
            metadata = self._metadata_store.read_metadata(wt_id)

            if is_main:
                backend_port, frontend_port = get_main_ports()
            elif metadata and metadata.ports:
                backend_port = int(metadata.ports.get("backend", 0))
                frontend_port = int(metadata.ports.get("frontend", 0))
            else:
                alloc = allocations.get(wt_id, {})
                backend_port = int(alloc.get("backend_port", 0))
                frontend_port = int(alloc.get("frontend_port", 0))

            active = active_services.get(wt_id, {})
            backend_pid = active.get("backend_pid")
            frontend_pid = active.get("frontend_pid")
            backend_running = bool(backend_pid is not None and self._process_runtime.is_process_running(int(backend_pid)))
            frontend_running = bool(frontend_pid is not None and self._process_runtime.is_process_running(int(frontend_pid)))

            services = ServiceStatus(
                backend=ServiceState(
                    running=backend_running,
                    port=backend_port,
                    pid=int(backend_pid) if backend_running and backend_pid is not None else None,
                    url=f"http://127.0.0.1:{backend_port}" if backend_running else None,
                ),
                frontend=ServiceState(
                    running=frontend_running,
                    port=frontend_port,
                    pid=int(frontend_pid) if frontend_running and frontend_pid is not None else None,
                    url=f"http://127.0.0.1:{frontend_port}" if frontend_running else None,
                ),
            )

            worktrees.append(
                WorktreeInfo(
                    id=wt_id,
                    path=path,
                    branch=str(wt.get("branch", "")),
                    commit=str(wt.get("commit", ""))[:8],
                    is_detached=bool(wt.get("detached", False)),
                    is_main=is_main,
                    metadata=metadata,
                    services=services,
                )
            )
        return worktrees

    def get_worktree(self, worktree_id_value: str) -> WorktreeInfo | None:
        for wt in self.list_worktrees():
            if wt.id == worktree_id_value:
                return wt
        return None

    def start_services(
        self,
        worktree_id: str,
        backend_port: int | None = None,
        frontend_port: int | None = None,
    ) -> ServiceStatus:
        wt = self.get_worktree(worktree_id)
        if wt is None:
            raise ValueError(f"Worktree not found: {worktree_id}")

        if wt.is_main:
            backend_port, frontend_port = get_main_ports()
        elif backend_port is None or frontend_port is None:
            if wt.metadata and wt.metadata.ports:
                backend_port = backend_port or int(wt.metadata.ports.get("backend", 0))
                frontend_port = frontend_port or int(wt.metadata.ports.get("frontend", 0))
            if not backend_port or not frontend_port:
                index = self._metadata_store.read_index()
                used_backend = {int(v.get("backend_port", 0)) for v in index.get("allocations", {}).values()}
                used_frontend = {int(v.get("frontend_port", 0)) for v in index.get("allocations", {}).values()}
                backend_port, frontend_port = allocate_ports(used_backend, used_frontend)

        assert backend_port is not None
        assert frontend_port is not None

        if not wt.is_main:
            index = self._metadata_store.read_index()
            index.setdefault("allocations", {})[worktree_id] = {
                "backend_port": int(backend_port),
                "frontend_port": int(frontend_port),
            }
            self._metadata_store.write_index(index)
            if wt.metadata:
                wt.metadata.ports = {"backend": int(backend_port), "frontend": int(frontend_port)}
                self._metadata_store.write_metadata(worktree_id, wt.metadata)

        backend_pid = self._process_runtime.start_backend(
            worktree_path=wt.path,
            port=int(backend_port),
            frontend_port=int(frontend_port),
        )
        frontend_pid = self._process_runtime.start_frontend(
            worktree_path=wt.path,
            port=int(frontend_port),
            backend_port=int(backend_port),
        )

        index = self._metadata_store.read_index()
        index.setdefault("active_services", {})[worktree_id] = {
            "backend_pid": int(backend_pid),
            "frontend_pid": int(frontend_pid),
            "backend_port": int(backend_port),
            "frontend_port": int(frontend_port),
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        self._metadata_store.write_index(index)

        return ServiceStatus(
            backend=ServiceState(
                running=True,
                port=int(backend_port),
                pid=int(backend_pid),
                url=f"http://127.0.0.1:{int(backend_port)}",
            ),
            frontend=ServiceState(
                running=True,
                port=int(frontend_port),
                pid=int(frontend_pid),
                url=f"http://127.0.0.1:{int(frontend_port)}",
            ),
        )

    def stop_services(self, worktree_id: str) -> bool:
        index = self._metadata_store.read_index()
        active = index.get("active_services", {}).get(worktree_id)
        if not active:
            return False

        self._process_runtime.terminate_process_group(active.get("backend_pid"))
        self._process_runtime.terminate_process_group(active.get("frontend_pid"))

        if worktree_id in index.get("active_services", {}):
            del index["active_services"][worktree_id]
            self._metadata_store.write_index(index)
        return True

    def create_worktree(
        self,
        branch: str,
        description: str,
        plan_path: str | None = None,
        base_branch: str = "main",
    ) -> WorktreeInfo:
        if len(description) < 20:
            raise ValueError("Description must be at least 20 characters")

        exists = subprocess.run(
            ["git", "rev-parse", "--verify", branch],
            cwd=self.repo_root,
            capture_output=True,
        )
        if exists.returncode != 0:
            subprocess.run(
                ["git", "branch", branch, base_branch],
                cwd=self.repo_root,
                check=True,
            )

        worktree_path = self.repo_root.parent / f"worktree-{branch.replace('/', '-')}"
        subprocess.run(
            ["git", "worktree", "add", str(worktree_path), branch],
            cwd=self.repo_root,
            check=True,
        )

        wt_id = worktree_id(str(worktree_path))
        index = self._metadata_store.read_index()
        used_backend = {int(v.get("backend_port", 0)) for v in index.get("allocations", {}).values()}
        used_frontend = {int(v.get("frontend_port", 0)) for v in index.get("allocations", {}).values()}
        backend_port, frontend_port = allocate_ports(used_backend, used_frontend)

        metadata = WorktreeMetadata(
            description=description,
            plan_path=plan_path,
            created_at=datetime.now(timezone.utc).isoformat(),
            owner=os.environ.get("USER"),
            ports={"backend": int(backend_port), "frontend": int(frontend_port)},
        )
        self._metadata_store.write_metadata(wt_id, metadata)

        index.setdefault("allocations", {})[wt_id] = {
            "backend_port": int(backend_port),
            "frontend_port": int(frontend_port),
        }
        self._metadata_store.write_index(index)

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
        wt = self.get_worktree(worktree_id)
        if wt is None:
            return False
        if wt.is_main:
            raise ValueError("Cannot delete main worktree")

        self.stop_services(worktree_id)

        meta_path = self.metadata_dir / f"{worktree_id}.json"
        if meta_path.exists():
            archive_path = self.metadata_dir / "archive" / f"{worktree_id}_{int(time.time())}.json"
            meta_path.rename(archive_path)

        index = self._metadata_store.read_index()
        if worktree_id in index.get("allocations", {}):
            del index["allocations"][worktree_id]
        if worktree_id in index.get("active_services", {}):
            del index["active_services"][worktree_id]
        self._metadata_store.write_index(index)

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
        metadata = self._metadata_store.read_metadata(worktree_id)
        if metadata is None:
            return None
        if description is not None:
            metadata.description = description
        if plan_path is not None:
            metadata.plan_path = plan_path
        self._metadata_store.write_metadata(worktree_id, metadata)
        return metadata
