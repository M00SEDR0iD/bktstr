from __future__ import annotations

from dataclasses import dataclass

from bktstr.provenance import resolve_sentiment_sources
from bktstr.regime import validate_regime_rules

from .data import normalize_symbol


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


def _optional_symbol(value: str | None, *, label: str) -> str | None:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    return normalize_symbol(value, label=label)


def normalize_regime_request(
    value: RegimeInput | None,
    *,
    default_rules: str | None = None,
) -> RegimeInput | None:
    """Validate only v0.5 registered, prior-session regime/context rules."""

    if value is None:
        return None
    if not isinstance(value, RegimeInput):
        raise TypeError("regime must be a RegimeInput or None")
    if type(value.enabled) is not bool or type(value.sentiment_enabled) is not bool:
        raise TypeError("regime flags must be bool")

    rules = value.rules.strip() if value.rules and value.rules.strip() else default_rules
    benchmark = _optional_symbol(value.benchmark, label="benchmark symbol")
    sector = _optional_symbol(
        value.sentiment_sector_benchmark, label="sentiment benchmark symbol"
    )
    market = _optional_symbol(
        value.sentiment_market_benchmark, label="sentiment benchmark symbol"
    )
    if not value.enabled:
        if any((value.rules, benchmark, value.sentiment_enabled, sector, market)):
            raise ValueError("disabled regime cannot include regime or sentiment settings")
        return RegimeInput(enabled=False)

    if rules:
        validate_regime_rules(
            rules,
            benchmark,
            sentiment_enabled=value.sentiment_enabled,
        )
    if value.sentiment_enabled and (sector is None or market is None):
        raise ValueError(
            "sentiment requires both sector and market benchmark symbols"
        )
    profile, sources = resolve_sentiment_sources(
        value.sentiment_data_profile,
        value.sentiment_sources,
    )
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
