from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any


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


def worktree_id(path: str) -> str:
    return hashlib.sha256(path.encode()).hexdigest()[:8]


def parse_worktree_list(output: str) -> list[dict[str, Any]]:
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
