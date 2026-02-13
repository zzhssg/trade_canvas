from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from starlette.requests import HTTPConnection

from ..config import Settings
from ..container import AppContainer
from ..flags import FeatureFlags
from ..runtime.flags import RuntimeFlags


def get_app_container(conn: HTTPConnection) -> AppContainer:
    container = getattr(conn.app.state, "container", None)
    if isinstance(container, AppContainer):
        return container
    raise HTTPException(status_code=500, detail="container_not_ready")


def get_settings(container: AppContainer = Depends(get_app_container)) -> Settings:
    return container.settings


def get_feature_flags(container: AppContainer = Depends(get_app_container)) -> FeatureFlags:
    return container.flags


def get_runtime_flags(container: AppContainer = Depends(get_app_container)) -> RuntimeFlags:
    return container.runtime_flags


AppContainerDep = Annotated[AppContainer, Depends(get_app_container)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
FeatureFlagsDep = Annotated[FeatureFlags, Depends(get_feature_flags)]
RuntimeFlagsDep = Annotated[RuntimeFlags, Depends(get_runtime_flags)]
