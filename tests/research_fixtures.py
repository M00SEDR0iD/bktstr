from __future__ import annotations

from types import MappingProxyType

from bktstr.services.backtest import (
    BacktestConfiguration,
    BacktestInput,
    BacktestMetrics,
    BacktestResearchResult,
    ResearchProvenance,
)


def deterministic_research_result(value: BacktestInput) -> BacktestResearchResult:
    """Return a complete, deterministic result without market-data execution."""
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
                "snapshot_id": "sha256:fixture",
                "coverage": {
                    "requested_start": value.start.isoformat(),
                    "requested_end": value.end.isoformat(),
                    "available_start": value.start.isoformat(),
                    "available_end": value.end.isoformat(),
                    "observations": 2,
                    "bars": 2,
                },
                "cache": {"hit_days": 0, "miss_days": 1, "fetched_ranges": 1},
            }
        ),
        execution_model=MappingProxyType(
            {"id": "bktstr.next-bar-open", "version": "1.0.0", "slippage_bps": 2.0}
        ),
        software=MappingProxyType(
            {
                "bktstr_version": "0.6.0",
                "git_commit": "fixture",
                "git_branch": None,
                "git_repo": None,
                "deployment_id": None,
                "build_time": None,
            }
        ),
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
