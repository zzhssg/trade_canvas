#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_FACTOR_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class FactorScaffoldError(RuntimeError):
    pass


@dataclass(frozen=True)
class FactorScaffoldSpec:
    factor_name: str
    depends_on: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class FactorScaffoldPaths:
    processor_path: Path
    bundle_path: Path


@dataclass(frozen=True)
class FactorScaffoldResult:
    spec: FactorScaffoldSpec
    paths: FactorScaffoldPaths
    dry_run: bool


def _repo_root_default() -> Path:
    return Path(__file__).resolve().parents[1]


def _validate_factor_name(value: str) -> str:
    name = str(value).strip()
    if not _FACTOR_NAME_PATTERN.fullmatch(name):
        raise FactorScaffoldError(f"factor_name_invalid:{name}")
    return name


def _parse_depends_on(value: str) -> tuple[str, ...]:
    raw = str(value or "").strip()
    if not raw:
        return ()

    out: list[str] = []
    for item in raw.split(","):
        dep = str(item).strip()
        if not dep:
            continue
        dep_name = _validate_factor_name(dep)
        if dep_name not in out:
            out.append(dep_name)
    return tuple(out)


def _to_pascal_case(factor_name: str) -> str:
    return "".join(part[:1].upper() + part[1:] for part in factor_name.split("_") if part)


def _title_case(factor_name: str) -> str:
    return " ".join(part[:1].upper() + part[1:] for part in factor_name.split("_") if part)


def _format_depends(depends_on: tuple[str, ...]) -> str:
    if not depends_on:
        return "()"
    quoted = ", ".join(f'"{name}"' for name in depends_on)
    return f"({quoted},)"


def _render_processor(spec: FactorScaffoldSpec) -> str:
    class_name = _to_pascal_case(spec.factor_name)
    event_kind = f"{spec.factor_name}.event"
    return (
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Any, Protocol\n\n"
        "from .plugin_contract import FactorCatalogSpec, FactorCatalogSubFeatureSpec, FactorPluginSpec\n"
        "from .runtime_contract import FactorRuntimeContext\n"
        "from .store import FactorEventWrite\n\n\n"
        f"class _{class_name}TickState(Protocol):\n"
        "    visible_time: int\n"
        "    events: list[FactorEventWrite]\n\n\n"
        "@dataclass(frozen=True)\n"
        f"class {class_name}Processor:\n"
        "    spec: FactorPluginSpec = FactorPluginSpec(\n"
        f"        factor_name=\"{spec.factor_name}\",\n"
        f"        depends_on={_format_depends(spec.depends_on)},\n"
        "        catalog=FactorCatalogSpec(\n"
        f"            label=\"{spec.label}\",\n"
        "            default_visible=True,\n"
        "            sub_features=(\n"
        f"                FactorCatalogSubFeatureSpec(key=\"{event_kind}\", label=\"Event\", default_visible=True),\n"
        "            ),\n"
        "        ),\n"
        "    )\n\n"
        "    def run_tick(self, *, series_id: str, state: _{class_name}TickState, runtime: FactorRuntimeContext) -> None:\n"
        "        _ = series_id\n"
        "        _ = runtime\n"
        "        _ = state\n"
        "        # TODO: 在这里追加你的因子事件\n"
    ).replace("{class_name}", class_name)


