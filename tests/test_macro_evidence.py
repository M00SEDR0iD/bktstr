import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import httpx
import pytest

from bktstr.macro import EvidenceSnapshot, EvidenceUnavailable, select_as_of
from bktstr.evidence_packets import build_packet
from bktstr.providers import BLSMacroProvider
from bktstr.variable_store import EvidenceStore

FIXTURES = Path(__file__).parent / 'fixtures' / 'macro'
HISTORICAL = 'historical_publication'
PROSPECTIVE = 'prospective_receipt'


def dt(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def releases():
    return tuple(EvidenceSnapshot.from_record(item) for item in json.loads((FIXTURES / 'revisions.json').read_text()))


@pytest.mark.parametrize('cutoff,mode,expected', [
    ('2026-03-06T13:29:59Z', HISTORICAL, []),
    ('2026-03-06T13:30:00Z', HISTORICAL, [3.0]),
    ('2026-03-06T13:34:59Z', PROSPECTIVE, []),
    ('2026-03-06T13:35:00Z', PROSPECTIVE, [3.0]),
    ('2026-03-08T12:00:00Z', HISTORICAL, [3.0]),
    ('2026-03-09T12:30:00Z', HISTORICAL, [3.2]),
    ('2026-03-09T12:31:59Z', PROSPECTIVE, [3.0]),
    ('2026-03-09T12:32:00Z', PROSPECTIVE, [3.2]),
])
def test_release_revision_and_receipt_boundaries(cutoff, mode, expected):
    assert [s.value for s in select_as_of(releases(), dt(cutoff), mode)] == expected


def test_dst_offsets_represent_same_cutoff():
    assert select_as_of(releases(), dt('2026-03-09T08:30:00-04:00'), HISTORICAL) == select_as_of(releases(), dt('2026-03-09T12:30:00Z'), HISTORICAL)


@pytest.mark.parametrize('field,value', [('published_at', None), ('vintage', None)])
def test_unverified_history_is_rejected(field, value):
    snapshot = replace(releases()[0], release_kind='unknown', **{field: value})
    with pytest.raises(EvidenceUnavailable, match='historical'):
        select_as_of([snapshot], dt('2026-03-10T00:00:00Z'), HISTORICAL)
    assert select_as_of([snapshot], dt('2026-03-10T00:00:00Z'), PROSPECTIVE)


def test_late_old_revision_does_not_replace_new_release():
    first, revision = releases()
    first = replace(first, ingested_at=dt('2026-03-10T00:00:00Z'))
    assert select_as_of([first, revision], dt('2026-03-11T00:00:00Z'), PROSPECTIVE)[0].value == 3.2


def test_duplicate_delivery_is_idempotent_but_conflicting_vintage_fails():
    first = releases()[0]
    assert select_as_of([first, first], first.ingested_at, PROSPECTIVE) == (first,)
    with pytest.raises(ValueError, match='conflicting'):
        select_as_of([first, replace(first, value=99)], first.ingested_at, PROSPECTIVE)


def test_packet_freezes_inputs_and_requires_fresh_available_values():
    first = releases()[0]
    packet = build_packet([first], first.ingested_at, PROSPECTIVE, max_age=timedelta(days=2), required_series=('macro.inflation',))
    assert packet.snapshot_ids == (first.id,)
    assert packet.normalized_payload['series']['macro.inflation']['surprise'] is None
    with pytest.raises(TypeError):
        packet.normalized_payload['series']['macro.inflation']['value'] = 0
    for items, cutoff in [([first], first.ingested_at + timedelta(days=3)),
                          ([replace(first, value=None)], first.ingested_at),
                          ([], first.ingested_at)]:
        with pytest.raises(EvidenceUnavailable):
            build_packet(items, cutoff, PROSPECTIVE, max_age=timedelta(days=2), required_series=('macro.inflation',))


def test_packet_digest_order_independent_and_mode_sensitive():
    first, revision = releases()
    cutoff = revision.ingested_at
    a = build_packet([first, revision], cutoff, HISTORICAL, max_age=timedelta(days=10))
    assert a == build_packet([revision, first], cutoff, HISTORICAL, max_age=timedelta(days=10))
    assert a.id != build_packet([first, revision], cutoff, PROSPECTIVE, max_age=timedelta(days=10)).id


def test_units_changes_and_expectation_are_time_aligned():
    actual = releases()[0]
    prior = replace(actual, value=250, units='basis_points', observed_at=dt('2026-01-31T00:00:00Z'), published_at=dt('2026-02-06T13:30:00Z'), available_at=dt('2026-02-06T13:30:00Z'), ingested_at=dt('2026-02-06T13:31:00Z'))
    expected = replace(actual, series_id='forecast.inflation', value=.028, units='fraction', published_at=dt('2026-03-06T13:00:00Z'), available_at=dt('2026-03-06T13:00:00Z'), ingested_at=dt('2026-03-06T13:01:00Z'))
    packet = build_packet([actual, prior, expected], actual.ingested_at, PROSPECTIVE, max_age=timedelta(days=40), expectations={'macro.inflation':'forecast.inflation'})
    context = packet.normalized_payload['series']['macro.inflation']
    assert context['units'] == 'percent'
    assert context['change'] == .5
    assert context['surprise'] == pytest.approx(.2)
    late = replace(expected, ingested_at=actual.ingested_at)
    late_packet = build_packet([actual, late], actual.ingested_at, PROSPECTIVE, max_age=timedelta(days=2), expectations={'macro.inflation':'forecast.inflation'})
    assert late_packet.normalized_payload['series']['macro.inflation']['surprise'] is None


@pytest.mark.parametrize('field,value', [('value', True), ('value', float('nan')), ('units', 'mystery'), ('ingested_at', datetime(2026,3,6)), ('payload', {'x':float('inf')})])
def test_invalid_source_records_fail_closed(field, value):
    with pytest.raises((ValueError, TypeError)):
        replace(releases()[0], **{field:value})


def test_store_round_trip_preserves_offline_evidence(tmp_path):
    path = tmp_path / 'macro.sqlite3'
    store = EvidenceStore(path)
    snapshots = releases()
    store.put_many(snapshots)
    store.put_many(snapshots)
    restored = EvidenceStore(path).load()
    assert set(s.id for s in restored) == set(s.id for s in snapshots)
    packet = build_packet(restored, snapshots[1].ingested_at, HISTORICAL, max_age=timedelta(days=10))
    assert packet.normalized_payload['series']['macro.inflation']['value'] == 3.2


def test_recorded_bls_adapter_is_prospective_only():
    recorded = json.loads((FIXTURES / 'bls_cpi_recorded.json').read_text())
    received = dt(recorded['received_at'])
    async def handler(request):
        assert request.url.path.endswith('/CUUR0000SA0')
        return httpx.Response(200, json=recorded['payload'])
    provider = BLSMacroProvider(transport=httpx.MockTransport(handler), clock=lambda:received)
    snapshots = asyncio.run(provider.fetch_snapshots('CUUR0000SA0'))
    assert len(snapshots) == 32  # 34 rows, including two excluded annual averages.
    assert max(snapshots, key=lambda s:s.observed_at).value == 334.980
    assert all(s.published_at is None and s.vintage is None for s in snapshots)
    assert not select_as_of(snapshots, received-timedelta(microseconds=1), PROSPECTIVE)
    with pytest.raises(EvidenceUnavailable):
        select_as_of(snapshots, received, HISTORICAL)
    assert select_as_of(snapshots, received, PROSPECTIVE)


def test_bls_unknown_series_rejected_before_network():
    async def handler(request):
        pytest.fail('unsupported dataset reached provider')
    with pytest.raises(ValueError, match='unsupported'):
        asyncio.run(BLSMacroProvider(transport=httpx.MockTransport(handler)).fetch_snapshots('UNVERIFIED'))


def test_delayed_availability_and_missing_latest_never_backfill():
    first, revision = releases()
    delayed = replace(revision, available_at=revision.published_at + timedelta(hours=1))
    assert select_as_of([first, delayed], revision.published_at, HISTORICAL) == (first,)
    missing = replace(revision, value=None)
    with pytest.raises(EvidenceUnavailable, match='missing'):
        build_packet([first, missing], revision.ingested_at, HISTORICAL, max_age=timedelta(days=10))


def test_unknown_publication_repoll_cannot_refresh_stale_observation():
    snapshot = replace(releases()[0], published_at=None, vintage=None, release_kind='unknown',
                       ingested_at=dt('2026-04-01T00:00:00Z'), available_at=dt('2026-04-01T00:00:00Z'))
    with pytest.raises(EvidenceUnavailable, match='stale'):
        build_packet([snapshot], snapshot.ingested_at, PROSPECTIVE, max_age=timedelta(days=2))


def test_lower_trust_propagates_and_unit_mismatch_rejects():
    from bktstr.variables import DataTier
    first = replace(releases()[0], tier=DataTier.D)
    packet = build_packet([first], first.ingested_at, PROSPECTIVE, max_age=timedelta(days=2))
    assert packet.tier is DataTier.D
    prior = replace(first, observed_at=first.observed_at-timedelta(days=31), units='index')
    with pytest.raises(ValueError, match='compatible units'):
        build_packet([prior, first], first.ingested_at, PROSPECTIVE, max_age=timedelta(days=40))


def test_store_detects_tampering_and_rolls_back_failed_batch(tmp_path):
    import sqlite3
    path = tmp_path / 'evidence.sqlite3'
    store = EvidenceStore(path)
    first = releases()[0]
    with pytest.raises(TypeError):
        store.put_many([first, object()])
    assert store.load() == ()
    store.put_many([first])
    changed = first.to_record()
    changed['value'] = 99
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE macro_evidence SET record=?', (json.dumps(changed),))
    with pytest.raises(ValueError, match='digest'):
        store.load()


@pytest.mark.parametrize('payload', [
    {'status':'REQUEST_FAILED'},
    {'status':'REQUEST_SUCCEEDED','Results':{'series':[]}},
    {'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':'CUUR0000SA0','data':[]}]}}
])
def test_bls_failure_does_not_create_evidence(payload):
    async def handler(request):
        return httpx.Response(200, json=payload)
    with pytest.raises(ValueError):
        asyncio.run(BLSMacroProvider(transport=httpx.MockTransport(handler)).fetch_snapshots('CUUR0000SA0'))


