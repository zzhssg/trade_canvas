from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..schemas import GetFactorSlicesResponseV1
from .store import OverlayInstructionVersionRow


@dataclass(frozen=True)
class OverlayIntegrityContext:
    series_id: str
    slices: GetFactorSlicesResponseV1
    latest_defs: list[OverlayInstructionVersionRow]


@dataclass(frozen=True)
class OverlayIntegrityResult:
    plugin_name: str
    should_rebuild: bool
    reason: str | None = None


class OverlayIntegrityPlugin(Protocol):
    @property
    def name(self) -> str: ...

    def evaluate(self, *, ctx: OverlayIntegrityContext) -> OverlayIntegrityResult: ...


def _to_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


@dataclass(frozen=True)
class AnchorCurrentStartIntegrityPlugin:
    name: str = "anchor.current.start"

    def evaluate(self, *, ctx: OverlayIntegrityContext) -> OverlayIntegrityResult:
        expected_start = 0
        try:
            anchor_snapshot = (ctx.slices.snapshots or {}).get("anchor")
            anchor_head = (anchor_snapshot.head if anchor_snapshot is not None else {}) or {}
            current_ref = anchor_head.get("current_anchor_ref") if isinstance(anchor_head, dict) else None
            if isinstance(current_ref, dict):
                expected_start = _to_int(current_ref.get("start_time"))
        except Exception:
            expected_start = 0

        if expected_start <= 0:
            return OverlayIntegrityResult(plugin_name=self.name, should_rebuild=False)

        rendered_start = 0
        current_def = next(
            (d for d in ctx.latest_defs if str(d.kind) == "polyline" and str(d.instruction_id) == "anchor.current"),
            None,
        )
        if current_def is not None:
            points = current_def.payload.get("points")
            if isinstance(points, list) and points:
                first = points[0]
                if isinstance(first, dict):
                    rendered_start = _to_int(first.get("time"))
        if rendered_start != expected_start:
            return OverlayIntegrityResult(
                plugin_name=self.name,
                should_rebuild=True,
                reason=f"expected_start={expected_start},rendered_start={rendered_start}",
            )
        return OverlayIntegrityResult(plugin_name=self.name, should_rebuild=False)


@dataclass(frozen=True)
class ZhongshuSignatureIntegrityPlugin:
    name: str = "zhongshu.signature"

    def evaluate(self, *, ctx: OverlayIntegrityContext) -> OverlayIntegrityResult:
        expected_has = False
        expected_ids: set[str] = set()
        try:
            zhongshu_snapshot = (ctx.slices.snapshots or {}).get("zhongshu")
            if zhongshu_snapshot is not None:
                zhongshu_history = (
                    (zhongshu_snapshot.history or {}) if isinstance(zhongshu_snapshot.history, dict) else {}
                )
                zhongshu_head = (zhongshu_snapshot.head or {}) if isinstance(zhongshu_snapshot.head, dict) else {}
                dead_items = zhongshu_history.get("dead")
                alive_items = zhongshu_head.get("alive")
                if isinstance(dead_items, list):
                    for item in dead_items:
                        if not isinstance(item, dict):
                            continue
                        start_time = _to_int(item.get("start_time"))
                        end_time = _to_int(item.get("end_time"))
                        if start_time <= 0 or end_time <= 0:
                            continue
                        zg = _to_float(item.get("zg"))
                        zd = _to_float(item.get("zd"))
                        base_id = f"zhongshu.dead:{start_time}:{end_time}:{zg:.6f}:{zd:.6f}"
                        expected_ids.add(f"{base_id}:top")
                        expected_ids.add(f"{base_id}:bottom")
                if isinstance(alive_items, list) and alive_items:
                    expected_ids.add("zhongshu.alive:top")
                    expected_ids.add("zhongshu.alive:bottom")
                expected_has = bool(
                    (isinstance(dead_items, list) and len(dead_items) > 0)
                    or (isinstance(alive_items, list) and len(alive_items) > 0)
                )
        except Exception:
            expected_has = False
            expected_ids = set()

        rendered_ids = {str(d.instruction_id) for d in ctx.latest_defs if str(d.instruction_id).startswith("zhongshu.")}
        rendered_has = bool(rendered_ids)
        if rendered_has != expected_has:
            return OverlayIntegrityResult(
                plugin_name=self.name,
                should_rebuild=True,
                reason=f"expected_has={int(expected_has)},rendered_has={int(rendered_has)}",
            )
        if rendered_ids != expected_ids:
            return OverlayIntegrityResult(
                plugin_name=self.name,
                should_rebuild=True,
                reason=f"expected_ids={len(expected_ids)},rendered_ids={len(rendered_ids)}",
            )
        return OverlayIntegrityResult(plugin_name=self.name, should_rebuild=False)


def build_default_overlay_integrity_plugins() -> tuple[OverlayIntegrityPlugin, ...]:
    return (
        AnchorCurrentStartIntegrityPlugin(),
        ZhongshuSignatureIntegrityPlugin(),
    )


def evaluate_overlay_integrity(
    *,
    series_id: str,
    slices: GetFactorSlicesResponseV1,
    latest_defs: list[OverlayInstructionVersionRow],
    plugins: tuple[OverlayIntegrityPlugin, ...] | None = None,
) -> tuple[bool, list[OverlayIntegrityResult]]:
    check_plugins = tuple(plugins or build_default_overlay_integrity_plugins())
    ctx = OverlayIntegrityContext(
        series_id=series_id,
        slices=slices,
        latest_defs=latest_defs,
    )
    out: list[OverlayIntegrityResult] = []
    should_rebuild = False
    for plugin in check_plugins:
        result = plugin.evaluate(ctx=ctx)
        out.append(result)
        if bool(result.should_rebuild):
            should_rebuild = True
    return should_rebuild, out
