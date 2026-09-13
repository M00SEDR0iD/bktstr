"""Shared provider selection and execution wiring for research and legacy clients."""

from datetime import date
import os

import httpx

from bktstr_cache.derived import DerivedFrameCache

from .cache import BarCache, CachedProvider
from .engine import validate_entry_window
from .orchestrator import (
    OrchestratorDependencies, StrategyRunError, StrategyRunResult, execute_strategy_run,
)
from .providers import MassiveProvider, YahooProvider, can_use_yahoo_intraday
from .strategies import StrategyRunRequest, baseline_strategy_registry
from .variable_store import VariableSnapshotStore


def select_provider(
    start: date, end: date, timeframe: str, *,
    requires_daily_context: bool = False, today: date | None = None,
) -> str:
    if os.getenv("MASSIVE_API_KEY", ""):
        return "massive"
    if requires_daily_context:
        raise RuntimeError("MASSIVE_API_KEY is required for regime or sentiment backtests")
    if can_use_yahoo_intraday(start, end, timeframe, today=today):
        return "yahoo"
    raise RuntimeError("MASSIVE_API_KEY is required for historical intraday ranges older than the Yahoo fallback window")


def cached_provider(
    start: date, end: date, timeframe: str, *, requires_daily_context: bool = False,
) -> CachedProvider:
    name = select_provider(start, end, timeframe, requires_daily_context=requires_daily_context)
    upstream = MassiveProvider(os.environ["MASSIVE_API_KEY"]) if name == "massive" else YahooProvider()
    return CachedProvider(upstream, BarCache(), provider_name=name)


async def run_strategy(request: StrategyRunRequest) -> StrategyRunResult:
    # Formula definitions still import the historical version constants from
    # service.py; defer their import until application wiring is complete.
    from .measurements import baseline_variable_registry

    registry = baseline_strategy_registry()
    resolved = registry.require(request.strategy_id, request.strategy_version).resolve(request.overrides)
    validate_entry_window(resolved.values["entry_start_time"], resolved.values["entry_end_time"])
    provider = cached_provider(
        request.start, request.end, request.timeframe,
        requires_daily_context=bool(resolved.values["regime_rules"] or resolved.values["sentiment"]),
    )
    enabled = os.getenv("BKTSTR_DERIVED_CACHE_ENABLED", "true").strip().lower()
    try:
        return await execute_strategy_run(
            request,
            OrchestratorDependencies(
                provider=provider,
                provider_name=provider.provider_name,
                variable_store=VariableSnapshotStore(DerivedFrameCache()),
                variable_registry=baseline_variable_registry(),
                strategy_registry=registry,
                derived_cache_enabled=enabled not in {"0", "false", "no", "off"},
            ),
        )
    except StrategyRunError as error:
        # Both API and legacy clients classify provider HTTP failures at their
        # outer boundary. Keep the original exception without exposing it in
        # the domain's serializable diagnostics.
        if isinstance(error.provider_cause, httpx.HTTPStatusError):
            raise error.provider_cause from None
        raise
