"""Immutable macro source evidence and explicit point-in-time selection."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Literal

from .variables import DataTier

EvidenceMode = Literal['historical_publication', 'prospective_receipt']


class EvidenceUnavailable(ValueError):
    """Required evidence cannot support the requested decision cutoff."""


def utc(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('evidence timestamps must be timezone-aware')
    return value.astimezone(timezone.utc)


def json_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise ValueError('evidence JSON keys must be strings')
        return {k: json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if value is None or type(value) in (str, bool, int):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError('evidence payload must contain finite JSON values')


def canonical_json(value: Any) -> str:
    return json.dumps(json_value(value), sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode('utf-8')).hexdigest()


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def normalize_value(value: float | None, units: str) -> tuple[float | None, str]:
    conversions = {'percent': (1, 'percent'), 'basis_points': (.01, 'percent'),
                   'fraction': (100, 'percent'), 'index': (1, 'index'),
                   'usd': (1, 'usd'), 'count': (1, 'count')}
    if units not in conversions:
        raise ValueError(f'unsupported evidence units: {units!r}')
    factor, normalized_units = conversions[units]
    if value is None:
        return None, normalized_units
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('evidence value must be a finite number or null')
    result = float(value) * factor
    if not math.isfinite(result):
        raise ValueError('normalized value must be finite')
    return result, normalized_units


@dataclass(frozen=True)
class EvidenceSnapshot:
    source_id: str
    series_id: str
    value: float | None
    units: str
    observed_at: datetime
    published_at: datetime | None
    ingested_at: datetime
    available_at: datetime
    vintage: str | None
    release_kind: Literal['initial', 'revision', 'unknown'] = 'unknown'
    payload: Mapping[str, Any] = field(default_factory=dict)
    tier: DataTier = DataTier.A
    id: str = field(init=False)
    content_digest: str = field(init=False)

    def __post_init__(self):
        for label in ('source_id', 'series_id'):
            value = getattr(self, label)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f'{label} cannot be blank')
        if self.vintage is not None and (not isinstance(self.vintage, str) or not self.vintage.strip()):
            raise ValueError('vintage must be nonempty or null')
        if self.release_kind not in ('initial', 'revision', 'unknown'):
            raise ValueError('unsupported release_kind')
        if self.release_kind != 'unknown' and (self.published_at is None or self.vintage is None):
            raise ValueError('identified releases require publication and vintage')
        if not isinstance(self.tier, DataTier):
            raise ValueError('tier must be a DataTier')
        normalize_value(self.value, self.units)
        if self.value is not None:
            object.__setattr__(self, 'value', float(self.value))
        for name in ('observed_at', 'published_at', 'ingested_at', 'available_at'):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, utc(value))
            elif name != 'published_at':
                raise ValueError(f'{name} is required')
        if self.published_at is not None and self.available_at < self.published_at:
            raise ValueError('available_at cannot precede publication')
        if not isinstance(self.payload, Mapping):
            raise ValueError('payload must be a JSON object')
        object.__setattr__(self, 'payload', freeze(json_value(self.payload)))
        source_record = self.to_record()
        source_record.pop('ingested_at')
        object.__setattr__(self, 'content_digest', digest(source_record))
        object.__setattr__(self, 'id', digest(self.to_record()))

    def to_record(self) -> dict[str, Any]:
        return {
            'source_id': self.source_id, 'series_id': self.series_id,
            'value': self.value, 'units': self.units, 'vintage': self.vintage,
            'release_kind': self.release_kind,
            'observed_at': self.observed_at.isoformat(),
            'published_at': self.published_at.isoformat() if self.published_at else None,
            'ingested_at': self.ingested_at.isoformat(), 'available_at': self.available_at.isoformat(),
            'payload': json_value(self.payload), 'tier': self.tier.value,
        }

    @classmethod
    def from_record(cls, record: Mapping[str, Any]) -> EvidenceSnapshot:
        values = dict(record)
        for name in ('observed_at', 'published_at', 'ingested_at', 'available_at'):
            if isinstance(values.get(name), str):
                values[name] = datetime.fromisoformat(values[name].replace('Z', '+00:00'))
        if 'tier' in values:
            values['tier'] = DataTier(values['tier'])
        return cls(**values)


def effective_at(snapshot: EvidenceSnapshot, mode: EvidenceMode) -> datetime:
    if mode == 'historical_publication':
        if snapshot.published_at is None or snapshot.vintage is None:
            raise EvidenceUnavailable(f'{snapshot.series_id}: historical publication and vintage required')
        return max(snapshot.published_at, snapshot.available_at)
    if mode == 'prospective_receipt':
        return max(snapshot.ingested_at, snapshot.available_at, snapshot.published_at or snapshot.available_at)
    raise ValueError('unknown evidence timing mode')


def select_as_of(snapshots: Iterable[EvidenceSnapshot], cutoff: datetime,
                 mode: EvidenceMode) -> tuple[EvidenceSnapshot, ...]:
    """Latest usable vintage per source/series/observation, never an arrival-order overwrite.

    Retrospective mode requires verified publication/vintage for every supplied
    record. Null latest observations remain selected so callers cannot backfill
    a missing release with an older value. Freshness is a packet policy.
    """
    cutoff = utc(cutoff)
    if mode not in ('historical_publication', 'prospective_receipt'):
        raise ValueError('unknown evidence timing mode')
    vintages, selected = {}, {}
    for item in snapshots:
        if not isinstance(item, EvidenceSnapshot):
            raise TypeError('snapshots must contain EvidenceSnapshot records')
        usable = effective_at(item, mode)
        key = (item.source_id, item.series_id, item.observed_at)
        if item.vintage is not None:
            vintage_key = (*key, item.vintage)
            previous_digest = vintages.setdefault(vintage_key, item.content_digest)
            if previous_digest != item.content_digest:
                raise ValueError(f'conflicting source vintage: {item.series_id}/{item.vintage}')
        if usable > cutoff or item.observed_at > cutoff:
            continue
        previous = selected.get(key)
        rank = (item.published_at or item.available_at, item.available_at)
        if previous is not None:
            previous_rank = (previous.published_at or previous.available_at, previous.available_at)
            if rank == previous_rank:
                if item.content_digest != previous.content_digest:
                    raise ValueError(f'conflicting simultaneous source events: {item.series_id}')
                # Repeated delivery of one source event preserves its first receipt.
                if item.ingested_at < previous.ingested_at:
                    selected[key] = item
                continue
            if rank < previous_rank:
                continue
        selected[key] = item
    return tuple(selected[key] for key in sorted(selected))
