from __future__ import annotations

from dataclasses import is_dataclass
import os
from urllib.parse import parse_qs

import uvicorn

from . import __version__
from .build_info import runtime_build_info
from .service import (
    BacktestRequest,
    INTRADAY_FEATURE_FORMULA_VERSION,
    REGIME_FORMULA_VERSION,
    SENTIMENT_FORMULA_VERSION,
)
from bktstr_cache.derived import CACHE_FORMAT_VERSION
from .provenance import capability_provenance
from .measurements import baseline_variable_registry
from .strategies import baseline_strategy_registry
from .variables import DataTier


def _registered_variable_capabilities() -> dict:
    definitions = tuple(baseline_variable_registry().definitions.values())

    def definition_payload(definition) -> dict:
        display = definition.display
        return {
            "id": definition.id,
            "version": definition.version,
            "kind": definition.kind.value,
            "tier": definition.tier.value,
            "column": definition.column,
            "value_dtype": definition.value_dtype,
            "frequency": definition.frequency,
            "units": definition.units,
            "inputs": [
                {"id": item.id, "version": item.version, "tier": item.tier.value}
                for item in definition.inputs
            ],
            "lineage": {
                "plugin_id": definition.plugin_id,
                "plugin_version": definition.plugin_version,
                "formula_version": definition.formula_version,
            },
            "suggestion_policy": {
                "method": definition.suggestion_policy.method,
                "rationale": definition.suggestion_policy.rationale,
            },
            "gui": None
            if display is None
            else {
                "label": display.label,
                "description": display.description,
                "category": display.category,
                "preferred_chart": display.preferred_chart,
                "color_hint": display.color_hint,
                "strategy_owned": display.strategy_owned,
            },
        }

    tiers = {}
    for tier in DataTier:
        tier_definitions = tuple(
            definition for definition in definitions if definition.tier is tier
        )
        tiers[tier.value] = {
            "immutable": all(
                is_dataclass(definition)
                and definition.__dataclass_params__.frozen
                for definition in tier_definitions
            ),
            "examples": sorted(
                {
                    part
                    for definition in tier_definitions
                    for part in (
                        definition.id.split(".", 1)[0],
                        definition.id.rsplit(".", 1)[-1],
                    )
                }
            ),
            "definitions": [definition_payload(item) for item in tier_definitions],
        }
    return {
        "tiers": tiers,
        "automatic_backfill": False,
        "missing_data": {
            "behavior": "fail with a deterministic suggestion; source arrays are never changed",
            "suggestions_applied": False,
        },
    }


def _registered_baseline_strategy_capability() -> dict:
    definition = next(iter(baseline_strategy_registry().definitions.values()))
    return {
        "id": definition.id,
        "version": definition.version,
        "schema_version": definition.schema_version,
        "name": definition.name,
        "description": definition.description,
        "instrument_roles": list(definition.instrument_roles),
        "timeframe": definition.timeframe,
        "calendar": definition.calendar,
        "timezone": definition.timezone,
        "execution_model": definition.execution_model_id,
        "execution_model_version": definition.execution_model_version,
        "parameters": [
            {
                "name": parameter.name,
                "type": parameter.value_type.__name__,
                "default": parameter.default,
                "minimum": parameter.minimum,
                "maximum": parameter.maximum,
                "choices": list(parameter.choices),
                "overridable": parameter.overridable,
                "allow_none": parameter.allow_none,
                "ui_metadata": dict(parameter.ui_metadata),
            }
            for parameter in definition.parameters
        ],
        "variable_uses": [
            {
                "id": use.variable.id,
                "version": use.variable.version,
                "tier": use.variable.tier.value,
                "role": use.role.value,
                "rule": use.rule,
                "forceable": use.forceable,
            }
            for use in definition.variable_uses
        ],
        "filters": [
            {
                "id": item.id,
                "version": item.version,
                "tier": item.tier.value,
                "role": item.role.value,
                "rule": item.rule,
                "forceable": item.forceable,
                "optional": item.optional,
            }
            for item in definition.filters
        ],
        "evidence_tier_opt_ins": [item.value for item in definition.evidence_tier_opt_ins],
    }


