from __future__ import annotations

import os


def truthy_flag(value: str | None) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(default)
    return truthy_flag(raw)


def resolve_env_bool(name: str, *, fallback: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return bool(fallback)
    return truthy_flag(raw)


def resolve_env_int(name: str, *, fallback: int, minimum: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(int(minimum), int(fallback))
    try:
        return max(int(minimum), int(raw))
    except ValueError:
        return max(int(minimum), int(fallback))


def resolve_env_float(name: str, *, fallback: float, minimum: float = 0.0) -> float:
    raw = (os.environ.get(name) or "").strip()
    fallback_value = max(float(minimum), float(fallback))
    if not raw:
        return fallback_value
    try:
        return max(float(minimum), float(raw))
    except ValueError:
        return fallback_value


def resolve_env_str(name: str, *, fallback: str = "") -> str:
    raw = os.environ.get(name)
    if raw is None:
        return str(fallback).strip()
    return str(raw).strip()


def env_int(name: str, *, default: int, minimum: int = 0) -> int:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return max(int(minimum), int(default))
    try:
        return max(int(minimum), int(raw))
    except ValueError:
        return max(int(minimum), int(default))
