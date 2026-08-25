from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

import bktstr.measurements as measurements
from bktstr.engine import prepare_bars_for_backtest
from bktstr.measurements import (
    attach_regime_variables,
    attach_sentiment_variables,
    baseline_variable_registry,
    compute_intraday_variables,
    compute_regime_variables,
    compute_sentiment_variables,
    intraday_definitions,
    regime_definitions,
    sentiment_definitions,
    source_definitions,
)
from bktstr.provenance import SOURCE_REGISTRY, capability_provenance
from bktstr.regime import attach_regime_to_intraday, build_daily_regime
from bktstr.sentiment import attach_sentiment_to_intraday, build_daily_sentiment
from bktstr.service import (
    INTRADAY_FEATURE_FORMULA_VERSION,
    REGIME_FORMULA_VERSION,
    SENTIMENT_FORMULA_VERSION,
)
from bktstr.variable_store import VariableSnapshotStore
from bktstr.variables import DataTier, VariableKind
from bktstr_cache.derived import DerivedFrameCache
from tests.v05_fixtures import daily_fixture, intraday_fixture


def _store(path: Path) -> VariableSnapshotStore:
    return VariableSnapshotStore(DerivedFrameCache(path))


def _daily_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    start = date(2025, 1, 2)
    end = date(2026, 8, 18)
    return (
        daily_fixture(start, end, 100.0, 0.20),
        daily_fixture(start, end, 100.0, 0.10),
        daily_fixture(start, end, 100.0, 0.08),
    )


def test_current_measurements_are_registered_tier_b():
    # Break caught: derived arrays could be mislabeled as raw Tier A sources.
    registry = baseline_variable_registry()
    for variable_id in [
        "technical.vwap",
        "technical.rsi14",
        "technical.volume_ratio20",
        "regime.relative_return20",
        "sentiment.direction",
        "sentiment.fragility",
    ]:
        definition = registry.require(variable_id)
        assert definition.tier is DataTier.B
        assert definition.kind is VariableKind.MEASUREMENT


def test_all_current_outputs_are_tier_b_and_depend_only_on_tier_a():
    # Break caught: a newly exposed legacy column could escape governance or depend on C/D evidence.
    subject, sector, market = _daily_inputs()
    expected_columns = {
        *prepare_bars_for_backtest(intraday_fixture()).columns[-3:],
        *build_daily_regime(subject, sector).columns,
        *build_daily_sentiment(subject, sector, market).columns,
    }
    definitions = (*intraday_definitions(), *regime_definitions(), *sentiment_definitions())

    assert {item.column for item in definitions} == expected_columns
    assert all(item.tier is DataTier.B for item in definitions)
    assert all(dependency.tier is DataTier.A for item in definitions for dependency in item.inputs)
    assert all(item.tier is DataTier.A for item in source_definitions("subject"))


def test_intraday_adapter_preserves_existing_formula(tmp_path: Path):
    # Break caught: the adapter could alter filtering, timezone conversion, or indicator formulas.
    expected = prepare_bars_for_backtest(intraday_fixture(), regular_hours_only=True)
    actual = compute_intraday_variables(
        store=_store(tmp_path),
        raw_bars=intraday_fixture(),
        symbol="NVDA",
        timeframe="1m",
        regular_hours_only=True,
    ).legacy_frame

    pd.testing.assert_frame_equal(actual, expected)


def test_intraday_adapter_preserves_additional_source_columns(tmp_path: Path):
    # Break caught: governed persistence could reject a valid delegated legacy frame.
    raw_bars = intraday_fixture().assign(source_sequence=[10, 11, 12])
    expected = prepare_bars_for_backtest(raw_bars, regular_hours_only=True)

    actual = compute_intraday_variables(
        store=_store(tmp_path),
        raw_bars=raw_bars,
        symbol="NVDA",
        timeframe="1m",
        regular_hours_only=True,
    ).legacy_frame

    pd.testing.assert_frame_equal(actual, expected)


