from __future__ import annotations

from dataclasses import dataclass

from bktstr.provenance import resolve_sentiment_sources
from bktstr.regime import (
    BENCHMARK_FIELDS,
    SENTIMENT_REGIME_FIELDS,
    validate_regime_rules,
)
from bktstr.rules import parse_rules

from .data import normalize_symbol
from .validation import SemanticValidationError


@dataclass(frozen=True)
class RegimeInput:
    enabled: bool = True
    rules: str | None = None
    benchmark: str | None = None
    sentiment_enabled: bool = False
    sentiment_sector_benchmark: str | None = None
    sentiment_market_benchmark: str | None = None
    sentiment_data_profile: str = "clean"
    sentiment_sources: tuple[str, ...] = ("price",)


def _optional_symbol(
    value: str | None, *, label: str, field_path: str
) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return normalize_symbol(value, label=label, field_path=field_path)


def _rule_fields(rules: str) -> set[str]:
    try:
        parsed = parse_rules(rules)
    except (TypeError, ValueError) as exc:
        raise SemanticValidationError(str(exc), ("regime.rules",)) from exc
    referenced: set[str] = set()
    for rule in parsed:
        referenced.add(rule.left)
        if isinstance(rule.right, str):
            referenced.add(rule.right)
    return referenced


def normalize_regime_request(
    value: RegimeInput | None,
    *,
    default_rules: str | None = None,
) -> RegimeInput | None:
    """Validate only v0.5 registered, prior-session regime/context rules."""

    if value is None:
        return None
    if not isinstance(value, RegimeInput):
        raise SemanticValidationError(
            "regime must be a RegimeInput or None", ("regime",)
        )
    if type(value.enabled) is not bool:
        raise SemanticValidationError(
            "regime enabled flag must be bool", ("regime.enabled",)
        )
    if type(value.sentiment_enabled) is not bool:
        raise SemanticValidationError(
            "regime sentiment flag must be bool", ("regime.sentiment_enabled",)
        )

    if value.rules is not None and not isinstance(value.rules, str):
        raise SemanticValidationError(
            "regime rules must be a string", ("regime.rules",)
        )
    rules = value.rules.strip() if value.rules and value.rules.strip() else default_rules
    benchmark = _optional_symbol(
        value.benchmark,
        label="benchmark symbol",
        field_path="regime.benchmark",
    )
    sector = _optional_symbol(
        value.sentiment_sector_benchmark,
        label="sentiment sector benchmark symbol",
        field_path="regime.sentiment_sector_benchmark",
    )
    market = _optional_symbol(
        value.sentiment_market_benchmark,
        label="sentiment market benchmark symbol",
        field_path="regime.sentiment_market_benchmark",
    )
    if not value.enabled:
        fields = tuple(
            field
            for present, field in (
                (value.rules, "regime.rules"),
                (benchmark, "regime.benchmark"),
                (value.sentiment_enabled, "regime.sentiment_enabled"),
                (sector, "regime.sentiment_sector_benchmark"),
                (market, "regime.sentiment_market_benchmark"),
            )
            if present
        )
        if fields:
            raise SemanticValidationError(
                "disabled regime cannot include regime or sentiment settings",
                fields,
            )
        return RegimeInput(enabled=False)

    if rules:
        referenced = _rule_fields(rules)
        if referenced & BENCHMARK_FIELDS and benchmark is None:
            raise SemanticValidationError(
                "benchmark is required for benchmark regime fields",
                ("regime.benchmark",),
            )
        if referenced & SENTIMENT_REGIME_FIELDS and not value.sentiment_enabled:
            raise SemanticValidationError(
                "sentiment=true is required for sentiment regime fields",
                ("regime.sentiment_enabled",),
            )
        try:
            validate_regime_rules(
                rules,
                benchmark,
                sentiment_enabled=value.sentiment_enabled,
            )
        except (TypeError, ValueError) as exc:
            raise SemanticValidationError(str(exc), ("regime.rules",)) from exc
    if value.sentiment_enabled:
        missing_benchmarks = tuple(
            field
            for missing, field in (
                (sector is None, "regime.sentiment_sector_benchmark"),
                (market is None, "regime.sentiment_market_benchmark"),
            )
            if missing
        )
        if missing_benchmarks:
            raise SemanticValidationError(
                "sentiment requires both sector and market benchmark symbols",
                missing_benchmarks,
            )
    try:
        resolve_sentiment_sources(value.sentiment_data_profile, ("price",))
    except (AttributeError, TypeError, ValueError) as exc:
        raise SemanticValidationError(
            str(exc), ("regime.sentiment_data_profile",)
        ) from exc
    try:
        profile, sources = resolve_sentiment_sources(
            value.sentiment_data_profile,
            value.sentiment_sources,
        )
    except (AttributeError, TypeError, ValueError) as exc:
        raise SemanticValidationError(
            str(exc), ("regime.sentiment_sources",)
        ) from exc
    return RegimeInput(
        enabled=True,
        rules=rules,
        benchmark=benchmark,
        sentiment_enabled=value.sentiment_enabled,
        sentiment_sector_benchmark=sector,
        sentiment_market_benchmark=market,
        sentiment_data_profile=profile,
        sentiment_sources=sources,
    )


__all__ = ["RegimeInput", "normalize_regime_request"]
