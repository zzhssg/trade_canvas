from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path

from . import pen as pen_module
from . import zhongshu as zhongshu_module
from .factor_graph import FactorGraph
from .factor_registry import FactorRegistry
from .factor_runtime_config import FactorSettings, factor_logic_version_override


def _file_sha256(path: Path) -> str:
    try:
        data = path.read_bytes()
    except Exception:
        return "missing"
    return hashlib.sha256(data).hexdigest()


def build_series_fingerprint(
    *,
    series_id: str,
    settings: FactorSettings,
    graph: FactorGraph,
    registry: FactorRegistry,
    orchestrator_file: Path,
) -> str:
    files = {
        "factor_orchestrator.py": _file_sha256(orchestrator_file),
        "factor_manifest.py": _file_sha256(orchestrator_file.with_name("factor_manifest.py")),
        "factor_plugin_contract.py": _file_sha256(orchestrator_file.with_name("factor_plugin_contract.py")),
        "factor_plugin_registry.py": _file_sha256(orchestrator_file.with_name("factor_plugin_registry.py")),
        "pen.py": _file_sha256(Path(getattr(pen_module, "__file__", ""))),
        "zhongshu.py": _file_sha256(Path(getattr(zhongshu_module, "__file__", ""))),
    }

    for plugin in sorted(registry.plugins(), key=lambda p: str(p.spec.factor_name)):
        try:
            plugin_file = Path(inspect.getfile(plugin.__class__))
        except Exception:
            continue
        files[f"plugin:{plugin.spec.factor_name}"] = _file_sha256(plugin_file)

    payload = {
        "series_id": str(series_id),
        "graph": list(graph.topo_order),
        "settings": {
            "pivot_window_major": int(settings.pivot_window_major),
            "pivot_window_minor": int(settings.pivot_window_minor),
            "lookback_candles": int(settings.lookback_candles),
            "state_rebuild_event_limit": int(settings.state_rebuild_event_limit),
        },
        "files": files,
        "logic_version_override": factor_logic_version_override(),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