def test_intraday_adapter_does_not_recompute_formulas_on_warm_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: eagerly preparing the compatibility frame could recompute
    # VWAP, RSI, and volume ratio even when every governed column is cached.
    raw_bars = intraday_fixture().assign(source_sequence=[10, 11, 12])
    expected = prepare_bars_for_backtest(raw_bars, regular_hours_only=True)
    actual_prepare = measurements.prepare_bars_for_backtest
    call_count = 0

    def count_prepare(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return actual_prepare(*args, **kwargs)

    monkeypatch.setattr(measurements, "prepare_bars_for_backtest", count_prepare)
    store = _store(tmp_path)

    cold = compute_intraday_variables(
        store=store,
        raw_bars=raw_bars,
        symbol="NVDA",
        timeframe="1m",
        regular_hours_only=True,
    )
    warm = compute_intraday_variables(
        store=store,
        raw_bars=raw_bars,
        symbol="NVDA",
        timeframe="1m",
        regular_hours_only=True,
    )

    assert cold.status.hit is False
    assert warm.status.hit is True
    assert call_count == 1
    pd.testing.assert_frame_equal(cold.legacy_frame, expected)
    pd.testing.assert_frame_equal(warm.legacy_frame, expected)


def test_regime_adapter_preserves_existing_formula(tmp_path: Path):
    # Break caught: the adapter could reimplement or omit a daily regime output.
    subject, benchmark, _ = _daily_inputs()
    expected = build_daily_regime(subject, benchmark)
    actual = compute_regime_variables(
        store=_store(tmp_path),
        subject_daily=subject,
        benchmark_daily=benchmark,
        subject="NVDA",
        benchmark="SOXX",
    ).legacy_frame

    pd.testing.assert_frame_equal(actual, expected)


def test_sentiment_adapter_preserves_existing_formula(tmp_path: Path):
    # Break caught: the adapter could drift from the established sentiment and fragility formulas.
    subject, sector, market = _daily_inputs()
    expected = build_daily_sentiment(subject, sector, market)
    actual = compute_sentiment_variables(
        store=_store(tmp_path),
        subject_daily=subject,
        sector_daily=sector,
        market_daily=market,
        subject="NVDA",
        sector_benchmark="SOXX",
        market_benchmark="QQQ",
    ).legacy_frame

    pd.testing.assert_frame_equal(actual, expected)


@pytest.mark.parametrize("source_id", ["options", "news", "social"])
def test_sentiment_adapter_rejects_unavailable_source_claims(
    tmp_path: Path, source_id: str
):
    # Break caught: Tier B price measurements could claim unavailable source lineage.
    subject, sector, market = _daily_inputs()

    with pytest.raises(ValueError, match=f"sentiment source '{source_id}' is not available"):
        compute_sentiment_variables(
            store=_store(tmp_path),
            subject_daily=subject,
            sector_daily=sector,
            market_daily=market,
            subject="NVDA",
            sector_benchmark="SOXX",
            market_benchmark="QQQ",
            sources=(source_id,),
        )


@pytest.mark.parametrize("source_id", ["news", "social"])
def test_sentiment_adapter_rejects_lower_tier_source_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, source_id: str
):
    # Break caught: a newly available Tier C/D source could contaminate Tier B provenance.
    subject, sector, market = _daily_inputs()
    monkeypatch.setitem(SOURCE_REGISTRY[source_id], "available", True)

    with pytest.raises(
        ValueError,
        match=f"sentiment source '{source_id}' tier [CD] is not allowed by profile 'clean'",
    ):
        compute_sentiment_variables(
            store=_store(tmp_path),
            subject_daily=subject,
            sector_daily=sector,
            market_daily=market,
            subject="NVDA",
            sector_benchmark="SOXX",
            market_benchmark="QQQ",
            sources=(source_id,),
        )


def test_attachment_adapters_preserve_strictly_prior_day_timing(tmp_path: Path):
    # Break caught: same-day daily context could leak future closes into intraday evaluation.
    subject, sector, market = _daily_inputs()
    intraday = intraday_fixture().set_axis(
        pd.DatetimeIndex(
            ["2026-08-18 09:30", "2026-08-18 09:31", "2026-08-18 09:32"],
            tz="America/New_York",
        )
    )
    daily_regime = build_daily_regime(subject, sector)
    daily_sentiment = build_daily_sentiment(subject, sector, market)

    expected_regime = attach_regime_to_intraday(intraday, daily_regime)
    actual_regime = attach_regime_variables(
        store=_store(tmp_path / "regime"),
        intraday=intraday,
        daily_regime=daily_regime,
        symbol="NVDA",
        timeframe="1m",
    ).legacy_frame
    expected_sentiment = attach_sentiment_to_intraday(intraday, daily_sentiment)
    actual_sentiment = attach_sentiment_variables(
        store=_store(tmp_path / "sentiment"),
        intraday=intraday,
        daily_sentiment=daily_sentiment,
        symbol="NVDA",
        timeframe="1m",
    ).legacy_frame

    pd.testing.assert_frame_equal(actual_regime, expected_regime)
    pd.testing.assert_frame_equal(actual_sentiment, expected_sentiment)
    assert actual_regime.iloc[0]["day_close"] == daily_regime.loc[pd.Timestamp("2026-08-17")]["day_close"]
    assert actual_sentiment.iloc[0]["sentiment_direction"] == daily_sentiment.loc[pd.Timestamp("2026-08-17")]["sentiment_direction"]


