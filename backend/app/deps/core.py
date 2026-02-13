from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException
from starlette.requests import HTTPConnection

from ..core.config import Settings
from ..bootstrap.container import AppContainer
from ..runtime.api_gates import ApiGateConfig
from ..runtime.flags import RuntimeFlags


def get_app_container(conn: HTTPConnection) -> AppContainer:
    container = getattr(conn.app.state, "container", None)
    if isinstance(container, AppContainer):
        return container
    raise HTTPException(status_code=500, detail="container_not_ready")


def get_settings(container: AppContainer = Depends(get_app_container)) -> Settings:
    return container.settings


def get_runtime_flags(container: AppContainer = Depends(get_app_container)) -> RuntimeFlags:
    return container.runtime_flags


def get_api_gates(container: AppContainer = Depends(get_app_container)) -> ApiGateConfig:
    return container.api_gates


AppContainerDep = Annotated[AppContainer, Depends(get_app_container)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
RuntimeFlagsDep = Annotated[RuntimeFlags, Depends(get_runtime_flags)]
ApiGatesDep = Annotated[ApiGateConfig, Depends(get_api_gates)]
