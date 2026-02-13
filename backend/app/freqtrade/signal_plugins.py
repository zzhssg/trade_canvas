from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..factor.plugin_contract import FactorPluginSpec
from .signal_plugin_contract import FreqtradeSignalBucketSpec, FreqtradeSignalContext, FreqtradeSignalPlugin


@dataclass(frozen=True)
class PenDirectionSignalPlugin:
    spec: FactorPluginSpec = FactorPluginSpec(factor_name="signal.pen_direction", depends_on=())
    bucket_specs: tuple[FreqtradeSignalBucketSpec, ...] = (
        FreqtradeSignalBucketSpec(
            factor_name="pen",
            event_kind="pen.confirmed",
            bucket_name="pen_confirmed",
            sort_keys=("visible_time", "start_time"),
        ),
    )

    def prepare_dataframe(self, *, dataframe: Any) -> None:
        dataframe["tc_pen_confirmed"] = 0
        dataframe["tc_pen_dir"] = None
        dataframe["tc_enter_long"] = 0
        dataframe["tc_enter_short"] = 0

    def apply(self, *, ctx: FreqtradeSignalContext) -> None:
        pen_events = list(ctx.buckets.get("pen_confirmed") or [])
        directions_by_time: dict[int, list[int]] = {}
        for payload in pen_events:
            visible_time = int(payload.get("visible_time") or payload.get("candle_time") or 0)
            if visible_time <= 0:
                continue
            try:
                direction = int(payload.get("direction") or 0)
            except Exception:
                continue
            if direction not in {-1, 1}:
                continue
            directions_by_time.setdefault(visible_time, []).append(direction)

        for idx in ctx.order:
            row_time = int(ctx.times_by_index.get(idx) or 0)
            if row_time <= 0:
                continue
            dirs = directions_by_time.get(row_time)
            if not dirs:
                continue
            direction = int(dirs[-1])
            ctx.dataframe.at[idx, "tc_pen_confirmed"] = 1
            ctx.dataframe.at[idx, "tc_pen_dir"] = direction
            if direction == 1:
                ctx.dataframe.at[idx, "tc_enter_long"] = 1
            elif direction == -1:
                ctx.dataframe.at[idx, "tc_enter_short"] = 1


def build_default_freqtrade_signal_plugins() -> tuple[FreqtradeSignalPlugin, ...]:
    return (PenDirectionSignalPlugin(),)
