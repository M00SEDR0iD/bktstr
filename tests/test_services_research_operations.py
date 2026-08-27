from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
from enum import StrEnum
from types import MappingProxyType

import pytest

import bktstr.services.backtest as backtest_service
from bktstr.services.backtest import (
    BacktestInput,
    BacktestMetrics,
    BacktestResearchResult,
    CompareInput,
    NamedVariantInput,
    ParameterSweepInput,
    RegimeComparisonInput,
    RegimeLabelInput,
    compare_experiments,
    run_parameter_sweep,
    run_regime_comparison,
    to_json_value,
)
from bktstr.services.experiments import (
    ExperimentOperationError,
    ExperimentStatus,
    ExperimentStore,
)
from bktstr.services.validation import SemanticValidationError
from research_fixtures import deterministic_research_result


BASE = BacktestInput(
    strategy_id="bktstr.bearish-regime-scalp",
    strategy_version="1.0.0",
    symbol="NVDA",
    start=date(2026, 8, 17),
    end=date(2026, 8, 17),
    timeframe="1m",
    side="short",
    entry="close.cross_below:vwap",
)


# Kept as a test-module compatibility alias for adjacent operation-route tests.
_research_result = deterministic_research_result


class _FixtureState(StrEnum):
    READY = "ready"


def test_to_json_value_recursively_thaws_domain_values():
    # Break caught: immutable service results could reach JSON persistence unchanged.
    value = MappingProxyType(
        {
            "candidate": MappingProxyType(
                {"metrics": BacktestMetrics(1, 2, 3, 4, 5, 6, 7, 8)}
            ),
            "states": (_FixtureState.READY,),
            "at": datetime(2026, 8, 26, tzinfo=timezone.utc),
        }
    )

    normalized = to_json_value(value)

    assert type(normalized) is dict
    assert type(normalized["candidate"]) is dict
    assert normalized["candidate"]["metrics"]["trade_count"] == 8
    assert normalized["states"] == ["ready"]
    assert normalized["at"] == "2026-08-26T00:00:00+00:00"


def test_parameter_sweep_rejects_non_overridable_grid_key():
    # Break caught: a sweep could replace protected execution semantics.
    with pytest.raises(ValueError, match="overridable"):
        ParameterSweepInput(
            base=BASE,
            grid={"execution_model": ("other",)},
            objective="profit_factor",
        )


@pytest.mark.parametrize(
    ("grid", "message"),
    [
        ({}, "cannot be empty"),
        ({"stop_pct": (1.0, 1.0)}, "duplicate canonical"),
        ({"stop_pct": (1.0,), "target_pct": ()}, "cannot be empty"),
    ],
)
def test_parameter_sweep_rejects_ambiguous_grids(grid, message):
    # Break caught: an empty or duplicate grid could create misleading duplicate research.
    with pytest.raises(ValueError, match=message):
        ParameterSweepInput(base=BASE, grid=grid, objective="profit_factor")


def test_parameter_sweep_honors_configured_bound(monkeypatch):
    # Break caught: a grid could exhaust the in-process Railway worker.
    monkeypatch.setenv("BKTSTR_MAX_SWEEP_VARIANTS", "3")
    with pytest.raises(ValueError, match="at most 3"):
        ParameterSweepInput(
            base=BASE,
            grid={"stop_pct": (1.0, 2.0), "target_pct": (2.0, 3.0)},
            objective="profit_factor",
        )


def test_parameter_sweep_is_deterministic_and_persists_linked_children(
    monkeypatch, tmp_path
):
    # Break caught: grid ordering or child linkage could vary between reproductions.
    async def deterministic(value: BacktestInput) -> BacktestResearchResult:
        return deterministic_research_result(value)

    monkeypatch.setattr(backtest_service, "run_backtest", deterministic)
    store = ExperimentStore(tmp_path)
    parent, _ = store.create_experiment("parameter_sweep", {"grid": {}}, "async")
    result = run_parameter_sweep(
        ParameterSweepInput(
            base=BASE,
            grid={"target_pct": (4.0, 3.0), "stop_pct": (2.0, 1.0)},
            objective="profit_factor",
        ),
        store=store,
        parent_experiment_id=parent.experiment_id,
    )

    assert [dict(item.parameters) for item in result.variants] == [
        {"stop_pct": 1.0, "target_pct": 3.0},
        {"stop_pct": 1.0, "target_pct": 4.0},
        {"stop_pct": 2.0, "target_pct": 3.0},
        {"stop_pct": 2.0, "target_pct": 4.0},
    ]
    assert [item.score for item in result.variants] == [2.0, 2.0, 3.0, 3.0]
    assert all(
        item.provenance.strategy["id"] == "bktstr.bearish-regime-scalp"
        for item in result.variants
    )
    for item in result.variants:
        child = store.load_experiment(item.experiment_id)
        assert child.status is ExperimentStatus.COMPLETED
        assert child.parent_experiment_id == parent.experiment_id