def test_revision_cannot_turn_post_release_forecast_into_consensus():
    first, revision = releases()
    late_forecast = replace(first, series_id='forecast.inflation', value=3.1,
        published_at=dt('2026-03-08T12:00:00Z'), available_at=dt('2026-03-08T12:00:00Z'),
        ingested_at=dt('2026-03-08T12:00:00Z'))
    packet = build_packet([first, revision, late_forecast], revision.ingested_at,
        PROSPECTIVE, max_age=timedelta(days=10), expectations={'macro.inflation':'forecast.inflation'})
    assert packet.normalized_payload['series']['macro.inflation']['surprise'] is None


def test_pre_release_forecast_survives_later_forecast_update():
    first, revision = releases()
    forecast = replace(first, series_id='forecast.inflation', value=2.8,
        published_at=dt('2026-03-06T12:00:00Z'), available_at=dt('2026-03-06T12:00:00Z'),
        ingested_at=dt('2026-03-06T12:00:00Z'))
    updated = replace(forecast, value=3.1, vintage='later',
        published_at=dt('2026-03-08T12:00:00Z'), available_at=dt('2026-03-08T12:00:00Z'),
        ingested_at=dt('2026-03-08T12:00:00Z'))
    packet = build_packet([first, revision, forecast, updated], revision.ingested_at,
        PROSPECTIVE, max_age=timedelta(days=10), expectations={'macro.inflation':'forecast.inflation'})
    context = packet.normalized_payload['series']['macro.inflation']
    assert context['surprise'] == pytest.approx(.4)
    assert context['expectation_snapshot_id'] == forecast.id
    assert first.id in packet.snapshot_ids


def test_no_surprise_without_identified_initial_release():
    first, revision = releases()
    forecast = replace(first, series_id='forecast.inflation', value=2.8,
        published_at=dt('2026-03-06T12:00:00Z'), available_at=dt('2026-03-06T12:00:00Z'),
        ingested_at=dt('2026-03-06T12:00:00Z'))
    packet = build_packet([revision, forecast], revision.ingested_at, PROSPECTIVE,
        max_age=timedelta(days=10), expectations={'macro.inflation':'forecast.inflation'})
    assert packet.normalized_payload['series']['macro.inflation']['surprise'] is None


def test_store_releases_database_handles_after_operations(tmp_path):
    # Windows cannot move/delete an open database; backups and temp replay need
    # deterministic connection closure, not eventual garbage collection.
    import gc
    path = tmp_path / 'evidence.sqlite3'
    gc.disable()
    try:
        store = EvidenceStore(path)
        store.put_many(releases())
        store.load()
        path.unlink()
    finally:
        gc.enable()
        gc.collect()
