import copy
import json
from pathlib import Path

import pandas as pd
import pytest

from bktstr.dataset_snapshots import freeze_dataset
from bktstr.research_ideas import digest
from bktstr.services.experiments import ExperimentStore
from bktstr.services.research_store import ResearchCatalog
from bktstr.services.research_transfer import export_bundle, import_bundle


def source_store(path):
    store = ExperimentStore(path)
    catalog = ResearchCatalog(store)
    idea = json.loads((Path(__file__).parents[1] / 'examples/ideas/vwap-continuation.json').read_text())
    catalog.register('idea', idea)
    opened = pd.Timestamp('2026-08-03T13:30:00Z')
    frame = pd.DataFrame([[100., 101., 99., 100., 50.]],
                         index=pd.DatetimeIndex([opened]), columns=['open', 'high', 'low', 'close', 'volume'])
    snapshot = freeze_dataset({'SPY': frame}, [dict(date='2026-08-03', open=opened.isoformat(),
        close='2026-08-03T13:31:00+00:00')], catalog.datasets, source='synthetic-test')
    artifact = catalog.save_artifact({'events': [{'value': 10}]})
    record, _ = store.create_experiment('configured_backtest', {'dataset': snapshot.id, 'idea': {'id': idea['id']}},
                                        idempotency_key='common-client-key')
    store.complete(record.experiment_id, {'events_artifact': artifact, 'ev_r_per_trade': 0.3}, {'build': 'original-build'})
    (catalog.reports / 'unused.html').write_text('derived report')
    return store, snapshot, record.experiment_id


def rehash(bundle):
    bundle['digest'] = digest({k: v for k, v in bundle.items() if k != 'digest'})
    return bundle


def test_round_trip_preserves_results_inputs_and_unrelated_server_data(tmp_path):
    source, snapshot, exp = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    other, _ = target.create_experiment('configured_backtest', {'unrelated': True}, idempotency_key='common-client-key')
    target.complete(other.experiment_id, {'other': True}, {})
    bundle = export_bundle(source)
    imported = import_bundle(target, bundle)
    assert imported['experiments_added'] == 1
    assert target.load_experiment(exp).result == source.load_experiment(exp).result
    assert target.load_experiment(exp).provenance == source.load_experiment(exp).provenance
    assert target.load_experiment(other.experiment_id).result['other'] is True
    assert (target.root / 'research/datasets' / (snapshot.id + '.json')).read_bytes() == (
        source.root / 'research/datasets' / (snapshot.id + '.json')).read_bytes()
    assert not list((target.root / 'research/reports').iterdir())
    assert import_bundle(target, bundle)['experiments_added'] == 0
    assert target.load_artifact_manifest(exp)


def test_changed_revision_collision_rejects_whole_import(tmp_path):
    source, _, exp = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    catalog = ResearchCatalog(target)
    idea = ResearchCatalog(source).revisions('idea')[0].document
    idea['thesis'] = 'An unrelated but conflicting hypothesis'
    catalog.register('idea', idea)
    before = list(catalog.datasets.iterdir())
    with pytest.raises(ValueError, match='collision'):
        import_bundle(target, export_bundle(source))
    assert list(catalog.datasets.iterdir()) == before
    with target._connect() as db:
        assert db.execute('SELECT count(*) FROM experiments').fetchone()[0] == 0


@pytest.mark.parametrize('mutation', ['table', 'path', 'content', 'active'])
def test_invalid_payload_rejected_without_partial_import(tmp_path, mutation):
    source, _, _ = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    bundle = export_bundle(source)
    if mutation == 'table':
        bundle['tables']['worker_leases'] = []
    elif mutation == 'path':
        content = next(iter(bundle['objects']['datasets'].values()))
        bundle['objects']['datasets']['../../escape'] = content
    elif mutation == 'content':
        content = next(iter(bundle['objects']['datasets'].values()))
        content['source'] = 'tampered'
    else:
        bundle['tables']['experiments'][0]['status'] = 'queued'
    rehash(bundle)
    with pytest.raises(ValueError):
        import_bundle(target, bundle)
    with target._connect() as db:
        assert db.execute('SELECT count(*) FROM experiments').fetchone()[0] == 0


def test_export_refuses_unfinished_experiments(tmp_path):
    store = ExperimentStore(tmp_path)
    store.create_experiment('backtest', {'value': 1})
    with pytest.raises(ValueError, match='terminal'):
        export_bundle(store)


def test_bundle_digest_and_size_are_checked(tmp_path):
    source, _, _ = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    bundle = export_bundle(source)
    corrupted = copy.deepcopy(bundle)
    corrupted['digest'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        import_bundle(target, corrupted)
    with pytest.raises(ValueError, match='limit'):
        import_bundle(target, bundle, max_bytes=10)
    with pytest.raises(ValueError, match='limit'):
        export_bundle(source, max_bytes=10)
    assert export_bundle(source, max_bytes=None)['digest'] == bundle['digest']
    assert import_bundle(target, bundle, max_bytes=None)['experiments_added'] == 1


def test_storage_audit_ids_do_not_collide_and_repeat_import_is_idempotent(tmp_path):
    from bktstr.services.research_storage import set_pin
    source, snapshot, _ = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    set_pin(ResearchCatalog(source), snapshot.id, False)
    catalog = ResearchCatalog(target)
    export_bundle(target)  # Initialize the destination audit tables.
    with catalog.transaction() as db:
        db.execute("INSERT INTO research_storage_events VALUES (1,'earlier','other','pin')")
    bundle = export_bundle(source)
    import_bundle(target, bundle)
    import_bundle(target, bundle)
    with target._connect() as db:
        rows = db.execute('SELECT * FROM research_storage_events').fetchall()
    assert len(rows) == 2
    assert {row['dataset'] for row in rows} == {'other', snapshot.id}


def test_evicted_input_metadata_survives_transfer_and_missing_result_artifact_fails(tmp_path):
    source, snapshot, exp = source_store(tmp_path / 'source')
    bundle = export_bundle(source)
    bundle['objects']['datasets'].clear()
    bundle['tables']['research_datasets'][0]['evicted_at'] = '2026-09-21T00:00:00+00:00'
    bundle['tables']['research_datasets'][0]['pinned'] = 0
    target = ExperimentStore(tmp_path / 'target')
    import_bundle(target, rehash(bundle))
    assert target.load_experiment(exp).result['ev_r_per_trade'] == .3
    assert not (target.root / 'research/datasets' / (snapshot.id + '.json')).exists()
    bundle['objects']['artifacts'].clear()
    with pytest.raises(ValueError, match='missing a retained result artifact'):
        import_bundle(ExperimentStore(tmp_path / 'broken'), rehash(bundle))


def test_failed_file_publication_rolls_back_catalog(tmp_path, monkeypatch):
    source, _, _ = source_store(tmp_path / 'source')
    target = ExperimentStore(tmp_path / 'target')
    bundle = export_bundle(source)
    from bktstr.services import research_transfer
    original = research_transfer.atomic_text
    count = 0

    def broken(path, text):
        nonlocal count
        count += 1
        if count == 2:
            raise OSError('simulated full disk')
        return original(path, text)

    monkeypatch.setattr(research_transfer, 'atomic_text', broken)
    with pytest.raises(OSError, match='full disk'):
        import_bundle(target, bundle)
    with target._connect() as db:
        assert db.execute('SELECT count(*) FROM experiments').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM research_revisions').fetchone()[0] == 0
    assert not list((target.root / 'research/datasets').iterdir())
