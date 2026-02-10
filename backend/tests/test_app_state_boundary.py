from __future__ import annotations

import re
from pathlib import Path


def _backend_app_root() -> Path:
    return Path(__file__).resolve().parents[1] / "app"


def test_routes_do_not_read_request_or_ws_state_directly() -> None:
    app_root = _backend_app_root()
    target_files = sorted(app_root.glob("*routes.py"))
    target_files.extend(
        [
            app_root / "debug_routes.py",
            app_root / "market_ws_routes.py",
        ]
    )

    pattern = re.compile(r"\b(?:request|ws)\.app\.state\b")
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"route/ws handlers must use dependencies, found direct app.state access in: {offenders}"


def test_main_only_exposes_container_on_app_state() -> None:
    main_py = _backend_app_root() / "main.py"
    text = main_py.read_text(encoding="utf-8")
    assigned = re.findall(r"app\.state\.(\w+)\s*=", text)
    assert assigned == ["container"], f"main.py should only assign app.state.container, got: {assigned}"


def test_route_dependencies_are_not_optional_none() -> None:
    app_root = _backend_app_root()
    target_files = sorted(app_root.glob("*routes.py"))
    pattern = re.compile(r":\s*[A-Za-z_]\w*Dep\s*=\s*None\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"route dependencies should be required DI params, found optional None: {offenders}"


def test_read_model_services_do_not_read_env_flags_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "factor_read_freshness.py",
        app_root / "read_models" / "draw_read_service.py",
        app_root / "read_models" / "world_read_service.py",
    ]
    pattern = re.compile(r"\bresolve_env_bool\b|\bos\.environ\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"read models should use runtime-injected flags, found env reads in: {offenders}"
