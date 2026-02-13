from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path


class WorktreeProcessRuntime:
    def is_process_running(self, pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    def start_backend(self, *, worktree_path: str, port: int, frontend_port: int) -> int:
        wt_path = Path(worktree_path)
        script_path = wt_path / "scripts" / "dev_backend.sh"
        if not script_path.exists():
            raise FileNotFoundError(f"Backend script not found: {script_path}")

        self.kill_port(port)

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
        time.sleep(1)
        return proc.pid

    def start_frontend(self, *, worktree_path: str, port: int, backend_port: int) -> int:
        wt_path = Path(worktree_path)
        frontend_path = wt_path / "frontend"
        if not frontend_path.exists():
            raise FileNotFoundError(f"Frontend directory not found: {frontend_path}")

        self.kill_port(port)

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
        time.sleep(1)
        return proc.pid

    def kill_port(self, port: int) -> None:
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return
            pids = [pid for pid in result.stdout.strip().split("\n") if pid]
            for pid in pids:
                try:
                    os.kill(int(pid), signal.SIGTERM)
                except (OSError, ValueError):
                    continue
            if pids:
                time.sleep(0.5)
        except Exception:
            return

    def terminate_process_group(self, pid: int | None) -> None:
        if pid is None:
            return
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            return
