from __future__ import annotations

from pathlib import Path

from backend.app.factor.runtime_config import FactorSettings


def test_factor_settings_defaults_are_stable() -> None:
    settings = FactorSettings()
    assert settings.pivot_window_major == 50
    assert settings.pivot_window_minor == 5
    assert settings.lookback_candles == 20000
    assert settings.state_rebuild_event_limit == 50000


def test_factor_runtime_config_no_longer_reads_env_directly() -> None:
    module_path = Path("backend/app/factor/runtime_config.py")
    text = module_path.read_text(encoding="utf-8")
    assert "os.environ" not in text