def _completed_backtest(
    store: ExperimentStore, *, stop_pct: float, profit_factor: float
) -> str:
    request = {
        "strategy": {
            "id": "bktstr.bearish-regime-scalp",
            "version": "1.0.0",
            "parameters": {"stop_pct": stop_pct},
        },
        "market": {
            "symbol": "NVDA",
            "start": "2026-08-17",
            "end": "2026-08-17",
            "timeframe": "1m",
            "source": "auto",
        },
        "side": "short",
        "entry": "close.cross_below:vwap",
        "regime": None,
        "execution": "sync",
        "include_trades": True,
    }
    provenance = {
        "strategy": {
            "id": "bktstr.bearish-regime-scalp",
            "version": "1.0.0",
            "schema_version": "1.0.0",
            "parameters": {"stop_pct": stop_pct},
        },
        "market_data": {
            "source": "fixture",
            "requested_source": "auto",
            "version": "fixture-v1",
            "snapshot_id": "fixture-snapshot",
            "coverage": {
                "requested_start": "2026-08-17",
                "requested_end": "2026-08-17",
                "available_start": "2026-08-17",
                "available_end": "2026-08-17",
                "observations": 2,
                "bars": 2,
            },
            "cache": {"hit_days": 1, "miss_days": 0, "fetched_ranges": 0},
        },
        "execution_model": {
            "id": "bktstr.next-bar-open",
            "version": "1.0.0",
            "slippage_bps": 2.0,
        },
        "software": {"bktstr_version": "0.5.0"},
    }
    record, _ = store.create_and_claim_experiment("backtest", request, "sync")
    completed = store.complete(
        record.experiment_id,
        {
            "metrics": {
                "total_pnl": 10.0,
                "total_return": 1.0,
                "ev_per_trade": 1.0,
                "win_rate": 50.0,
                "profit_factor": profit_factor,
                "max_drawdown": -1.0,
                "sharpe": 0.5,
                "trade_count": 2,
            },
            "trades": [],
            "configuration": {},
            "provenance": provenance,
        },
        provenance,
    )
    return completed.experiment_id


def test_compare_records_changed_inputs_and_metric_deltas(tmp_path):
    # Break caught: comparison could hide the exact changed input or imply a winner.
    store = ExperimentStore(tmp_path)
    first = _completed_backtest(store, stop_pct=1.0, profit_factor=1.5)
    second = _completed_backtest(store, stop_pct=2.0, profit_factor=2.0)

    result = compare_experiments((first, second), store=store)

    assert result.items[0].changed_inputs == ("strategy.parameters.stop_pct",)
    assert result.metric_deltas["profit_factor"][second] == 0.5
    assert result.candidates[0].provenance["strategy"]["id"] == "bktstr.bearish-regime-scalp"
    assert not hasattr(result, "winner")
    assert not hasattr(result.items[0], "causality")


def test_compare_requires_completed_backtest_experiments(tmp_path):
    # Break caught: comparisons could align incomplete or unrelated results as if valid.
    store = ExperimentStore(tmp_path)
    queued, _ = store.create_experiment("backtest", {"symbol": "NVDA"}, "async")
    completed = _completed_backtest(store, stop_pct=1.0, profit_factor=1.5)

    with pytest.raises(ExperimentOperationError) as raised:
        compare_experiments((queued.experiment_id, completed), store=store)

    assert raised.value.code == "invalid_request"
    assert str(raised.value) == (
        f"Comparison candidate 0 '{queued.experiment_id}' has status 'queued'; "
        "expected 'completed'."
    )
    assert raised.value.details == {
        "fields": ["candidates.0"],
        "candidate_index": 0,
        "candidate_id": queued.experiment_id,
        "reason": "not_completed",
    }


