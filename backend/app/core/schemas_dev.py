from __future__ import annotations

from pydantic import BaseModel, Field


class DevServiceState(BaseModel):
    running: bool
    port: int
    pid: int | None = None
    url: str | None = None


class DevServiceStatus(BaseModel):
    backend: DevServiceState
    frontend: DevServiceState


class DevWorktreeMetadata(BaseModel):
    description: str
    plan_path: str | None = None
    created_at: str = ""
    owner: str | None = None
    ports: dict[str, int] = Field(default_factory=dict)


class DevWorktreeInfo(BaseModel):
    id: str
    path: str
    branch: str
    commit: str
    is_detached: bool
    is_main: bool
    metadata: DevWorktreeMetadata | None = None
    services: DevServiceStatus | None = None


class DevWorktreeListResponse(BaseModel):
    worktrees: list[DevWorktreeInfo]


class DevCreateWorktreeRequest(BaseModel):
    branch: str = Field(..., min_length=1)
    description: str = Field(..., min_length=20)
    plan_path: str | None = None
    base_branch: str = "main"


class DevCreateWorktreeResponse(BaseModel):
    ok: bool
    worktree: DevWorktreeInfo | None = None
    error: str | None = None


class DevStartServicesRequest(BaseModel):
    backend_port: int | None = None
    frontend_port: int | None = None


class DevStartServicesResponse(BaseModel):
    ok: bool
    services: DevServiceStatus | None = None
    error: str | None = None


class DevStopServicesResponse(BaseModel):
    ok: bool
    error: str | None = None


class DevDeleteWorktreeRequest(BaseModel):
    force: bool = False


class DevDeleteWorktreeResponse(BaseModel):
    ok: bool
    error: str | None = None


class DevPortAllocationResponse(BaseModel):
    backend_port: int
    frontend_port: int


class DevUpdateMetadataRequest(BaseModel):
    description: str | None = None
    plan_path: str | None = None


class DevUpdateMetadataResponse(BaseModel):
    ok: bool
    metadata: DevWorktreeMetadata | None = None
    error: str | None = None
