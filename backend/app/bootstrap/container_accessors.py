from __future__ import annotations

from pathlib import Path

from .container_contexts import (
    CoreContainerContext,
    DevContainerContext,
    FactorContainerContext,
    MarketContainerContext,
    ReadContainerContext,
    ReplayContainerContext,
    StoreContainerContext,
)


class AppContainerAccessors:
    project_root: Path
    core: CoreContainerContext
    stores: StoreContainerContext
    factor: FactorContainerContext
    read: ReadContainerContext
    replay: ReplayContainerContext
    market: MarketContainerContext
    dev: DevContainerContext

    @property
    def settings(self):
        return self.core.settings

    @property
    def runtime_flags(self):
        return self.core.runtime_flags

    @property
    def api_gates(self):
        return self.core.api_gates

    @property
    def debug_hub(self):
        return self.core.debug_hub

    @property
    def runtime_metrics(self):
        return self.core.runtime_metrics

    @property
    def worktree_manager(self):
        return self.core.worktree_manager

    @property
    def store(self):
        return self.stores.store

    @property
    def factor_store(self):
        return self.stores.factor_store

    @property
    def feature_store(self):
        return self.stores.feature_store

    @property
    def overlay_store(self):
        return self.stores.overlay_store

    @property
    def factor_orchestrator(self):
        return self.factor.factor_orchestrator

    @property
    def factor_slices_service(self):
        return self.factor.factor_slices_service

    @property
    def factor_read_service(self):
        return self.factor.factor_read_service

    @property
    def feature_orchestrator(self):
        return self.factor.feature_orchestrator

    @property
    def feature_read_service(self):
        return self.factor.feature_read_service

    @property
    def ledger_sync_service(self):
        return self.factor.ledger_sync_service

    @property
    def overlay_orchestrator(self):
        return self.factor.overlay_orchestrator

    @property
    def draw_read_service(self):
        return self.read.draw_read_service

    @property
    def world_read_service(self):
        return self.read.world_read_service

    @property
    def read_repair_service(self):
        return self.read.read_repair_service

    @property
    def replay_prepare_service(self):
        return self.replay.replay_prepare_service

    @property
    def replay_service(self):
        return self.replay.replay_service

    @property
    def market_runtime(self):
        return self.market.market_runtime

    @property
    def lifecycle(self):
        return self.market.lifecycle

    @property
    def backtest_service(self):
        return self.dev.backtest_service
