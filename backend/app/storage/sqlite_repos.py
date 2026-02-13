from __future__ import annotations

from ..factor_store import FactorStore
from ..overlay_store import OverlayStore
from ..store import CandleStore


class SqliteCandleRepository(CandleStore):
    """
    Thin semantic alias for sqlite candle repository.
    """


class SqliteFactorRepository(FactorStore):
    """
    Thin semantic alias for sqlite factor repository.
    """


class SqliteOverlayRepository(OverlayStore):
    """
    Thin semantic alias for sqlite overlay repository.
    """