def test_compare_input_reports_the_invalid_experiment_candidate_index():
    with pytest.raises(SemanticValidationError) as raised:
        CompareInput(("exp_valid", "not-an-experiment"))

    assert raised.value.fields == ("candidates.1",)


def test_named_variant_reports_structured_local_fields():
    with pytest.raises(SemanticValidationError) as raised:
        NamedVariantInput("", BASE)

    assert raised.value.fields == ("name",)


def test_regime_comparison_allows_overlap_by_default_but_can_require_disjoint_periods():
    # Break caught: the service could silently reject intentional overlap or ignore disjoint mode.
    labels = (
        RegimeLabelInput("first", date(2026, 1, 1), date(2026, 1, 10)),
        RegimeLabelInput("second", date(2026, 1, 10), date(2026, 1, 20)),
    )
    assert RegimeComparisonInput(base=BASE, labels=labels).labels == labels
    with pytest.raises(ValueError, match="overlap"):
        RegimeComparisonInput(base=BASE, labels=labels, disjoint_periods=True)


@pytest.mark.parametrize(
    ("labels", "fields"),
    [
        (
            (
                RegimeLabelInput(
                    "bad rule",
                    date(2026, 1, 1),
                    date(2026, 1, 2),
                    "day_close.cross_below:day_sma20",
                ),
                RegimeLabelInput("valid", date(2026, 2, 1), date(2026, 2, 2)),
            ),
            ("labels.0.rule",),
        ),
        (
            (
                RegimeLabelInput("same", date(2026, 1, 1), date(2026, 1, 2)),
                RegimeLabelInput("same", date(2026, 2, 1), date(2026, 2, 2)),
            ),
            ("labels.0.label", "labels.1.label"),
        ),
    ],
)
def test_regime_comparison_reports_indexed_label_fields(labels, fields):
    with pytest.raises(SemanticValidationError) as raised:
        RegimeComparisonInput(base=BASE, labels=labels)

    assert raised.value.fields == fields


@pytest.mark.parametrize(
    ("kwargs", "fields"),
    [
        (
            {"label": "", "start": date(2026, 1, 1), "end": date(2026, 1, 2)},
            ("label",),
        ),
        (
            {"label": "dates", "start": date(2026, 1, 2), "end": date(2026, 1, 1)},
            ("start", "end"),
        ),
        (
            {
                "label": "rule",
                "start": date(2026, 1, 1),
                "end": date(2026, 1, 2),
                "rule": "",
            },
            ("rule",),
        ),
    ],
)
def test_regime_label_reports_structured_local_fields(kwargs, fields):
    with pytest.raises(SemanticValidationError) as raised:
        RegimeLabelInput(**kwargs)

    assert raised.value.fields == fields


def test_regime_comparison_persists_every_caller_label_and_child(
    monkeypatch, tmp_path
):
    # Break caught: labels or exact period/rule inputs could disappear from provenance.
    async def deterministic(value: BacktestInput) -> BacktestResearchResult:
        return deterministic_research_result(value)

    monkeypatch.setattr(backtest_service, "run_backtest", deterministic)
    store = ExperimentStore(tmp_path)
    parent, _ = store.create_experiment("regime_comparison", {"labels": []}, "async")
    result = run_regime_comparison(
        RegimeComparisonInput(
            base=replace(BASE, regime=None),
            labels=(
                RegimeLabelInput("2025", date(2025, 1, 1), date(2025, 1, 31)),
                RegimeLabelInput("2026", date(2026, 1, 1), date(2026, 1, 31)),
            ),
        ),
        store=store,
        parent_experiment_id=parent.experiment_id,
    )

    assert [item.label for item in result.items] == ["2025", "2026"]
    assert list(result.comparison_matrix["profit_factor"]) == ["2025", "2026"]
    assert result.provenance["labels"] == [
        {"label": "2025", "start": "2025-01-01", "end": "2025-01-31", "rule": None},
        {"label": "2026", "start": "2026-01-01", "end": "2026-01-31", "rule": None},
    ]
    assert all(
        store.load_experiment(item.experiment_id).parent_experiment_id
        == parent.experiment_id
        for item in result.items
    )
