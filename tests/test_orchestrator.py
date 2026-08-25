from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from bktstr.cache import BarCache, CachedProvider
from bktstr.measurements import baseline_variable_registry
from bktstr.orchestrator import (
    OrchestratorDependencies,
    StrategyRunError,
    execute_strategy_run,
    legacy_request_to_strategy_run,
)
from bktstr.regime import build_daily_regime
from bktstr.sentiment import build_daily_sentiment
from bktstr.service import BacktestRequest
from bktstr.strategies import (
    StrategyFilterDefinition,
    StrategyRegistry,
    baseline_strategy_definition,
)
from bktstr.variable_store import VariableSnapshotStore
from bktstr.variables import (
    DataTier,
    FilterRole,
    ResearchVariableDefinition,
    VariableContractError,
    VariableRef,
)
from bktstr_cache.derived import DerivedFrameCache
from tests.v05_fixtures import daily_fixture, intraday_fixture


class FixtureProvider:
    """External-data boundary fake with realistic Tier A frames."""

    def __init__(self, *, empty_intraday: bool = False, secret: str = "fixture-secret") -> None:
        self.empty_intraday = empty_intraday
        self.secret = secret
        self.calls: list[tuple[str, date, date, str]] = []

    async def fetch_bars(
        self, symbol: str, start: date, end: date, timeframe: str = "1m"
    ) -> pd.DataFrame:
        self.calls.append((symbol, start, end, timeframe))
        if timeframe == "1d":
            return _daily_bars(symbol, start, end)
        if self.empty_intraday:
            return intraday_fixture().iloc[0:0]
        return intraday_fixture()


class ExplodingProvider(FixtureProvider):
    async def fetch_bars(
        self, symbol: str, start: date, end: date, timeframe: str = "1m"
    ) -> pd.DataFrame:
        raise RuntimeError(f"provider rejected request with credential {self.secret}")


def _daily_bars(symbol: str, start: date, end: date) -> pd.DataFrame:
    """Return the same date-indexed provider history regardless of fetch chunking."""
    frame = daily_fixture(
        date(2024, 1, 1),
        date(2027, 12, 31),
        {"NVDA": 300.0, "SOXX": 200.0, "QQQ": 500.0}[symbol],
        {"NVDA": -0.2, "SOXX": 0.1, "QQQ": 0.05}[symbol],
    )
    return frame.loc[(frame.index.date >= start) & (frame.index.date <= end)].copy()


def _dependencies(
    tmp_path: Path,
    upstream: FixtureProvider,
    *,
    strategy_registry: StrategyRegistry | None = None,
    variable_registry=None,
    derived_cache_enabled: bool = True,
) -> OrchestratorDependencies:
    return OrchestratorDependencies(
        provider=CachedProvider(
            upstream,
            BarCache(tmp_path / "raw"),
            provider_name="fixture",
            today_fn=lambda: date(2026, 8, 25),
        ),
        provider_name="fixture",
        variable_store=VariableSnapshotStore(DerivedFrameCache(tmp_path / "derived")),
        variable_registry=variable_registry or baseline_variable_registry(),
        strategy_registry=strategy_registry or _baseline_registry(),
        derived_cache_enabled=derived_cache_enabled,
        build_identity={"git_commit": "fixture-commit"},
    )


def _baseline_registry() -> StrategyRegistry:
    registry = StrategyRegistry()
    registry.register(baseline_strategy_definition())
    return registry


def _request(*, with_context: bool = False, confirm_degraded: bool = False):
    request = BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000" if with_context else "close.cross_below:vwap",
        regime=("day_sma20_slope5.lt:999,relative_return20.lt:999" if with_context else None),
        benchmark="SOXX" if with_context else None,
        sentiment=with_context,
        sentiment_sector_benchmark="SOXX" if with_context else None,
        sentiment_market_benchmark="QQQ" if with_context else None,
        stop_pct=10.0,
        target_pct=10.0,
        max_hold_minutes=1,
        slippage_bps=0.0,
    )
    return replace(legacy_request_to_strategy_run(request), confirm_degraded=confirm_degraded)


def _run(request, dependencies: OrchestratorDependencies):
    return asyncio.run(execute_strategy_run(request, dependencies))


