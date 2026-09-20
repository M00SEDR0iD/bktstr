"""Strict local strategy documents compiled to the existing research contracts.

Compilation is offline. A valid manifest can describe a future execution version;
runtime support is checked separately, before provider selection.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from .engine import validate_entry_window
from .rules import parse_rules
from .regime import validate_regime_rules
from .strategies import (
    StrategyDefinition, StrategyRunRequest, StrategyVariableUse,
    _immutable_mapping, _require_identifier,
    minute_strategy_definition,
)
from .variables import FilterRole


def _require_version(value: str, *, label: str) -> None:
    core = r'(?:0|[1-9][0-9]*)'
    identifier = r'(?:0|[1-9][0-9]*|[0-9]*[A-Za-z-][0-9A-Za-z-]*)'
    pattern = rf'{core}\.{core}\.{core}(?:-{identifier}(?:\.{identifier})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?'
    if not re.fullmatch(pattern, value):
        raise ValueError(f'{label} must be a semantic version')


class _Object(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, allow_inf_nan=False)


class Session(_Object):
    regular_hours_only: Literal[True] = True
    same_day_only: Literal[True] = True
    entry_start_time: str | None = None
    entry_end_time: str | None = None


class Entry(_Object):
    side: Literal['long', 'short']
    rules: str


class Risk(_Object):
    # Units are explicit in the field names: percent, minutes, account currency.
    stop_pct: float = Field(gt=0, lt=100)
    target_pct: float = Field(gt=0)
    max_hold_minutes: StrictInt = Field(ge=1)
    position_size: float = Field(gt=0)
    starting_capital: float = Field(gt=0)


class Execution(_Object):
    id: Literal['bktstr.next-bar-open'] = 'bktstr.next-bar-open'
    version: str = '1.0.0'
    slippage_bps: float = Field(default=2.0, ge=0, lt=10000)


class Filter(_Object):
    layer: Literal['technical', 'regime']
    role: Literal['gate'] = 'gate'
    rules: str


class ModelPolicy(_Object):
    enabled: bool = False
    model: str | None = None
    question: str | None = None


class PaperLimits(_Object):
    duration_minutes: StrictInt = Field(gt=0)
    position_limit: StrictInt = Field(gt=0)
    gross_limit: float = Field(gt=0)
    daily_loss_limit: float = Field(gt=0)
    stale_after_seconds: StrictInt = Field(gt=0)
    model_budget: float = Field(ge=0)
    end_policy: Literal['flatten', 'halt_entries']


class Evaluation(_Object):
    start: str
    end: str
    variant_budget: StrictInt = Field(ge=1)


class StrategyDocument(_Object):
    schema_version: Literal['1.0.0']
    strategy_id: str
    strategy_version: str
    hypothesis: str = Field(min_length=1)
    falsification: str = Field(min_length=1)
    mode: Literal['historical', 'paper'] = 'historical'
    instruments: dict[str, str]
    calendar: Literal['XNYS'] = 'XNYS'
    timezone: Literal['America/New_York'] = 'America/New_York'
    timeframe: Literal['1m'] = '1m'
    session: Session
    entry: Entry
    risk: Risk
    execution: Execution
    evaluation: Evaluation
    filters: list[Filter] = Field(default_factory=list)
    model_policy: ModelPolicy = Field(default_factory=ModelPolicy)
    paper_limits: PaperLimits | None = None

    @model_validator(mode='after')
    def validate_contract(self):
        _require_identifier(self.strategy_id, label='strategy id')
        _require_version(self.strategy_version, label='strategy version')
        _require_version(self.execution.version, label='execution version')
        if self.strategy_id == 'bktstr.bearish-regime-scalp':
            raise ValueError('configuration cannot redefine the registered baseline')
        if self.mode == 'paper' and self.paper_limits is None:
            raise ValueError('paper_limits are required for paper mode')
        if not self.hypothesis.strip() or not self.falsification.strip():
            raise ValueError('hypothesis and falsification cannot be blank')
        if 'subject' not in self.instruments or set(self.instruments) - {'subject', 'benchmark'}:
            raise ValueError('instruments require subject and optionally benchmark')
        for symbol in self.instruments.values():
            if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', symbol):
                raise ValueError('instrument symbols must be explicit uppercase equity/ETF symbols')
        validate_entry_window(self.session.entry_start_time, self.session.entry_end_time)
        if self.model_policy.model is not None and not re.fullmatch(
            r'typesafe/jev-\d+\.\d+(?:\.\d+)?', self.model_policy.model
        ):
            raise ValueError('model must be a pinned typesafe/jev version, not an alias')
        if self.model_policy.enabled:
            raise ValueError('model inference is not implemented; model_policy must be disabled')
        return self


@dataclass(frozen=True)
class StrategyManifest:
    document: Mapping[str, object]
    canonical_json: str
    digest: str
    definition: StrategyDefinition
    request: StrategyRunRequest


def _normalize_rules(spec, definitions):
    known = {item.column: item for item in definitions}
    normalized = []
    uses = {}
    for rule in parse_rules(spec):
        fields = [rule.left] + ([rule.right] if isinstance(rule.right, str) else [])
        for column in fields:
            if column not in known:
                raise ValueError(f'unsupported variable {column!r} in rule {spec!r}')
            definition = known[column]
            uses[definition.id] = StrategyVariableUse(definition.ref, FilterRole.GATE, spec, False)
        if isinstance(rule.right, float) and not math.isfinite(rule.right):
            raise ValueError('rule operands must be finite')
        normalized.append(f'{rule.left}.{rule.op}:{rule.right}')
    return ','.join(normalized), uses


def compile_strategy(document: Mapping[str, object]) -> StrategyManifest:
    """Validate and freeze a JSON-shaped strategy without acquiring any data."""
    from .measurements import intraday_definitions, regime_definitions, source_definitions

    if not isinstance(document, Mapping):
        raise TypeError('strategy document must be a mapping')
    value = StrategyDocument.model_validate(dict(document))
    normalized = value.model_dump(mode='json')
    technical = (*source_definitions('subject'), *intraday_definitions())
    entry, uses = _normalize_rules(value.entry.rules, technical)
    normalized['entry']['rules'] = entry
    entry_parts, regime_parts = [entry], []
    for index, item in enumerate(value.filters):
        definitions = technical if item.layer == 'technical' else regime_definitions()
        rules, extra_uses = _normalize_rules(item.rules, definitions)
        normalized['filters'][index]['rules'] = rules
        uses.update(extra_uses)
        (entry_parts if item.layer == 'technical' else regime_parts).append(rules)
    if regime_parts:
        validate_regime_rules(','.join(regime_parts), value.instruments.get('benchmark'))
    if any(key in uses for key in ('regime.relative_return20', 'regime.benchmark_return20')):
        if 'benchmark' not in value.instruments:
            raise ValueError('relative and benchmark rules require an explicit benchmark instrument')
    overrides = {
        **value.risk.model_dump(), **value.session.model_dump(),
        'side': value.entry.side, 'entry_rules': ','.join(entry_parts),
        'regime_rules': ','.join(regime_parts) or None,
        'slippage_bps': value.execution.slippage_bps,
    }
    definition = replace(
        minute_strategy_definition(),
        id=value.strategy_id, version=value.strategy_version,
        description=value.hypothesis, instrument_roles=tuple(sorted(value.instruments)),
        variable_uses=tuple(uses.values()), execution_model_version=value.execution.version,
    )
    definition.resolve(overrides)
    request = StrategyRunRequest(
        strategy_id=definition.id, strategy_version=definition.version,
        instruments=value.instruments, start=date.fromisoformat(value.evaluation.start),
        end=date.fromisoformat(value.evaluation.end), timeframe=value.timeframe,
        overrides=overrides,
    )
    normalized['evaluation']['start'] = request.start.isoformat()
    normalized['evaluation']['end'] = request.end.isoformat()
    canonical = json.dumps(normalized, sort_keys=True, separators=(',', ':'), allow_nan=False)
    return StrategyManifest(_immutable_mapping(normalized), canonical,
                            hashlib.sha256(canonical.encode()).hexdigest(), definition, request)


def load_strategy(path: str | Path) -> StrategyManifest:
    """Read strict JSON, rejecting duplicate keys rather than silently replacing them."""
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError(f'duplicate strategy field: {key}')
            result[key] = value
        return result
    return compile_strategy(json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=pairs))
