from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .models import WorktreeMetadata


def _default_index() -> dict[str, Any]:
    return {"version": 1, "allocations": {}, "active_services": {}}


class WorktreeMetadataStore:
    def __init__(self, *, repo_root: Path, metadata_dir: Path | None = None) -> None:
        self._repo_root = repo_root.resolve()
        self.metadata_dir = (metadata_dir or (self._repo_root / ".worktree-meta")).resolve()

    def ensure_storage(self) -> None:
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        (self.metadata_dir / "archive").mkdir(exist_ok=True)
        index_path = self.metadata_dir / "index.json"
        if not index_path.exists():
            self.write_index(_default_index())

    def resolve_main_worktree_root(self) -> Path:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--git-common-dir"],
                cwd=self._repo_root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return self._repo_root
            raw = result.stdout.strip()
            if not raw:
                return self._repo_root
            common_dir = Path(raw)
            if not common_dir.is_absolute():
                common_dir = (self._repo_root / common_dir).resolve()
            return common_dir.parent.resolve()
        except Exception:
            return self._repo_root

    def read_index(self) -> dict[str, Any]:
        index_path = self.metadata_dir / "index.json"
        if not index_path.exists():
            return _default_index()
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            return _default_index()

    def write_index(self, data: dict[str, Any]) -> None:
        index_path = self.metadata_dir / "index.json"
        index_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def read_metadata(self, worktree_id: str) -> WorktreeMetadata | None:
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

    def write_metadata(self, worktree_id: str, metadata: WorktreeMetadata) -> None:
        meta_path = self.metadata_dir / f"{worktree_id}.json"
        payload = {
            "id": worktree_id,
            "description": metadata.description,
            "plan_path": metadata.plan_path,
            "created_at": metadata.created_at,
            "owner": metadata.owner,
            "ports": metadata.ports,
        }
        meta_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
