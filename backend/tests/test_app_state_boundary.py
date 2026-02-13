from __future__ import annotations

import re
from pathlib import Path


def _backend_app_root() -> Path:
    return Path(__file__).resolve().parents[1] / "app"


def test_routes_do_not_read_request_or_ws_state_directly() -> None:
    app_root = _backend_app_root()
    target_files = sorted(app_root.rglob("*routes.py"))

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


def test_main_lifecycle_delegates_startup_shutdown_to_service() -> None:
    main_py = _backend_app_root() / "main.py"
    text = main_py.read_text(encoding="utf-8")
    assert "container.lifecycle.startup()" in text
    assert "container.lifecycle.shutdown()" in text
    assert "run_startup_kline_sync_for_runtime(" not in text
    assert "container.supervisor.start_whitelist(" not in text
    assert "container.supervisor.start_reaper(" not in text


def test_route_dependencies_are_not_optional_none() -> None:
    app_root = _backend_app_root()
    target_files = sorted(app_root.rglob("*routes.py"))
    pattern = re.compile(r":\s*[A-Za-z_]\w*Dep\s*=\s*None\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"route dependencies should be required DI params, found optional None: {offenders}"


def test_market_routes_do_not_depend_on_market_runtime_aggregate() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "market/http_routes.py",
        app_root / "market/debug_routes.py",
        app_root / "market/health_routes.py",
        app_root / "market/top_markets_routes.py",
    ]
    pattern = re.compile(r"\bMarketRuntimeDep\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"market routes should depend on narrow services, found MarketRuntimeDep in: {offenders}"


def test_market_ws_handler_does_not_depend_on_market_runtime_aggregate() -> None:
    app_root = _backend_app_root()
    target_file = app_root / "market/ws_routes.py"
    text = target_file.read_text(encoding="utf-8")
    assert "MarketRuntime" not in text, "market_ws_routes should not depend on MarketRuntime aggregate directly"


def test_dependencies_do_not_export_market_runtime_aggregate_dep() -> None:
    app_root = _backend_app_root()
    target_file = app_root / "deps" / "__init__.py"
    text = target_file.read_text(encoding="utf-8")
    assert "def get_market_runtime(" not in text
    assert "MarketRuntimeDep =" not in text


def test_market_runtime_removes_legacy_passthrough_properties() -> None:
    app_root = _backend_app_root()
    target_file = app_root / "market/runtime.py"
    text = target_file.read_text(encoding="utf-8")
    legacy_props = [
        "def query(self)",
        "def ingest(self)",
        "def ws_messages(self)",
        "def ws_subscriptions(self)",
        "def ingest_pipeline(self)",
        "def backfill_progress(self)",
    ]
    offenders = [name for name in legacy_props if name in text]
    assert not offenders, f"market_runtime should expose contexts directly, legacy passthrough properties found: {offenders}"


def test_read_model_services_do_not_read_env_flags_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "factor" / "read_freshness.py",
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
        app_root / "market/ingest_service.py",
        app_root / "market/query_service.py",
        app_root / "ingest" / "supervisor.py",
        app_root / "ingest" / "binance_ws.py",
        app_root / "market" / "history_bootstrapper.py",
        app_root / "overlay" / "orchestrator.py",
        app_root / "replay" / "package_service_v1.py",
        app_root / "overlay" / "package_service_v1.py",
        app_root / "debug" / "routes.py",
    ]
    pattern = re.compile(r"\bresolve_env_bool\b|\bresolve_env_int\b|\bos\.environ\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"runtime services should rely on injected config, found env reads in: {offenders}"


def test_market_query_service_does_not_trigger_ingest_pipeline_refresh() -> None:
    app_root = _backend_app_root()
    target_file = app_root / "market/query_service.py"
    text = target_file.read_text(encoding="utf-8")
    assert "refresh_series_sync" not in text


def test_services_do_not_raise_http_exception_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "backtest" / "service.py",
        app_root / "market/ingest_service.py",
        app_root / "replay" / "package_service_v1.py",
        app_root / "overlay" / "package_service_v1.py",
        app_root / "replay" / "prepare_service.py",
    ]
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if "HTTPException" in text:
            offenders.append(path.name)
    assert not offenders, f"services should raise ServiceError and let routes map HTTP errors, found: {offenders}"


