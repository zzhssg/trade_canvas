from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .worktree_service import (
    bind_plan,
    get_service_state,
    list_projects,
    start_single_service,
    start_test_services,
    stop_single_service,
    stop_test_services,
    update_plan_status,
)


class BindPlanRequest(BaseModel):
    plan_path: str = Field(..., min_length=1)


class StatusRequest(BaseModel):
    status: str = Field(..., min_length=1)


def create_app() -> FastAPI:
    app = FastAPI(title="project-console", version="0.3.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    default_repo = Path(os.environ.get("PROJECT_CONSOLE_REPO_ROOT", ".")).resolve()
    frontend_file = (Path(__file__).resolve().parents[1] / "frontend" / "index.html").resolve()

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"ok": "true"}

    @app.get("/api/projects")
    def projects(repo_root: str | None = Query(default=None)) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            rows = list_projects(repo)
        except RuntimeError as e:
            raise HTTPException(status_code=500, detail=str(e)) from e
        payload = []
        for r in rows:
            s = get_service_state(repo, r.worktree_id)
            payload.append(
                {
                    "worktree_id": r.worktree_id,
                    "path": r.path,
                    "branch": r.branch,
                    "commit": r.commit,
                    "is_main": r.is_main,
                    "description": r.description,
                    "plan_path": r.plan_path,
                    "plan_title": r.plan_title,
                    "plan_status": r.plan_status,
                    "plan_status_label": r.plan_status_label,
                    "ports": r.ports,
                    "is_main_project": bool(r.is_main or r.branch == "main"),
                    "services": {
                        "backend_running": s.backend_running,
                        "frontend_running": s.frontend_running,
                        "backend_port": s.backend_port,
                        "frontend_port": s.frontend_port,
                    },
                }
            )
        return {"repo_root": str(repo), "projects": payload}

    @app.post("/api/projects/{worktree_id}/bind_plan")
    def bind_plan_api(
        worktree_id: str,
        req: BindPlanRequest,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            row = bind_plan(repo, worktree_id, req.plan_path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "project": {
                "worktree_id": row.worktree_id,
                "plan_path": row.plan_path,
                "plan_title": row.plan_title,
                "plan_status": row.plan_status,
                "plan_status_label": row.plan_status_label,
            },
        }

    @app.post("/api/projects/{worktree_id}/status")
    def update_status_api(
        worktree_id: str,
        req: StatusRequest,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            row = update_plan_status(repo, worktree_id, req.status)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "project": {
                "worktree_id": row.worktree_id,
                "plan_path": row.plan_path,
                "plan_title": row.plan_title,
                "plan_status": row.plan_status,
                "plan_status_label": row.plan_status_label,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/start")
    def test_start_api(
        worktree_id: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = start_test_services(repo, worktree_id, restart=False)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/stop")
    def test_stop_api(
        worktree_id: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = stop_test_services(repo, worktree_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/restart")
    def test_restart_api(
        worktree_id: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = start_test_services(repo, worktree_id, restart=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/{component}/start")
    def test_single_start_api(
        worktree_id: str,
        component: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = start_single_service(repo, worktree_id, component, restart=False)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/{component}/restart")
    def test_single_restart_api(
        worktree_id: str,
        component: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = start_single_service(repo, worktree_id, component, restart=True)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.post("/api/projects/{worktree_id}/test/{component}/stop")
    def test_single_stop_api(
        worktree_id: str,
        component: str,
        repo_root: str | None = Query(default=None),
    ) -> dict[str, object]:
        repo = Path(repo_root).resolve() if repo_root else default_repo
        if not (repo / ".git").exists():
            raise HTTPException(status_code=400, detail=f"not a git repo: {repo}")
        try:
            s = stop_single_service(repo, worktree_id, component)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "services": {
                "backend_running": s.backend_running,
                "frontend_running": s.frontend_running,
                "backend_port": s.backend_port,
                "frontend_port": s.frontend_port,
            },
        }

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(frontend_file)

    return app


app = create_app()