CAPABILITIES = {
    "service": "bktstr",
    "version": __version__,
    "timeframes": ["1m", "5m", "15m", "1h", "1d"],
    "sides": ["long", "short"],
    "rule_syntax": {
        "examples": [
            "close.cross_below:vwap",
            "close.cross_above:vwap",
            "rsi14.lt:45",
            "rsi14.gt:55",
            "volume_ratio20.gt:1.5",
        ],
        "combine": "comma-separated rules are ANDed",
        "operators": ["lt", "lte", "gt", "gte", "eq", "cross_below", "cross_above"],
    },
    "regime": {
        "parameter": "regime",
        "benchmark_parameter": "benchmark",
        "fields": [
            "day_close",
            "day_sma20",
            "day_sma50",
            "day_sma20_slope5",
            "day_return20",
            "benchmark_return20",
            "relative_return20",
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "sentiment_fields_require": "sentiment=true",
        "operators": ["lt", "lte", "gt", "gte", "eq"],
        "lookahead_guard": "intraday session uses latest completed daily feature row strictly before that session date",
    },
    "sentiment": {
        "enabled_parameter": "sentiment",
        "sector_benchmark_parameter": "sentiment_sector_benchmark",
        "market_benchmark_parameter": "sentiment_market_benchmark",
        "direction_range": [-1.0, 1.0],
        "confidence_range": [0.0, 1.0],
        "momentum_range": [-1.0, 1.0],
        "fragility_range": [0.0, 1.0],
        "multiplier_range": [0.5, 1.5],
        "raw_features": [
            "relative_return63_sector",
            "relative_return126_sector",
            "relative_return63_market",
            "relative_return126_market",
            "distance_from_52w_high",
            "sma50_slope20",
            "sma100_slope20",
            "sma200_slope20",
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
        ],
        "component_scores": [
            "sentiment_leadership_score",
            "sentiment_trend_score",
            "sentiment_peak_score",
            "sentiment_persistence_score",
        ],
        "outputs": [
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_completeness",
            "sentiment_multiplier_long",
            "sentiment_multiplier_short",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "component_weights": {
            "leadership": 0.35,
            "trend": 0.30,
            "peak": 0.20,
            "persistence": 0.15,
        },
        "multipliers_are_informational": True,
        "filterable_fields": [
            "sentiment_direction",
            "sentiment_confidence",
            "sentiment_momentum20",
            "sentiment_momentum60",
            "sentiment_momentum",
            "sentiment_component_spread",
            "sentiment_volatility_stress",
            "sentiment_fragility",
        ],
        "coverage_fields": [
            "requested_warmup_start",
            "coverage_start",
            "coverage_end",
            "warmup_degraded",
        ],
        "optional_warmup_behavior": "degrade completeness and report coverage; required-period data remains strict",
        "data_profile_parameter": "sentiment_data_profile",
        "sources_parameter": "sentiment_sources",
        "data_profiles": capability_provenance(),
        "lookahead_guard": "intraday session uses latest completed sentiment row strictly before that session date",
    },
    "execution_model": {
        "entry": "next bar open after signal",
        "same_bar_stop_target": "stop first (conservative)",
        "slippage": "applied adversely to entry and exit",
        "default_regular_hours_only": True,
        "default_same_day_only": True,
        "entry_window": "optional entry_start_time/entry_end_time in America/New_York, HH:MM; end is exclusive",
    },
    "providers": {
        "massive": "full-range pagination with 429/5xx retry; used when MASSIVE_API_KEY is configured",
        "yahoo": "fallback for recent intraday data only",
    },
    "release": {
        "build": runtime_build_info(),
        "feature_formula_versions": {
            "intraday": INTRADAY_FEATURE_FORMULA_VERSION,
            "regime": REGIME_FORMULA_VERSION,
            "sentiment": SENTIMENT_FORMULA_VERSION,
        },
        "derived_cache_format_version": CACHE_FORMAT_VERSION,
    },
    "cache": {
        "type": "daily compressed OHLCV files",
        "persistent_when": "Railway Volume is attached or BKTSTR_CACHE_DIR is set",
        "default_path": "RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache or /tmp/bktstr-cache",
        "raw": {
            "type": "daily compressed OHLCV files",
            "persistent_when": "Railway Volume is attached or BKTSTR_CACHE_DIR is set",
            "default_path": "RAILWAY_VOLUME_MOUNT_PATH/bktstr-cache or /tmp/bktstr-cache",
        },
        "derived": {
            "type": "deterministic feature/context DataFrames",
            "namespaces": ["intraday_features", "daily_regime", "daily_sentiment"],
            "toggle": "BKTSTR_DERIVED_CACHE_ENABLED",
            "default_enabled": True,
            "override_path_variable": "BKTSTR_DERIVED_CACHE_DIR",
            "strategy_decisions_cached": False,
        },
    },
    "research_variables": _registered_variable_capabilities(),
    "strategies": {"baseline": _registered_baseline_strategy_capability()},
}


def health_payload() -> dict:
    return {
        "status": "ok",
        "service": "bktstr",
        "version": __version__,
        **runtime_build_info(),
    }


def _first(params: dict[str, list[str]], name: str, default: str | None = None) -> str:
    values = params.get(name)
    if values:
        return values[0]
    if default is None:
        raise ValueError(f"missing required query parameter '{name}'")
    return default


def _bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"invalid boolean '{value}'")


def parse_backtest_query(query: str) -> tuple[BacktestRequest, dict]:
    params = parse_qs(query, keep_blank_values=False)
    request = BacktestRequest.from_values(
        symbol=_first(params, "symbol"),
        start=_first(params, "start"),
        end=_first(params, "end"),
        timeframe=_first(params, "timeframe", "1m"),
        side=_first(params, "side", "long"),
        entry=_first(params, "entry"),
        stop_pct=float(_first(params, "stop_pct", "1.0")),
        target_pct=float(_first(params, "target_pct", "3.0")),
        max_hold_minutes=int(_first(params, "max_hold_minutes", "240")),
        position_size=float(_first(params, "position_size", "1000")),
        starting_capital=float(_first(params, "starting_capital", "10000")),
        slippage_bps=float(_first(params, "slippage_bps", "2")),
        regular_hours_only=_bool(_first(params, "regular_hours_only", "true")),
        same_day_only=_bool(_first(params, "same_day_only", "true")),
        entry_start_time=_first(params, "entry_start_time", "") or None,
        entry_end_time=_first(params, "entry_end_time", "") or None,
        regime=_first(params, "regime", "") or None,
        benchmark=_first(params, "benchmark", "") or None,
        sentiment=_bool(_first(params, "sentiment", "false")),
        sentiment_sector_benchmark=_first(params, "sentiment_sector_benchmark", "") or None,
        sentiment_market_benchmark=_first(params, "sentiment_market_benchmark", "") or None,
        sentiment_data_profile=_first(params, "sentiment_data_profile", "clean"),
        sentiment_sources=_first(params, "sentiment_sources", "") or None,
    )
    trade_limit = int(_first(params, "trade_limit", "100"))
    if not 0 <= trade_limit <= 1000:
        raise ValueError("trade_limit must be between 0 and 1000")
    return request, {"trade_limit": trade_limit}


def _trim_result(result: dict, trade_limit: int) -> dict:
    trades = result.get("trades", [])
    result = dict(result)
    result["trades_total"] = len(trades)
    result["trades"] = trades[:trade_limit]
    result["trades_returned"] = len(result["trades"])
    result["trades_truncated"] = len(trades) > trade_limit
    return result


def main() -> None:
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("bktstr.api.app:create_app", factory=True, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
