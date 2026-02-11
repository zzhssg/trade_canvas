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
        app_root / "read_models" / "repair_service.py",
        app_root / "read_models" / "world_read_service.py",
    ]
    pattern = re.compile(r"\bresolve_env_bool\b|\bos\.environ\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"read models should use runtime-injected flags, found env reads in: {offenders}"


def test_runtime_services_do_not_read_env_flags_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "market_ingest_service.py",
        app_root / "ingest_supervisor.py",
        app_root / "ingest_binance_ws.py",
        app_root / "overlay_orchestrator.py",
        app_root / "replay_package_service_v1.py",
        app_root / "overlay_package_service_v1.py",
        app_root / "debug_routes.py",
    ]
    pattern = re.compile(r"\bresolve_env_bool\b|\bresolve_env_int\b|\bos\.environ\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"runtime services should rely on injected config, found env reads in: {offenders}"


def test_services_do_not_raise_http_exception_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "backtest_service.py",
        app_root / "market_ingest_service.py",
        app_root / "replay_package_service_v1.py",
        app_root / "overlay_package_service_v1.py",
        app_root / "replay_prepare_service.py",
    ]
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if "HTTPException" in text:
            offenders.append(path.name)
    assert not offenders, f"services should raise ServiceError and let routes map HTTP errors, found: {offenders}"


def test_replay_overlay_services_delegate_sqlite_reads_to_reader_layer() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "replay_package_service_v1.py",
        app_root / "overlay_package_service_v1.py",
    ]
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if "sqlite_connect" in text or "SELECT " in text:
            offenders.append(path.name)
    assert not offenders, f"service layer should orchestrate only; sqlite reads belong to *reader_v1 modules: {offenders}"


def test_read_models_do_not_raise_http_exception_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "factor_read_freshness.py",
        app_root / "read_models" / "draw_read_service.py",
        app_root / "read_models" / "world_read_service.py",
    ]
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if "HTTPException" in text:
            offenders.append(str(path.relative_to(app_root)))
    assert not offenders, f"read models should raise ServiceError and let routes map HTTP errors, found: {offenders}"


def test_market_runtime_path_does_not_depend_on_market_flags_module() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "market_runtime_builder.py",
        app_root / "replay_package_service_v1.py",
        app_root / "market_backfill.py",
        app_root / "market_data" / "derived_services.py",
        app_root / "market_data" / "read_services.py",
    ]
    pattern = re.compile(r"\bmarket_flags\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(str(path.relative_to(app_root)))

    assert not offenders, f"runtime path should use runtime flags/config injection, found market_flags dependency in: {offenders}"


def test_blocking_and_ccxt_client_do_not_read_env_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "blocking.py",
        app_root / "ccxt_client.py",
    ]
    pattern = re.compile(r"\bos\.environ\b|\bresolve_env_int\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"infrastructure modules should rely on runtime injection, found env reads in: {offenders}"
