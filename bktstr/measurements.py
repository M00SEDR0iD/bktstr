from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace

import pandas as pd

from .engine import prepare_bars_for_backtest
from .provenance import SOURCE_REGISTRY, resolve_sentiment_sources
from .regime import attach_regime_to_intraday, build_daily_regime
from .sentiment import attach_sentiment_to_intraday, build_daily_sentiment
from .service import (
    INTRADAY_FEATURE_FORMULA_VERSION,
    REGIME_FORMULA_VERSION,
    SENTIMENT_FORMULA_VERSION,
)
from .variable_registry import VariableRegistry
from .variable_store import VariableSnapshotStore, VariableStoreResult
from .variables import DataTier, ResearchVariableDefinition, VariableKind, VariableRef


_DEFINITION_VERSION = "1.0.0"
_PLUGIN_VERSION = "1.0.0"
_SOURCE_ROLES = ("subject", "benchmark", "sector", "market")
_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")
_INTRADAY_COLUMNS = ("vwap", "rsi14", "volume_ratio20")
_REGIME_COLUMNS = (
    "day_close",
    "day_sma20",
    "day_sma50",
    "day_sma20_slope5",
    "day_return20",
    "benchmark_return20",
    "relative_return20",
)
_SENTIMENT_COLUMNS = (
    "relative_return63_sector",
    "relative_return126_sector",
    "relative_return63_market",
    "relative_return126_market",
    "sma50_slope20",
    "sma100_slope20",
    "sma200_slope20",
    "distance_from_52w_high",
    "days_below_sma50",
    "ema50",
    "ema100",
    "ema200",
    "atr20_pct",
    "realized_vol20",
    "realized_vol60",
    "volatility_ratio",
    "persistence_occupancy",
    "normalized_ema50_distance",
    "persistence_pressure_raw",
    "sentiment_leadership_score",
    "sentiment_trend_score",
    "sentiment_peak_score",
    "sentiment_persistence_score",
    "sentiment_direction",
    "sentiment_completeness",
    "sentiment_confidence",
    "sentiment_multiplier_long",
    "sentiment_multiplier_short",
    "sentiment_momentum20",
    "sentiment_momentum60",
    "sentiment_momentum",
    "sentiment_component_spread",
    "sentiment_volatility_stress",
    "sentiment_fragility",
)


def source_definitions(role: str) -> tuple[ResearchVariableDefinition, ...]:
    """Return the Tier A OHLCV contract for one instrument role."""
    normalized_role = str(role).strip().lower()
    if normalized_role not in _SOURCE_ROLES:
        raise ValueError(f"unsupported source role {role!r}")
    return tuple(
        ResearchVariableDefinition.source(
            id=f"market.{normalized_role}.{column}",
            version=_DEFINITION_VERSION,
            tier=DataTier.A,
            column=column,
            value_dtype="float64",
            frequency="bar",
            units="shares" if column == "volume" else "price",
        )
        for column in _OHLCV_COLUMNS
    )


def _refs(role: str, columns: Iterable[str]) -> tuple[VariableRef, ...]:
    by_column = {item.column: item.ref for item in source_definitions(role)}
    return tuple(by_column[column] for column in columns)


def _measurement(
    *,
    variable_id: str,
    column: str,
    frequency: str,
    inputs: tuple[VariableRef, ...],
    plugin_id: str,
    formula_version: str,
) -> ResearchVariableDefinition:
    return ResearchVariableDefinition(
        id=variable_id,
        version=_DEFINITION_VERSION,
        kind=VariableKind.MEASUREMENT,
        tier=DataTier.B,
        column=column,
        value_dtype="float64",
        frequency=frequency,
        inputs=inputs,
        plugin_id=plugin_id,
        plugin_version=_PLUGIN_VERSION,
        formula_version=formula_version,
    )


def intraday_definitions() -> tuple[ResearchVariableDefinition, ...]:
    subject = {item.column: item.ref for item in source_definitions("subject")}
    inputs_by_column = {
        "vwap": (subject["high"], subject["low"], subject["close"], subject["volume"]),
        "rsi14": (subject["close"],),
        "volume_ratio20": (subject["volume"],),
    }
    return tuple(
        _measurement(
            variable_id=f"technical.{column}",
            column=column,
            frequency="intraday",
            inputs=inputs_by_column[column],
            plugin_id="bktstr.technical",
            formula_version=INTRADAY_FEATURE_FORMULA_VERSION,
        )
        for column in _INTRADAY_COLUMNS
    )


def regime_definitions(
    include_benchmark: bool = True,
) -> tuple[ResearchVariableDefinition, ...]:
    subject_inputs = _refs("subject", ("close",))
    benchmark_inputs = subject_inputs + _refs("benchmark", ("close",))
    columns = _REGIME_COLUMNS if include_benchmark else _REGIME_COLUMNS[:5]
    return tuple(
        _measurement(
            variable_id=f"regime.{column}",
            column=column,
            frequency="1d",
            inputs=benchmark_inputs if column in _REGIME_COLUMNS[5:] else subject_inputs,
            plugin_id="bktstr.regime",
            formula_version=REGIME_FORMULA_VERSION,
        )
        for column in columns
    )


def _sentiment_id(column: str) -> str:
    suffix = column.removeprefix("sentiment_")
    return f"sentiment.{suffix}"


def sentiment_definitions() -> tuple[ResearchVariableDefinition, ...]:
    inputs = (
        *_refs("subject", ("high", "low", "close")),
        *_refs("sector", ("close",)),
        *_refs("market", ("close",)),
    )
    return tuple(
        _measurement(
            variable_id=_sentiment_id(column),
            column=column,
            frequency="1d",
            inputs=inputs,
            plugin_id="bktstr.sentiment",
            formula_version=SENTIMENT_FORMULA_VERSION,
        )
        for column in _SENTIMENT_COLUMNS
    )


