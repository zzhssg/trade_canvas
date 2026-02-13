from __future__ import annotations

import subprocess
from pathlib import Path

from backend.app.worktree.manager import WorktreeManager


def test_list_worktrees_marks_canonical_main_from_git_common_dir(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = Path("/Users/rick/.codex/worktrees/b1bc/trade_canvas")
    manager = WorktreeManager(repo_root=repo_root, metadata_dir=tmp_path / ".worktree-meta")

    def fake_run(cmd, cwd=None, capture_output=False, text=False, check=False):
        if cmd == ["git", "rev-parse", "--git-common-dir"]:
            return subprocess.CompletedProcess(
                cmd, 0, stdout="/Users/rick/code/trade_canvas/.git\n", stderr=""
            )
        if cmd == ["git", "worktree", "list", "--porcelain"]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=(
                    "worktree /Users/rick/code/trade_canvas\n"
                    "HEAD deadbeefdeadbeef\n"
                    "branch refs/heads/main\n\n"
                    "worktree /Users/rick/.codex/worktrees/b1bc/trade_canvas\n"
                    "HEAD cafebabecafebabe\n"
                    "branch refs/heads/codex/b1bc\n\n"
                ),
                stderr="",
            )
        raise AssertionError(f"Unexpected command: {cmd}")

    monkeypatch.setattr("backend.app.worktree.manager.subprocess.run", fake_run)
    monkeypatch.setattr("backend.app.worktree.metadata_store.subprocess.run", fake_run)
    monkeypatch.setattr(
        manager._metadata_store,
        "read_index",
        lambda: {"version": 1, "allocations": {}, "active_services": {}},
    )
    monkeypatch.setattr(manager._metadata_store, "read_metadata", lambda _wid: None)

    worktrees = manager.list_worktrees()
    by_path = {wt.path: wt for wt in worktrees}

    main = by_path["/Users/rick/code/trade_canvas"]
    current = by_path["/Users/rick/.codex/worktrees/b1bc/trade_canvas"]

    assert main.is_main is True
    assert main.services is not None
    assert main.services.backend.port == 8000
    assert main.services.frontend.port == 5173

    assert current.is_main is False
    assert current.services is not None
    assert current.services.backend.port == 0
    assert current.services.frontend.port == 0


def test_start_services_passes_frontend_port_to_backend_start(
    tmp_path: Path, monkeypatch
) -> None:
    repo_root = Path("/Users/rick/.codex/worktrees/b1bc/trade_canvas")
    manager = WorktreeManager(repo_root=repo_root, metadata_dir=tmp_path / ".worktree-meta")
    # Minimal fake worktree payload
    class _Wt:
        def __init__(self) -> None:
            self.id = "wt1"
            self.path = "/tmp/wt1"
            self.branch = "codex/wt1"
            self.commit = "deadbeef"
            self.is_detached = False
            self.is_main = False
            self.metadata = None
            self.services = None

    wt = _Wt()

    calls: dict[str, tuple[int, int] | None] = {"backend": None}

    monkeypatch.setattr(manager, "get_worktree", lambda _wid: wt)
    monkeypatch.setattr(
        manager._metadata_store,
        "read_index",
        lambda: {"version": 1, "allocations": {}, "active_services": {}},
    )
    monkeypatch.setattr(manager._metadata_store, "write_index", lambda _data: None)
    monkeypatch.setattr(
        manager._process_runtime,
        "start_frontend",
        lambda **_kwargs: 2222,
    )
    monkeypatch.setattr(
        "backend.app.worktree.manager.allocate_ports",
        lambda _used_backend, _used_frontend: (8001, 5174),
    )

    def fake_start_backend(*, worktree_path: str, port: int, frontend_port: int) -> int:
        _ = worktree_path
        calls["backend"] = (port, frontend_port)
        return 1111

    monkeypatch.setattr(manager._process_runtime, "start_backend", fake_start_backend)

    manager.start_services("wt1")
    assert calls["backend"] == (8001, 5174)
