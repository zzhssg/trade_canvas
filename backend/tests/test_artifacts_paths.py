from __future__ import annotations

from pathlib import Path

from backend.app.artifacts import resolve_artifacts_root


def test_resolve_artifacts_root_defaults_to_backend_data(monkeypatch) -> None:
    monkeypatch.delenv("TRADE_CANVAS_ARTIFACTS_DIR", raising=False)
    root = resolve_artifacts_root()
    assert root.as_posix().endswith("/backend/data/artifacts")


def test_resolve_artifacts_root_supports_relative_env(monkeypatch) -> None:
    monkeypatch.setenv("TRADE_CANVAS_ARTIFACTS_DIR", "tmp/artifacts")
    root = resolve_artifacts_root()
    expected = (Path(__file__).resolve().parents[2] / "tmp" / "artifacts").resolve()
    assert root == expected