def test_regime_attachment_does_not_recompute_formula_on_warm_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: a cached prior-day regime attachment could still rerun the
    # causal attachment formula before consulting the variable store.
    subject, sector, _ = _daily_inputs()
    intraday = intraday_fixture()
    daily_regime = build_daily_regime(subject, sector)
    expected = attach_regime_to_intraday(intraday, daily_regime)
    actual_attach = measurements.attach_regime_to_intraday
    call_count = 0

    def count_attach(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return actual_attach(*args, **kwargs)

    monkeypatch.setattr(measurements, "attach_regime_to_intraday", count_attach)
    store = _store(tmp_path)

    cold = attach_regime_variables(
        store=store,
        intraday=intraday,
        daily_regime=daily_regime,
        symbol="NVDA",
        timeframe="1m",
    )
    warm = attach_regime_variables(
        store=store,
        intraday=intraday,
        daily_regime=daily_regime,
        symbol="NVDA",
        timeframe="1m",
    )

    assert cold.status.hit is False
    assert warm.status.hit is True
    assert call_count == 1
    pd.testing.assert_frame_equal(cold.legacy_frame, expected)
    pd.testing.assert_frame_equal(warm.legacy_frame, expected)


def test_sentiment_attachment_does_not_recompute_formula_on_warm_hit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    # Break caught: a cached prior-day sentiment attachment could still rerun
    # the causal attachment formula before consulting the variable store.
    subject, sector, market = _daily_inputs()
    intraday = intraday_fixture()
    daily_sentiment = build_daily_sentiment(subject, sector, market)
    expected = attach_sentiment_to_intraday(intraday, daily_sentiment)
    actual_attach = measurements.attach_sentiment_to_intraday
    call_count = 0

    def count_attach(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return actual_attach(*args, **kwargs)

    monkeypatch.setattr(measurements, "attach_sentiment_to_intraday", count_attach)
    store = _store(tmp_path)

    cold = attach_sentiment_variables(
        store=store,
        intraday=intraday,
        daily_sentiment=daily_sentiment,
        symbol="NVDA",
        timeframe="1m",
    )
    warm = attach_sentiment_variables(
        store=store,
        intraday=intraday,
        daily_sentiment=daily_sentiment,
        symbol="NVDA",
        timeframe="1m",
    )

    assert cold.status.hit is False
    assert warm.status.hit is True
    assert call_count == 1
    pd.testing.assert_frame_equal(cold.legacy_frame, expected)
    pd.testing.assert_frame_equal(warm.legacy_frame, expected)


def test_definitions_reuse_existing_formula_versions():
    # Break caught: an adapter-only release could accidentally fork cache/formula identity.
    assert {item.formula_version for item in intraday_definitions()} == {
        INTRADAY_FEATURE_FORMULA_VERSION
    }
    assert {item.formula_version for item in regime_definitions()} == {
        REGIME_FORMULA_VERSION
    }
    assert {item.formula_version for item in sentiment_definitions()} == {
        SENTIMENT_FORMULA_VERSION
    }


def test_capability_provenance_separates_source_and_artifact_tiers():
    # Break caught: describing derived artifacts could overwrite the price source's Tier A identity.
    provenance = capability_provenance()

    assert provenance["sources"]["price"]["id"] == "price"
    assert provenance["sources"]["price"]["tier"] == "A"
    assert provenance["artifact_tiers"]["source_arrays"]["tier"] == "A"
    assert provenance["artifact_tiers"]["deterministic_measurements"]["tier"] == "B"


def test_shared_adapter_provenance_does_not_relabel_source_snapshots(tmp_path: Path):
    # Break caught: shared computation provenance could contradict a Tier A source definition.
    result = compute_intraday_variables(
        store=_store(tmp_path),
        raw_bars=intraday_fixture(),
        symbol="NVDA",
        timeframe="1m",
    )
    source = result.variables["market.subject.close"]

    assert source.tier is DataTier.A
    assert "artifact_tier" not in source.provenance
    assert source.provenance["source_tiers"] == {"price": "A"}
