from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from ..bootstrap.container import AppContainer
from ..overlay.package_service_v1 import OverlayReplayPackageServiceV1
from ..replay.package_service_v1 import ReplayPackageServiceV1
from ..replay.prepare_service import ReplayPrepareService
from .core import get_app_container


def get_replay_service(container: AppContainer = Depends(get_app_container)) -> ReplayPackageServiceV1:
    return container.replay_service


def get_replay_prepare_service(container: AppContainer = Depends(get_app_container)) -> ReplayPrepareService:
    return container.replay_prepare_service


def get_overlay_package_service(
    container: AppContainer = Depends(get_app_container),
) -> OverlayReplayPackageServiceV1:
    return container.overlay_pkg_service


ReplayServiceDep = Annotated[ReplayPackageServiceV1, Depends(get_replay_service)]
ReplayPrepareServiceDep = Annotated[ReplayPrepareService, Depends(get_replay_prepare_service)]
OverlayPackageServiceDep = Annotated[OverlayReplayPackageServiceV1, Depends(get_overlay_package_service)]