def test_baseline_run_resolves_exact_strategy_and_records_tiered_dependency_trace(
    tmp_path: Path,
):
    # Break caught: the compatibility baseline could bypass its versioned strategy or lose B-to-A lineage.
    result = _run(_request(), _dependencies(tmp_path, FixtureProvider()))

    assert result.resolved_strategy.strategy_id == "bktstr.bearish-regime-scalp"
    assert result.resolved_strategy.strategy_version == "1.0.0"
    assert result.resolved_strategy.values["entry_rules"] == "close.cross_below:vwap"
    assert result.degraded is False
    assert result.canonical is True
    assert result.provenance["stages"][:4] == (
        "strategy_resolved",
        "variable_graph_validated",
        "tier_a_acquired",
        "tier_b_calculated",
    )

    trace = {item["id"]: item for item in result.provenance["dependency_trace"]}
    assert trace["market.subject.close"]["tier"] == "A"
    assert trace["technical.vwap"]["tier"] == "B"
    assert trace["technical.vwap"]["dependencies"] == (
        "market.subject.high",
        "market.subject.low",
        "market.subject.close",
        "market.subject.volume",
    )
    assert result.variables["technical.vwap"].tier is DataTier.B
    assert result.variables["technical.vwap"].series.index.equals(intraday_fixture().index)


def test_context_variables_attached_from_strictly_prior_day_snapshots(tmp_path: Path):
    # Break caught: regime or sentiment could leak same-day daily data into an intraday signal.
    result = _run(_request(with_context=True), _dependencies(tmp_path, FixtureProvider()))

    regime_subject = _daily_bars(
        "NVDA", date(2026, 8, 17) - timedelta(days=120), date(2026, 8, 17)
    )
    regime_benchmark = _daily_bars(
        "SOXX", date(2026, 8, 17) - timedelta(days=120), date(2026, 8, 17)
    )
    expected_regime = build_daily_regime(regime_subject, regime_benchmark)
    sentiment_subject = _daily_bars(
        "NVDA", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    sentiment_sector = _daily_bars(
        "SOXX", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    sentiment_market = _daily_bars(
        "QQQ", date(2026, 8, 17) - timedelta(days=460), date(2026, 8, 17)
    )
    expected_sentiment = build_daily_sentiment(
        sentiment_subject, sentiment_sector, sentiment_market
    )

    assert result.variables["regime.day_close"].series.iloc[0] == pytest.approx(
        expected_regime.loc[pd.Timestamp("2026-08-14"), "day_close"]
    )
    assert result.variables["sentiment.direction"].series.iloc[0] == pytest.approx(
        expected_sentiment.loc[pd.Timestamp("2026-08-14"), "sentiment_direction"]
    )
    assert result.provenance["attachments"]["regime"]["availability"] == "prior_day"
    assert result.provenance["attachments"]["sentiment"]["availability"] == "prior_day"


def test_missing_primary_signal_data_has_deterministic_nonforceable_diagnostic(
    tmp_path: Path,
):
    # Break caught: an absent primary signal could be silently backfilled or forced into a canonical run.
    dependencies = _dependencies(tmp_path, FixtureProvider(empty_intraday=True))

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), dependencies)

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "missing_coverage"
    assert diagnostic.variable_id == "market.subject.close"
    assert diagnostic.variable is not None and diagnostic.variable.tier is DataTier.A
    assert diagnostic.affected_coverage == {
        "available_end": None,
        "available_start": None,
        "required_end": "2026-08-17",
        "required_start": "2026-08-17",
    }
    assert diagnostic.affected_rules == ("close.cross_below:vwap",)
    assert diagnostic.suggestion_method == "no_safe_suggestion"
    assert diagnostic.applied is False
    assert diagnostic.forceable is False