def baseline_variable_registry() -> VariableRegistry:
    registry = VariableRegistry()
    for role in _SOURCE_ROLES:
        for definition in source_definitions(role):
            registry.register(definition)
    for definition in (*intraday_definitions(), *regime_definitions(), *sentiment_definitions()):
        registry.register(definition)
    return registry


def _provenance(*source_ids: str) -> dict[str, object]:
    return {
        "source_ids": list(source_ids),
        "source_tiers": {
            source_id: SOURCE_REGISTRY[source_id]["tier"] for source_id in source_ids
        },
    }


def compute_intraday_variables(
    *,
    store: VariableSnapshotStore,
    raw_bars: pd.DataFrame,
    symbol: str,
    timeframe: str,
    regular_hours_only: bool = True,
) -> VariableStoreResult:
    definitions = (*source_definitions("subject"), *intraday_definitions())
    prepared = prepare_bars_for_backtest(
        raw_bars, regular_hours_only=regular_hours_only
    )
    columns = [item.column for item in definitions]
    result = store.resolve(
        namespace="intraday_features",
        definitions=definitions,
        dimensions={
            "symbol": symbol,
            "timeframe": timeframe,
            "regular_hours_only": regular_hours_only,
            "formula_version": INTRADAY_FEATURE_FORMULA_VERSION,
        },
        inputs={"raw": raw_bars},
        provenance=_provenance("price"),
        compute=lambda: prepared[columns],
    )
    return replace(result, legacy_frame=prepared.copy(deep=True))


def compute_regime_variables(
    *,
    store: VariableSnapshotStore,
    subject_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame | None,
    subject: str,
    benchmark: str | None,
) -> VariableStoreResult:
    inputs = {"subject": subject_daily}
    if benchmark_daily is not None:
        inputs["benchmark"] = benchmark_daily
    return store.resolve(
        namespace="daily_regime",
        definitions=regime_definitions(include_benchmark=benchmark_daily is not None),
        dimensions={
            "subject": subject,
            "benchmark": benchmark,
            "formula_version": REGIME_FORMULA_VERSION,
        },
        inputs=inputs,
        provenance=_provenance("price"),
        compute=lambda: build_daily_regime(subject_daily, benchmark_daily),
    )


def compute_sentiment_variables(
    *,
    store: VariableSnapshotStore,
    subject_daily: pd.DataFrame,
    sector_daily: pd.DataFrame,
    market_daily: pd.DataFrame,
    subject: str,
    sector_benchmark: str,
    market_benchmark: str,
    data_profile: str = "clean",
    sources: tuple[str, ...] = ("price",),
) -> VariableStoreResult:
    normalized_profile, normalized_sources = resolve_sentiment_sources(
        data_profile, sources
    )
    return store.resolve(
        namespace="daily_sentiment",
        definitions=sentiment_definitions(),
        dimensions={
            "subject": subject,
            "sector_benchmark": sector_benchmark,
            "market_benchmark": market_benchmark,
            "data_profile": normalized_profile,
            "sources": list(normalized_sources),
            "formula_version": SENTIMENT_FORMULA_VERSION,
        },
        inputs={
            "subject": subject_daily,
            "sector": sector_daily,
            "market": market_daily,
        },
        provenance=_provenance(*normalized_sources),
        compute=lambda: build_daily_sentiment(subject_daily, sector_daily, market_daily),
    )


def _available_definitions(
    definitions: tuple[ResearchVariableDefinition, ...], frame: pd.DataFrame
) -> tuple[ResearchVariableDefinition, ...]:
    by_column = {item.column: item for item in definitions}
    return tuple(by_column[column] for column in frame.columns)


def attach_regime_variables(
    *,
    store: VariableSnapshotStore,
    intraday: pd.DataFrame,
    daily_regime: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> VariableStoreResult:
    definitions = _available_definitions(regime_definitions(), daily_regime)
    attached = attach_regime_to_intraday(intraday, daily_regime)
    columns = [item.column for item in definitions]
    result = store.resolve(
        namespace="intraday_regime_attachment",
        definitions=definitions,
        dimensions={
            "symbol": symbol,
            "timeframe": timeframe,
            "formula_version": REGIME_FORMULA_VERSION,
        },
        inputs={"intraday": intraday, "daily_regime": daily_regime},
        provenance=_provenance("price"),
        compute=lambda: attached[columns],
    )
    return replace(result, legacy_frame=attached.copy(deep=True))


def attach_sentiment_variables(
    *,
    store: VariableSnapshotStore,
    intraday: pd.DataFrame,
    daily_sentiment: pd.DataFrame,
    symbol: str,
    timeframe: str,
) -> VariableStoreResult:
    definitions = _available_definitions(sentiment_definitions(), daily_sentiment)
    attached = attach_sentiment_to_intraday(intraday, daily_sentiment)
    columns = [item.column for item in definitions]
    result = store.resolve(
        namespace="intraday_sentiment_attachment",
        definitions=definitions,
        dimensions={
            "symbol": symbol,
            "timeframe": timeframe,
            "formula_version": SENTIMENT_FORMULA_VERSION,
        },
        inputs={"intraday": intraday, "daily_sentiment": daily_sentiment},
        provenance=_provenance("price"),
        compute=lambda: attached[columns],
    )
    return replace(result, legacy_frame=attached.copy(deep=True))


__all__ = [
    "attach_regime_variables",
    "attach_sentiment_variables",
    "baseline_variable_registry",
    "compute_intraday_variables",
    "compute_regime_variables",
    "compute_sentiment_variables",
    "intraday_definitions",
    "regime_definitions",
    "sentiment_definitions",
    "source_definitions",
]
