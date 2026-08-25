from __future__ import annotations

from dataclasses import replace
from datetime import date
from types import MappingProxyType

import pytest

import bktstr.services.backtest as backtest_service
from bktstr.services.backtest import (
    BacktestConfiguration,
    BacktestInput,
    BacktestMetrics,
    BacktestResearchResult,
    CompareInput,
    ParameterSweepInput,
    RegimeComparisonInput,
    RegimeLabelInput,
    ResearchProvenance,
    compare_experiments,
    run_parameter_sweep,
    run_regime_comparison,
)
from bktstr.services.experiments import ExperimentStatus, ExperimentStore


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


def _research_result(value: BacktestInput) -> BacktestResearchResult:
    stop_pct = float(value.parameters.get("stop_pct", 1.0))
    strategy = MappingProxyType(
        {
            "id": value.strategy_id,
            "version": value.strategy_version,
            "schema_version": "1.0.0",
            "parameters": {"stop_pct": stop_pct},
        }
    )
    metrics = BacktestMetrics(
        total_pnl=stop_pct * 10.0,
        total_return=stop_pct,
        ev_per_trade=stop_pct,
        win_rate=50.0,
        profit_factor=stop_pct + 1.0,
        max_drawdown=-stop_pct,
        sharpe=stop_pct / 2.0,
        trade_count=2,
    )
    provenance = ResearchProvenance(
        strategy=strategy,
        market_data=MappingProxyType(
            {
                "source": "fixture",
                "requested_source": "auto",
                "version": "fixture-v1",
                "coverage": {
                    "requested_start": value.start.isoformat(),
                    "requested_end": value.end.isoformat(),
                    "bars": 2,
                },
            }
        ),
        execution_model=MappingProxyType(
            {"id": "bktstr.next-bar-open", "version": "1.0.0", "slippage_bps": 2.0}
        ),
        software=MappingProxyType({"bktstr_version": "0.5.0"}),
    )
    return BacktestResearchResult(
        metrics=metrics,
        trades=(),
        configuration=BacktestConfiguration(
            strategy=strategy,
            market=MappingProxyType(
                {
                    "symbol": value.symbol,
                    "start": value.start.isoformat(),
                    "end": value.end.isoformat(),
                    "timeframe": value.timeframe,
                    "source": value.source,
                }
            ),
            regime=MappingProxyType(
                {
                    "enabled": bool(value.regime and value.regime.enabled),
                    "rules": value.regime.rules if value.regime else None,
                }
            ),
            execution=MappingProxyType(
                {
                    "mode": value.execution,
                    "model_id": "bktstr.next-bar-open",
                    "model_version": "1.0.0",
                    "slippage_bps": 2.0,
                    "position_size": 1000.0,
                    "starting_capital": 10000.0,
                }
            ),
        ),
        provenance=provenance,
    )


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
        return _research_result(value)

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
            "provenance": {"strategy": {"id": "bktstr.bearish-regime-scalp"}},
        },
        {"strategy": {"id": "bktstr.bearish-regime-scalp"}},
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

    with pytest.raises(ValueError, match="completed backtest"):
        compare_experiments((queued.experiment_id, completed), store=store)


def test_regime_comparison_allows_overlap_by_default_but_can_require_disjoint_periods():
    # Break caught: the service could silently reject intentional overlap or ignore disjoint mode.
    labels = (
        RegimeLabelInput("first", date(2026, 1, 1), date(2026, 1, 10)),
        RegimeLabelInput("second", date(2026, 1, 10), date(2026, 1, 20)),
    )
    assert RegimeComparisonInput(base=BASE, labels=labels).labels == labels
    with pytest.raises(ValueError, match="overlap"):
        RegimeComparisonInput(base=BASE, labels=labels, disjoint_periods=True)


def test_regime_comparison_persists_every_caller_label_and_child(
    monkeypatch, tmp_path
):
    # Break caught: labels or exact period/rule inputs could disappear from provenance.
    async def deterministic(value: BacktestInput) -> BacktestResearchResult:
        return _research_result(value)

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
