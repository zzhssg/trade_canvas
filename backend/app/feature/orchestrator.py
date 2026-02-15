from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from ..factor.capability_manifest import (
    FactorCapabilitySpec,
    build_default_factor_capability_manifest,
)
from ..factor.manifest import FactorManifest
from ..factor.store import FactorStore
from .contracts import FeatureValue
from .store import FeatureStore, FeatureVectorWrite


@dataclass(frozen=True)
class FeatureSettings:
    ingest_enabled: bool = True


@dataclass(frozen=True)
class FeatureIngestResult:
    wrote: int
    head_time: int | None


class FeatureOrchestrator:
    def __init__(
        self,
        *,
        factor_store: FactorStore,
        feature_store: FeatureStore,
        factor_manifest: FactorManifest | None = None,
        capability_overrides: dict[str, FactorCapabilitySpec] | None = None,
        settings: FeatureSettings | None = None,
    ) -> None:
        self._factor_store = factor_store
        self._feature_store = feature_store
        self._settings = settings or FeatureSettings()
        self._capabilities = build_default_factor_capability_manifest(
            manifest=factor_manifest,
            overrides=capability_overrides,
        )

    def enabled(self) -> bool:
        return bool(self._settings.ingest_enabled)

    def head_time(self, series_id: str) -> int | None:
        return self._feature_store.head_time(series_id)

    def reset_series(self, *, series_id: str) -> None:
        with self._feature_store.connect() as conn:
            self._feature_store.clear_series_in_conn(conn, series_id=series_id)
            conn.commit()

    def _enabled_feature_factors(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                str(item.factor_name)
                for item in self._capabilities
                if bool(item.enable_feature)
            )
        )

    @staticmethod
    def _kind_feature_key(*, factor_name: str, event_kind: str) -> str:
        factor = str(factor_name or "").strip()
        kind = str(event_kind or "").strip()
        if not factor:
            return "event"
        prefix = f"{factor}."
        if kind.startswith(prefix):
            kind = kind[len(prefix) :]
        normalized = kind.replace(".", "_").strip("_")
        if not normalized:
            return "event"
        return normalized

    @staticmethod
    def _safe_feature_value(value: object) -> FeatureValue:
        if value is None:
            return None
        if isinstance(value, (bool, int, float, str)):
            return value
        return None

    def _build_feature_rows(
        self,
        *,
        series_id: str,
        start_time: int,
        up_to_time: int,
        enabled_factors: tuple[str, ...],
    ) -> list[FeatureVectorWrite]:
        if not enabled_factors:
            return []
        enabled_set = set(enabled_factors)
        rows = self._factor_store.get_events_between_times(
            series_id=series_id,
            factor_name=None,
            start_candle_time=int(start_time),
            end_candle_time=int(up_to_time),
            limit=200000,
        )
        count_by_time: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        value_by_time: dict[int, dict[str, FeatureValue]] = defaultdict(dict)
        for row in rows:
            factor_name = str(row.factor_name or "")
            if factor_name not in enabled_set:
                continue
            candle_time = int(row.candle_time)
            bucket = count_by_time[candle_time]
            bucket["feature_event_count"] += 1
            bucket[f"{factor_name}_event_count"] += 1
            kind_key = self._kind_feature_key(
                factor_name=factor_name,
                event_kind=str(row.kind or ""),
            )
            bucket[f"{factor_name}_{kind_key}_count"] += 1

            direction_value = self._safe_feature_value(dict(row.payload or {}).get("direction"))
            if direction_value is not None:
                value_by_time[candle_time][f"{factor_name}_{kind_key}_direction"] = direction_value

        out: list[FeatureVectorWrite] = []
        for candle_time in sorted(count_by_time.keys()):
            values: dict[str, FeatureValue] = {}
            for key, value in count_by_time[candle_time].items():
                values[key] = float(value)
            values.update(value_by_time.get(candle_time, {}))
            out.append(
                FeatureVectorWrite(
                    series_id=str(series_id),
                    candle_time=int(candle_time),
                    candle_id=f"{series_id}:{int(candle_time)}",
                    values=dict(values),
                )
            )
        return out

    def ingest_closed(self, *, series_id: str, up_to_candle_time: int) -> FeatureIngestResult:
        if not self.enabled():
            return FeatureIngestResult(wrote=0, head_time=self.head_time(series_id))
        up_to = int(up_to_candle_time or 0)
        if up_to <= 0:
            return FeatureIngestResult(wrote=0, head_time=self.head_time(series_id))

        enabled_factors = self._enabled_feature_factors()
        if not enabled_factors:
            return FeatureIngestResult(wrote=0, head_time=self.head_time(series_id))

        factor_head = int(self._factor_store.head_time(series_id) or 0)
        if factor_head < up_to:
            raise RuntimeError(f"feature_factor_out_of_sync:{series_id}:{factor_head}:{up_to}")

        current_head = int(self._feature_store.head_time(series_id) or 0)
        if up_to <= current_head:
            return FeatureIngestResult(wrote=0, head_time=current_head)

        start_time = int(current_head + 1) if current_head > 0 else 0
        feature_rows = self._build_feature_rows(
            series_id=series_id,
            start_time=int(start_time),
            up_to_time=int(up_to),
            enabled_factors=enabled_factors,
        )

        with self._feature_store.connect() as conn:
            wrote = self._feature_store.upsert_rows_in_conn(conn, rows=feature_rows)
            self._feature_store.upsert_head_time_in_conn(conn, series_id=series_id, head_time=int(up_to))
            conn.commit()
        return FeatureIngestResult(wrote=int(wrote), head_time=int(up_to))