def test_replay_overlay_services_delegate_package_reads_to_reader_layer() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "replay" / "package_service_v1.py",
        app_root / "overlay" / "package_service_v1.py",
    ]
    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if "SELECT " in text:
            offenders.append(path.name)
    assert not offenders, f"service layer should orchestrate only; package reads belong to *reader_v1 modules: {offenders}"


def test_read_models_do_not_raise_http_exception_directly() -> None:
    app_root = _backend_app_root()
    target_files = [
        app_root / "factor" / "read_freshness.py",
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
        app_root / "market/runtime_builder.py",
        app_root / "replay" / "package_service_v1.py",
        app_root / "market/backfill.py",
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
        app_root / "runtime" / "blocking.py",
        app_root / "market" / "ccxt_client.py",
    ]
    pattern = re.compile(r"\bos\.environ\b|\bresolve_env_int\b")

    offenders: list[str] = []
    for path in target_files:
        text = path.read_text(encoding="utf-8")
        if pattern.search(text):
            offenders.append(path.name)

    assert not offenders, f"infrastructure modules should rely on runtime injection, found env reads in: {offenders}"


def test_ingest_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_ingest_files = sorted(path.name for path in app_root.glob("ingest_*.py"))
    assert not top_level_ingest_files, (
        "ingest domain modules must live under backend/app/ingest/, "
        f"found legacy flat files: {top_level_ingest_files}"
    )

    ingest_pkg = app_root / "ingest"
    assert (ingest_pkg / "__init__.py").exists()
    assert (ingest_pkg / "supervisor.py").exists()
    assert (ingest_pkg / "binance_ws.py").exists()


def test_market_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_market_files = sorted(path.name for path in app_root.glob("market_*.py"))
    assert not top_level_market_files, (
        "market domain modules must live under backend/app/market/, "
        f"found legacy flat files: {top_level_market_files}"
    )

    market_pkg = app_root / "market"
    assert (market_pkg / "__init__.py").exists()
    assert (market_pkg / "runtime.py").exists()
    assert (market_pkg / "runtime_builder.py").exists()


def test_factor_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_factor_files = sorted(path.name for path in app_root.glob("factor_*.py"))
    assert not top_level_factor_files, (
        "factor domain modules must live under backend/app/factor/, "
        f"found legacy flat files: {top_level_factor_files}"
    )

    factor_pkg = app_root / "factor"
    assert (factor_pkg / "__init__.py").exists()
    assert (factor_pkg / "orchestrator.py").exists()
    assert (factor_pkg / "routes.py").exists()


def test_freqtrade_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_freqtrade_files = sorted(path.name for path in app_root.glob("freqtrade_*.py"))
    assert not top_level_freqtrade_files, (
        "freqtrade domain modules must live under backend/app/freqtrade/, "
        f"found legacy flat files: {top_level_freqtrade_files}"
    )

    freqtrade_pkg = app_root / "freqtrade"
    assert (freqtrade_pkg / "__init__.py").exists()
    assert (freqtrade_pkg / "runner.py").exists()
    assert (freqtrade_pkg / "adapter_v1.py").exists()


def test_overlay_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_overlay_files = sorted(path.name for path in app_root.glob("overlay_*.py"))
    assert not top_level_overlay_files, (
        "overlay domain modules must live under backend/app/overlay/, "
        f"found legacy flat files: {top_level_overlay_files}"
    )

    overlay_pkg = app_root / "overlay"
    assert (overlay_pkg / "__init__.py").exists()
    assert (overlay_pkg / "orchestrator.py").exists()
    assert (overlay_pkg / "store.py").exists()


def test_replay_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_replay_files = sorted(path.name for path in app_root.glob("replay_*.py"))
    assert not top_level_replay_files, (
        "replay domain modules must live under backend/app/replay/, "
        f"found legacy flat files: {top_level_replay_files}"
    )

    replay_pkg = app_root / "replay"
    assert (replay_pkg / "__init__.py").exists()
    assert (replay_pkg / "routes.py").exists()
    assert (replay_pkg / "package_service_v1.py").exists()


