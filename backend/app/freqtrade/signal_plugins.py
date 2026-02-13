from __future__ import annotations

from .signal_plugin_contract import FreqtradeSignalPlugin
from .signal_strategies import build_default_freqtrade_signal_plugins as _discover_default_signal_plugins
from .signal_strategies.pen_direction import PenDirectionSignalPlugin


def build_default_freqtrade_signal_plugins() -> tuple[FreqtradeSignalPlugin, ...]:
    return _discover_default_signal_plugins()


__all__ = [
    "PenDirectionSignalPlugin",
    "build_default_freqtrade_signal_plugins",
]
