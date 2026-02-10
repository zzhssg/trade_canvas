from __future__ import annotations

from pathlib import Path

from .flags import resolve_env_str


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_artifacts_root() -> Path:
    raw = resolve_env_str("TRADE_CANVAS_ARTIFACTS_DIR", fallback="")
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = (repo_root() / path).resolve()
        return path
    return (repo_root() / "backend" / "data" / "artifacts").resolve()