def test_backtest_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_backtest_files = sorted(path.name for path in app_root.glob("backtest_*.py"))
    assert not top_level_backtest_files, (
        "backtest domain modules must live under backend/app/backtest/, "
        f"found legacy flat files: {top_level_backtest_files}"
    )

    backtest_pkg = app_root / "backtest"
    assert (backtest_pkg / "__init__.py").exists()
    assert (backtest_pkg / "routes.py").exists()
    assert (backtest_pkg / "service.py").exists()


def test_ws_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_ws_files = sorted(path.name for path in app_root.glob("ws_*.py"))
    assert not top_level_ws_files, (
        "ws domain modules must live under backend/app/ws/, "
        f"found legacy flat files: {top_level_ws_files}"
    )

    ws_pkg = app_root / "ws"
    assert (ws_pkg / "__init__.py").exists()
    assert (ws_pkg / "hub.py").exists()
    assert (ws_pkg / "protocol.py").exists()


def test_debug_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_debug_files = sorted(path.name for path in app_root.glob("debug_*.py"))
    assert not top_level_debug_files, (
        "debug modules must live under backend/app/debug/, "
        f"found legacy flat files: {top_level_debug_files}"
    )

    debug_pkg = app_root / "debug"
    assert (debug_pkg / "__init__.py").exists()
    assert (debug_pkg / "hub.py").exists()
    assert (debug_pkg / "routes.py").exists()


def test_ledger_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_ledger_files = sorted(path.name for path in app_root.glob("ledger_*.py"))
    assert not top_level_ledger_files, (
        "ledger modules must live under backend/app/ledger/, "
        f"found legacy flat files: {top_level_ledger_files}"
    )

    ledger_pkg = app_root / "ledger"
    assert (ledger_pkg / "__init__.py").exists()
    assert (ledger_pkg / "alignment.py").exists()
    assert (ledger_pkg / "sync_service.py").exists()


def test_runtime_modules_are_packaged_under_domain_directory() -> None:
    app_root = _backend_app_root()
    top_level_runtime_files = sorted(path.name for path in app_root.glob("runtime_*.py"))
    assert not top_level_runtime_files, (
        "runtime modules must live under backend/app/runtime/, "
        f"found legacy flat files: {top_level_runtime_files}"
    )

    runtime_pkg = app_root / "runtime"
    assert (runtime_pkg / "__init__.py").exists()
    assert (runtime_pkg / "flags.py").exists()
    assert (runtime_pkg / "metrics.py").exists()


def test_shared_route_modules_are_packaged_under_routes_directory() -> None:
    app_root = _backend_app_root()
    legacy_route_files = ["dev_routes.py", "draw_routes.py", "repair_routes.py", "world_routes.py"]
    existing_legacy = sorted(name for name in legacy_route_files if (app_root / name).exists())
    assert not existing_legacy, (
        "shared route modules must live under backend/app/routes/, "
        f"found legacy flat files: {existing_legacy}"
    )

    routes_pkg = app_root / "routes"
    assert (routes_pkg / "__init__.py").exists()
    assert (routes_pkg / "dev.py").exists()
    assert (routes_pkg / "draw.py").exists()
    assert (routes_pkg / "repair.py").exists()
    assert (routes_pkg / "world.py").exists()


def test_factor_semantics_modules_are_packaged_under_factor_directory() -> None:
    app_root = _backend_app_root()
    legacy_files = ["anchor_semantics.py", "pen.py", "pivot.py", "zhongshu.py"]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "factor semantics modules must live under backend/app/factor/, "
        f"found legacy flat files: {existing_legacy}"
    )

    factor_pkg = app_root / "factor"
    assert (factor_pkg / "anchor_semantics.py").exists()
    assert (factor_pkg / "pen.py").exists()
    assert (factor_pkg / "pivot.py").exists()
    assert (factor_pkg / "zhongshu.py").exists()


def test_worktree_modules_are_packaged_under_worktree_directory() -> None:
    app_root = _backend_app_root()
    top_level_worktree_files = sorted(path.name for path in app_root.glob("worktree_*.py"))
    assert not top_level_worktree_files, (
        "worktree modules must live under backend/app/worktree/, "
        f"found legacy flat files: {top_level_worktree_files}"
    )

    worktree_pkg = app_root / "worktree"
    assert (worktree_pkg / "__init__.py").exists()
    assert (worktree_pkg / "manager.py").exists()
    assert (worktree_pkg / "metadata_store.py").exists()
    assert (worktree_pkg / "models.py").exists()
    assert (worktree_pkg / "process_runtime.py").exists()