def _optional_filter_strategy(*, forceable: bool, optional: bool) -> tuple[StrategyRegistry, object]:
    definition = baseline_strategy_definition()
    input_ref = VariableRef(
        "strategy.bktstr.bearish-regime-scalp.filter.context-input",
        "1.0.0",
        DataTier.C,
    )
    evidence_filter = StrategyFilterDefinition(
        id="bktstr.context-confirmation",
        version="1.0.0",
        output=VariableRef(
            "strategy.bktstr.bearish-regime-scalp.filter.context-confirmation",
            "1.0.0",
            DataTier.C,
        ),
        inputs=(input_ref,),
        role=FilterRole.ANNOTATE,
        rule=None,
        tier=DataTier.C,
        forceable=forceable,
        optional=optional,
    )
    registry = StrategyRegistry()
    registry.register(
        replace(
            definition,
            filters=(evidence_filter,),
            evidence_tier_opt_ins=(DataTier.C,),
        )
    )
    return registry, input_ref


def _registry_with_unavailable_filter_input(input_ref: VariableRef):
    registry = baseline_variable_registry()
    registry.register(
        ResearchVariableDefinition.source(
            id=input_ref.id,
            version=input_ref.version,
            tier=input_ref.tier,
            column="context_input",
            value_dtype="float64",
            frequency="1m",
        )
    )
    return registry


def test_force_omits_only_declared_optional_forceable_filter_after_confirmation(
    tmp_path: Path,
):
    # Break caught: a lower-trust unavailable filter could be silently ignored without an explicit degraded decision.
    strategies, input_ref = _optional_filter_strategy(forceable=True, optional=True)
    dependencies = _dependencies(
        tmp_path,
        FixtureProvider(),
        strategy_registry=strategies,
        variable_registry=_registry_with_unavailable_filter_input(input_ref),
    )

    with pytest.raises(StrategyRunError) as unconfirmed:
        _run(_request(), dependencies)
    assert unconfirmed.value.diagnostics[0].forceable is True

    forced = _run(_request(confirm_degraded=True), dependencies)
    assert forced.degraded is True
    assert forced.canonical is False
    assert forced.diagnostics[0].applied is False
    assert forced.diagnostics[0].forceable is True
    decision = forced.provenance["filters"][0]
    assert {
        "id": "bktstr.context-confirmation",
        "role": "annotate",
        "status": "not_evaluated",
        "tier": "C",
        "version": "1.0.0",
    }.items() <= decision.items()
    assert decision["inputs"] == (
        "strategy.bktstr.bearish-regime-scalp.filter.context-input",
    )


def test_confirmation_cannot_omit_a_required_filter(tmp_path: Path):
    # Break caught: confirmation could make a required filter forceable despite its immutable definition.
    strategies, input_ref = _optional_filter_strategy(forceable=False, optional=True)
    dependencies = _dependencies(
        tmp_path,
        FixtureProvider(),
        strategy_registry=strategies,
        variable_registry=_registry_with_unavailable_filter_input(input_ref),
    )

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), dependencies)

    assert raised.value.diagnostics[0].forceable is False
    assert raised.value.diagnostics[0].variable_id.endswith("context-confirmation")


def test_immutable_snapshot_corruption_is_nonforceable_and_sanitized(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: corruption could be treated as an optional data gap or expose cache implementation details.
    secret = "corrupt-provider-token"

    def corrupt_snapshot(*args, **kwargs):
        raise VariableContractError(
            f"immutable snapshot corruption near {secret}",
            code="invalid_snapshot_digest",
        )

    monkeypatch.setattr(VariableSnapshotStore, "resolve", corrupt_snapshot)
    with pytest.raises(StrategyRunError) as raised:
        _run(_request(confirm_degraded=True), _dependencies(tmp_path, FixtureProvider(secret=secret)))

    diagnostic = raised.value.diagnostics[0]
    assert diagnostic.code == "immutable_snapshot_corruption"
    assert diagnostic.forceable is False
    assert secret not in str(raised.value)
    assert secret not in repr(diagnostic)


def test_provider_secrets_never_appear_in_diagnostics_or_provenance(tmp_path: Path):
    # Break caught: provider exceptions or object metadata could leak credentials into durable run evidence.
    secret = "provider-secret-never-publish"
    successful = _run(_request(), _dependencies(tmp_path / "success", FixtureProvider(secret=secret)))
    assert secret not in repr(successful.provenance)

    with pytest.raises(StrategyRunError) as raised:
        _run(_request(), _dependencies(tmp_path / "failure", ExplodingProvider(secret=secret)))

    assert secret not in str(raised.value)
    assert all(secret not in repr(item) for item in raised.value.diagnostics)