def _render_bundle(spec: FactorScaffoldSpec) -> str:
    class_name = _to_pascal_case(spec.factor_name)
    event_kind = f"{spec.factor_name}.event"
    bucket_name = f"{spec.factor_name}_events"
    return (
        "from __future__ import annotations\n\n"
        "from collections.abc import Callable\n"
        "from dataclasses import dataclass\n\n"
        "from ..plugin_contract import FactorPluginSpec\n"
        f"from ..processor_{spec.factor_name} import {class_name}Processor\n"
        "from ..registry import FactorPlugin\n"
        "from ..slice_plugin_contract import FactorSliceBuildContext, FactorSlicePlugin, SliceBucketSpec\n"
        "from ...core.schemas import FactorSliceV1\n"
        "from .common import build_factor_meta\n\n"
        f"_{class_name.upper()}_BUCKET_SPECS: tuple[SliceBucketSpec, ...] = (\n"
        "    SliceBucketSpec(\n"
        f"        factor_name=\"{spec.factor_name}\",\n"
        f"        event_kind=\"{event_kind}\",\n"
        f"        bucket_name=\"{bucket_name}\",\n"
        "    ),\n"
        ")\n\n\n"
        "@dataclass(frozen=True)\n"
        f"class {class_name}SlicePlugin:\n"
        f"    spec: FactorPluginSpec = FactorPluginSpec(factor_name=\"{spec.factor_name}\", depends_on={_format_depends(spec.depends_on)})\n"
        f"    bucket_specs: tuple[SliceBucketSpec, ...] = _{class_name.upper()}_BUCKET_SPECS\n\n"
        "    def build_snapshot(self, ctx: FactorSliceBuildContext) -> FactorSliceV1 | None:\n"
        f"        items = list(ctx.buckets.get(\"{bucket_name}\") or [])\n"
        "        if not items:\n"
        "            return None\n"
        "        return FactorSliceV1(\n"
        "            history={\"events\": items},\n"
        "            head={},\n"
        f"            meta=build_factor_meta(ctx=ctx, factor_name=\"{spec.factor_name}\"),\n"
        "        )\n\n\n"
        "FactorBundleBuilders = tuple[\n"
        "    Callable[[], FactorPlugin],\n"
        "    Callable[[], FactorSlicePlugin],\n"
        "]\n\n\n"
        "def build_bundle() -> FactorBundleBuilders:\n"
        f"    return {class_name}Processor, {class_name}SlicePlugin\n"
    )


def _write_file(*, path: Path, content: str, force: bool, dry_run: bool) -> None:
    if path.exists() and not force:
        raise FactorScaffoldError(f"scaffold_target_exists:{path}")
    if dry_run:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_factor_scaffold(
    *,
    repo_root: Path,
    factor_name: str,
    depends_on: tuple[str, ...],
    label: str | None,
    force: bool,
    dry_run: bool,
) -> FactorScaffoldResult:
    name = _validate_factor_name(factor_name)
    if name in depends_on:
        raise FactorScaffoldError(f"factor_depends_on_self:{name}")

    spec = FactorScaffoldSpec(
        factor_name=name,
        depends_on=tuple(depends_on),
        label=str(label).strip() if str(label or "").strip() else _title_case(name),
    )
    paths = FactorScaffoldPaths(
        processor_path=repo_root / "backend/app/factor" / f"processor_{name}.py",
        bundle_path=repo_root / "backend/app/factor/bundles" / f"{name}.py",
    )

    _write_file(path=paths.processor_path, content=_render_processor(spec), force=force, dry_run=dry_run)
    _write_file(path=paths.bundle_path, content=_render_bundle(spec), force=force, dry_run=dry_run)

    return FactorScaffoldResult(spec=spec, paths=paths, dry_run=bool(dry_run))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="生成 factor 插件骨架（processor + bundle）。")
    parser.add_argument("--factor", required=True, help="因子名（snake_case）。")
    parser.add_argument("--depends-on", default="", help="依赖因子，逗号分隔，例如 pivot,pen")
    parser.add_argument("--label", default="", help="catalog label，默认由 factor_name 自动生成")
    parser.add_argument("--repo-root", default=str(_repo_root_default()), help="仓库根目录")
    parser.add_argument("--force", action="store_true", help="覆盖已存在文件")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不落盘")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = _parse_args(argv)
    try:
        depends_on = _parse_depends_on(args.depends_on)
        result = build_factor_scaffold(
            repo_root=Path(args.repo_root).expanduser().resolve(),
            factor_name=str(args.factor),
            depends_on=depends_on,
            label=str(args.label),
            force=bool(args.force),
            dry_run=bool(args.dry_run),
        )
    except FactorScaffoldError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    mode = "[dry-run] " if result.dry_run else ""
    print(f"{mode}factor scaffold ready: {result.spec.factor_name}")
    print(f"- processor: {result.paths.processor_path}")
    print(f"- bundle:    {result.paths.bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
