from contextlib import closing
from pathlib import Path
import json
import pandas as pd
import pytest

from test_configured_research import configured
from test_research_protocol import protocol_doc
from test_dataset_snapshots import sample_frames, sample_schedule


def final_protocol(request, name):
    return protocol_doc(request, id=name, final_candidates=[request['specification']],
        splits=[dict(name='final',stage='final',start=request['start'],end=request['end'])], attempt_budget=3)


def test_two_final_protocols_cannot_reserve_same_unseen_scope(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt
    store, catalog, request = configured(tmp_path)
    for name in ('a','b'):
        register_protocol(final_protocol(request, name), catalog)
    admit_attempt('a', request['specification'], request['application'], 'final', 'once', catalog)
    with pytest.raises(ValueError, match='reserv'):
        admit_attempt('b', request['specification'], request['application'], 'final', 'once', catalog)


def test_replay_preserves_original_stage_and_parent(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt
    from bktstr.services.research_archive import replay_research
    from bktstr.services.experiments import ExperimentWorker
    from bktstr.services.configured_research import research_operations
    store, catalog, request = configured(tmp_path)
    register_protocol(final_protocol(request, 'final'), catalog)
    original = admit_attempt('final', request['specification'], request['application'], 'final', 'once', catalog)
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    replay = replay_research(original.experiment_id, store)
    assert replay.request['protocol']['stage'] == 'final'
    assert replay.request['replay_of'] == original.experiment_id


@pytest.mark.parametrize('filename', ['services/event_studies.py', 'services/configured_research.py',
    'services/research_protocol.py', 'idea_resolution.py', 'dataset_snapshots.py', 'runtime.py'])
def test_result_producing_source_changes_build_identity(monkeypatch, filename):
    from bktstr.dataset_snapshots import build_identity
    before = build_identity()
    original = Path.read_bytes
    target = Path('bktstr', filename).resolve()
    monkeypatch.setattr(Path, 'read_bytes', lambda path: original(path) + (b'changed' if path.resolve() == target else b''))
    assert build_identity() != before


def test_out_of_scope_study_fails_instead_of_reporting_zero_events(tmp_path):
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    submit_research_run(store, request | {'start':'2027-01-04T14:30:00Z','end':'2027-01-04T15:00:00Z'}, 'outside')
    result = ExperimentWorker(store, research_operations(store)).run_one()
    assert result.status == 'failed'
    assert 'scope' in result.error['message']


def test_new_protocol_name_does_not_reset_attempt_budget(tmp_path):
    from bktstr.services.research_protocol import register_protocol, admit_attempt
    store, catalog, request = configured(tmp_path)
    for name in ('a','b'):
        register_protocol(protocol_doc(request,id=name), catalog)
    admit_attempt('a', request['specification'], request['application'], 'dev', 'once', catalog)
    with pytest.raises(ValueError, match='budget'):
        admit_attempt('b', request['specification'], request['application'], 'dev', 'once', catalog)
    with closing(store._connect()) as db:
        assert db.execute('SELECT count(*) FROM research_admission_failures').fetchone()[0] == 1
    from bktstr.services.idea_reports import idea_report
    report = idea_report(request['idea']['id'], store)
    assert report['blocked_admissions'][0]['protocol_id'] == 'b'
    assert report['search_history']['research_families'][0]['attempts_used'] == 1


def test_study_and_policy_share_scored_session_warmup(tmp_path):
    import asyncio
    from bktstr.dataset_snapshots import freeze_dataset, SnapshotProvider
    from bktstr.event_research import build_events
    from bktstr.engine import add_indicators
    from test_research_components import study_doc
    frames = sample_frames()
    previous = frames['SPY'].copy()
    from datetime import timedelta
    previous.index = pd.DatetimeIndex([t.to_pydatetime() - timedelta(days=1) for t in previous.index])
    previous['volume'] = 9000
    schedule = [dict(date='2026-08-16',open='2026-08-16T13:30:00Z',close='2026-08-16T13:36:00Z'),*sample_schedule()]
    snap = freeze_dataset({'SPY':pd.concat([previous, frames['SPY']])}, schedule, tmp_path, source='synthetic')
    study = study_doc(event_rules='close.gt:0', contexts=['rsi14','volume_ratio20'])
    events = build_events(study, {'instruments':{'subject':'SPY'}}, snap, start=sample_schedule()[0]['open'],end=sample_schedule()[0]['close'])
    from datetime import date
    bars = asyncio.run(SnapshotProvider(snap).fetch_bars('SPY',date(2026,8,17),date(2026,8,17),'1m'))
    features = add_indicators(bars)
    for row, (_, feature) in zip(events.document['rows'], features.iterrows()):
        for name in study['contexts']:
            value = None if pd.isna(feature[name]) else float(feature[name])
            assert row['values'][name] == value
    assert events.document['warmup'] == 'scored_sessions_only'


def test_direct_research_jobs_can_be_cancelled(tmp_path):
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.research_protocol import cancel_attempt
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    original = submit_research_run(store, request, 'cancel-direct')
    assert cancel_attempt(original.experiment_id, catalog)
    result = ExperimentWorker(store, research_operations(store)).run_one()
    assert result.error['code'] == 'research_cancelled'


def test_bootstrap_keeps_scheduled_zero_event_sessions():
    from bktstr.services.event_studies import block_resamples, StudyAnalysisSpec
    rows = [dict(session='2026-08-03',value=1),dict(session='2026-08-05',value=3)]
    axis = ['2026-08-03','2026-08-04','2026-08-05','2026-08-06']
    samples = block_resamples(rows, StudyAnalysisSpec(label='x', block_sessions=2, minimum_blocks=2), session_axis=axis)
    assert len(samples) == 200


def test_backup_holds_database_write_boundary(tmp_path, monkeypatch):
    import sqlite3
    from bktstr.services.research_archive import backup_research
    store, catalog, request = configured(tmp_path / 'original')
    import shutil
    original = shutil.copytree
    checked = []
    def copy(source, destination, *args, **kwargs):
        with closing(sqlite3.connect(store.database_path, timeout=.01, isolation_level=None)) as db:
            with pytest.raises(sqlite3.OperationalError, match='locked'):
                db.execute("INSERT INTO research_assessments VALUES ('concurrent','idea','now','{}')")
        checked.append(True)
        return original(source,destination,*args,**kwargs)
    monkeypatch.setattr(shutil,'copytree',copy)
    backup_research(store,tmp_path/'backup')
    assert checked
