"""Deterministic, frozen macro inputs for future judgment and decision consumers."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from .macro import (EvidenceMode, EvidenceSnapshot, EvidenceUnavailable,
                    digest, effective_at, freeze, select_as_of, utc)
from .variables import DataTier, inherited_tier


@dataclass(frozen=True)
class EvidencePacket:
    id: str
    cutoff: datetime
    mode: EvidenceMode
    snapshot_ids: tuple[str, ...]
    payload_digest: str
    normalized_payload: Mapping[str, Any]
    tier: DataTier


def build_packet(snapshots: Iterable[EvidenceSnapshot], cutoff: datetime,
                 mode: EvidenceMode, *, max_age: timedelta,
                 required_series: tuple[str, ...] = (),
                 expectations: Mapping[str, str] | None = None) -> EvidencePacket:
    """Build source and numerical context, with an explicit freshness policy.

    Unknown publication timestamps age from observation time, conservatively:
    repeatedly downloading an old value cannot make it fresh. Differences are
    native normalized units, not inferred economic surprise percentages.
    """
    from .measurements import macro_numerical_context

    cutoff = utc(cutoff)
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise ValueError('max_age must be a positive timedelta')
    snapshots = tuple(snapshots)
    selected = select_as_of(snapshots, cutoff, mode)
    groups: dict[str, list[EvidenceSnapshot]] = {}
    for item in selected:
        groups.setdefault(item.series_id, []).append(item)
    if not groups or set(required_series) - groups.keys():
        raise EvidenceUnavailable('required macro series are unavailable')
    series, consumed = {}, {}
    expectations = dict(expectations or {})
    if set(expectations) - groups.keys():
        raise EvidenceUnavailable('expectation mapping refers to an unavailable actual series')
    for series_id, items in sorted(groups.items()):
        if len({item.source_id for item in items}) != 1:
            raise ValueError(f'ambiguous sources for {series_id}; choose one explicitly')
        items.sort(key=lambda item: item.observed_at)
        actual = items[-1]
        age_from = actual.published_at or actual.observed_at
        if cutoff - age_from > max_age:
            raise EvidenceUnavailable(f'stale macro evidence: {series_id}')
        if actual.value is None:
            raise EvidenceUnavailable(f'missing macro value: {series_id}')
        prior = items[-2] if len(items) > 1 else None
        expected, anchor = None, None
        if series_id in expectations:
            # A revision must not move the forecast deadline forward. Require an
            # explicitly identified initial release, not merely the earliest row
            # in an incomplete archive, and preserve that anchor in provenance.
            anchors = [item for item in snapshots
                       if item.source_id == actual.source_id and item.series_id == series_id
                       and item.observed_at == actual.observed_at
                       and item.release_kind == 'initial' and effective_at(item, mode) <= cutoff]
            if len({item.published_at for item in anchors}) > 1:
                raise ValueError('conflicting initial release timestamps')
            if anchors:
                anchor = min(anchors, key=lambda item: (item.ingested_at, item.id))
                forecasts = select_as_of(
                    (item for item in snapshots if item.series_id == expectations[series_id]
                     and item.observed_at == actual.observed_at),
                    anchor.published_at - timedelta(microseconds=1), mode,
                )
                if len(forecasts) > 1:
                    raise ValueError('ambiguous forecast sources')
                expected = forecasts[0] if forecasts else None
        context = macro_numerical_context(actual, prior, expected)
        series[series_id] = {**context, 'snapshot_id': actual.id,
                             'previous_snapshot_id': prior.id if prior else None,
                             'expectation_snapshot_id': expected.id if expected else None,
                             'initial_release_snapshot_id': anchor.id if anchor else None}
        for item in (actual, prior, expected, anchor):
            if item is not None:
                consumed[item.id] = item
    ordered = tuple(consumed[key] for key in sorted(consumed))
    tier = inherited_tier(tuple(item.tier for item in ordered), method_floor=DataTier.B)
    payload = {
        'schema_version': '1.0.0', 'formula_version': '1.0.0',
        'cutoff': cutoff.isoformat(), 'mode': mode, 'max_age_seconds': max_age.total_seconds(),
        'required_series': sorted(set(required_series)), 'expectations': expectations,
        'series': series, 'sources': [item.to_record() for item in ordered], 'tier': tier.value,
    }
    fingerprint = digest(payload)
    return EvidencePacket(fingerprint, cutoff, mode, tuple(item.id for item in ordered),
                          fingerprint, freeze(payload), tier)