def test_lifecycle_modules_are_packaged_under_lifecycle_directory() -> None:
    app_root = _backend_app_root()
    legacy_files = [
        "app_lifecycle_service.py",
        "startup_kline_sync.py",
        "shutdown_cancellation_middleware.py",
    ]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "lifecycle modules must live under backend/app/lifecycle/, "
        f"found legacy flat files: {existing_legacy}"
    )

    lifecycle_pkg = app_root / "lifecycle"
    assert (lifecycle_pkg / "__init__.py").exists()
    assert (lifecycle_pkg / "service.py").exists()
    assert (lifecycle_pkg / "startup_kline_sync.py").exists()
    assert (lifecycle_pkg / "shutdown_cancellation_middleware.py").exists()


def test_build_modules_are_packaged_under_build_directory() -> None:
    app_root = _backend_app_root()
    legacy_files = ["artifacts.py", "build_job_manager.py", "package_build_service_base.py"]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "build modules must live under backend/app/build/, "
        f"found legacy flat files: {existing_legacy}"
    )

    build_pkg = app_root / "build"
    assert (build_pkg / "__init__.py").exists()
    assert (build_pkg / "artifacts.py").exists()
    assert (build_pkg / "job_manager.py").exists()
    assert (build_pkg / "service_base.py").exists()


def test_core_modules_are_packaged_under_core_directory() -> None:
    app_root = _backend_app_root()
    legacy_files = [
        "config.py",
        "flags.py",
        "schemas.py",
        "series_id.py",
        "service_errors.py",
        "timeframe.py",
        "shared_ports.py",
    ]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "core modules must live under backend/app/core/, "
        f"found legacy flat files: {existing_legacy}"
    )

    core_pkg = app_root / "core"
    assert (core_pkg / "__init__.py").exists()
    assert (core_pkg / "config.py").exists()
    assert (core_pkg / "flags.py").exists()
    assert (core_pkg / "schemas.py").exists()
    assert (core_pkg / "series_id.py").exists()
    assert (core_pkg / "service_errors.py").exists()
    assert (core_pkg / "timeframe.py").exists()
    assert (core_pkg / "ports.py").exists()


def test_storage_candle_store_modules_are_packaged_under_storage_directory() -> None:
    app_root = _backend_app_root()
    legacy_files = ["store.py", "local_store_runtime.py"]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "candle store modules must live under backend/app/storage/, "
        f"found legacy flat files: {existing_legacy}"
    )

    storage_pkg = app_root / "storage"
    assert (storage_pkg / "candle_store.py").exists()
    assert (storage_pkg / "local_store_runtime.py").exists()


def test_runtime_market_worktree_support_modules_are_packaged_under_domain_directories() -> None:
    app_root = _backend_app_root()
    legacy_files = [
        "blocking.py",
        "ccxt_client.py",
        "derived_timeframes.py",
        "history_bootstrapper.py",
        "whitelist.py",
        "port_allocator.py",
    ]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "runtime/market/worktree support modules must be domain-packaged, "
        f"found legacy flat files: {existing_legacy}"
    )

    assert (app_root / "runtime" / "blocking.py").exists()
    assert (app_root / "market" / "ccxt_client.py").exists()
    assert (app_root / "market" / "derived_timeframes.py").exists()
    assert (app_root / "market" / "history_bootstrapper.py").exists()
    assert (app_root / "market" / "whitelist.py").exists()
    assert (app_root / "worktree" / "port_allocator.py").exists()


def test_bootstrap_and_dependency_aggregation_modules_are_packaged() -> None:
    app_root = _backend_app_root()
    legacy_files = ["container.py", "container_builders.py", "dependencies.py"]
    existing_legacy = sorted(name for name in legacy_files if (app_root / name).exists())
    assert not existing_legacy, (
        "bootstrap and dependency aggregation modules must be packaged, "
        f"found legacy flat files: {existing_legacy}"
    )

    bootstrap_pkg = app_root / "bootstrap"
    assert (bootstrap_pkg / "__init__.py").exists()
    assert (bootstrap_pkg / "container.py").exists()
    assert (bootstrap_pkg / "container_builders.py").exists()

    deps_pkg = app_root / "deps"
    assert (deps_pkg / "__init__.py").exists()
