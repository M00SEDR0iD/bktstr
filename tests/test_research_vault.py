import copy
import json

import pytest

from test_configured_research import configured
from bktstr.services.configured_research import submit_research_run, research_operations
from bktstr.services.experiments import ExperimentStore, ExperimentWorker
from bktstr.services.research_store import ResearchCatalog
from bktstr.services.research_transfer import export_bundle
from bktstr.services.research_vault import preserve_bundle, list_archives, load_archive, render_archive_idea


def archive_fixture(root):
    store, _, request = configured(root)
    submit_research_run(store, request, 'vault-fixture')
    worker = ExperimentWorker(store, research_operations(store))
    try:
        result = worker.run_one()
        assert result.status == 'completed', result.error
    finally:
        worker.release_lease()
    return export_bundle(store), request, result.experiment_id


def test_conflicting_native_revisions_are_preserved_without_overwrite(tmp_path):
    bundle, request, _ = archive_fixture(tmp_path / 'source')
    main = ExperimentStore(tmp_path / 'main')
    # Deliberately select the actual idea, independent of table sort ordering.
    idea = json.loads(next(row['document'] for row in bundle['tables']['research_revisions'] if row['kind'] == 'idea'))
    changed = dict(idea, title='Current live idea with conflicting identity')
    ResearchCatalog(main).register('idea', changed)
    saved = preserve_bundle(main, bundle)
    assert saved['digest'] == bundle['digest']
    assert saved['experiments'] == 1
    assert load_archive(main, saved['digest']) == bundle
    assert preserve_bundle(main, bundle)['digest'] == saved['digest']
    assert len(list_archives(main)) == 1
    assert ResearchCatalog(main).revisions('idea')[0].document['title'] == changed['title']
    with main._connect() as db:
        assert db.execute('SELECT count(*) FROM experiments').fetchone()[0] == 0


def test_html_uses_saved_results_and_records_main_catalog_exposure(tmp_path, monkeypatch):
    bundle, request, exp = archive_fixture(tmp_path / 'source')
    main = ExperimentStore(tmp_path / 'main')
    preserve_bundle(main, bundle)

    def forbidden(*args, **kwargs):
        raise AssertionError('archive rendering must not execute a strategy or read numerical inputs')

    monkeypatch.setattr(ExperimentWorker, 'run', forbidden)
    monkeypatch.setattr('bktstr.dataset_snapshots.DatasetSnapshot.frame', forbidden)
    html = render_archive_idea(main, bundle['digest'], request['idea']['id'])
    assert exp in html
    assert '<html' in html.lower()
    assert load_archive(main, bundle['digest']) == bundle
    with main._connect() as db:
        rows = db.execute('SELECT * FROM research_exposures').fetchall()
    assert len(rows) == 1
    assert rows[0]['symbol'] == 'SPY'
    assert rows[0]['start'] == request['start'].replace('Z', '+00:00')
    assert rows[0]['protocol_id'] == ''
    assert bundle['digest'] in rows[0]['artifact_id']


def test_full_backup_contains_vault_and_corruption_is_rejected(tmp_path):
    from bktstr.services.research_archive import backup_research, restore_research
    bundle, _, _ = archive_fixture(tmp_path / 'source')
    main = ExperimentStore(tmp_path / 'main')
    preserve_bundle(main, bundle)
    backup_research(main, tmp_path / 'backup')
    restored = restore_research(tmp_path / 'backup', tmp_path / 'restored')
    assert load_archive(restored, bundle['digest']) == bundle
    path = main.root / 'research' / 'archives' / (bundle['digest'] + '.json')
    path.write_text('{}')
    with pytest.raises(ValueError):
        load_archive(main, bundle['digest'])
    with pytest.raises(ValueError, match='collision'):
        preserve_bundle(main, bundle)


def test_invalid_bundle_and_path_are_rejected(tmp_path):
    bundle, _, _ = archive_fixture(tmp_path / 'source')
    main = ExperimentStore(tmp_path / 'main')
    invalid = copy.deepcopy(bundle)
    invalid['digest'] = '0' * 64
    with pytest.raises(ValueError, match='digest'):
        preserve_bundle(main, invalid)
    with pytest.raises(ValueError, match='digest'):
        load_archive(main, '../other')
    assert list_archives(main) == []


@pytest.mark.parametrize('retained_input', [True, False])
def test_public_export_records_exposure_and_internal_backup_does_not(tmp_path, retained_input):
    from bktstr.research_ideas import digest
    from bktstr.services.research_transfer import import_bundle
    bundle, request, _ = archive_fixture(tmp_path / 'source')
    if not retained_input:
        bundle['objects']['datasets'].clear()
        bundle['tables']['research_datasets'][0]['evicted_at'] = '2026-09-21T00:00:00+00:00'
        bundle['tables']['research_datasets'][0]['pinned'] = 0
        bundle['digest'] = digest({k: v for k, v in bundle.items() if k != 'digest'})
    main = ExperimentStore(tmp_path / 'main')
    import_bundle(main, bundle)
    internal = export_bundle(main)
    assert internal['tables']['research_exposures'] == []
    public = export_bundle(main, inspect=True)
    rows = public['tables']['research_exposures']
    assert len(rows) == (2 if retained_input else 1)
    assert rows[0]['symbol'] == 'SPY'
    assert rows[0]['protocol_id'] == ''
    assert rows[0]['reason'] == 'archive download'
    assert export_bundle(main)['tables']['research_exposures'] == rows


def test_downloaded_vault_bundle_records_main_exposure_without_changing_digest(tmp_path):
    bundle, _, _ = archive_fixture(tmp_path / 'source')
    main = ExperimentStore(tmp_path / 'main')
    preserve_bundle(main, bundle)
    assert load_archive(main, bundle['digest'], inspect=True) == bundle
    with main._connect() as db:
        rows = db.execute('SELECT * FROM research_exposures').fetchall()
    assert len(rows) == 2
    assert rows[0]['protocol_id'] == ''


def test_preservation_imports_prior_exposure_once_without_protocol_exemption(tmp_path):
    from bktstr.services.research_protocol import record_inspection
    _, request, exp = archive_fixture(tmp_path / 'source')
    source = ExperimentStore(tmp_path / 'source')
    record_inspection(ResearchCatalog(source), symbols=['SPY'], start=request['start'], end=request['end'],
        artifact_id=exp, actor='original-owner', reason='original local review', _protocol_id='conflicting-protocol')
    bundle = export_bundle(source)
    original = bundle['tables']['research_exposures'][0]
    main = ExperimentStore(tmp_path / 'main')
    preserve_bundle(main, bundle)
    preserve_bundle(main, bundle)
    with main._connect() as db:
        rows = db.execute('SELECT * FROM research_exposures').fetchall()
    assert len(rows) == 1
    saved = rows[0]
    assert saved['id'] != original['id']
    assert saved['protocol_id'] == ''
    assert saved['artifact_id'] == 'archive:' + bundle['digest'] + ':' + exp
    for column in ('created_at', 'symbol', 'start', 'end', 'actor', 'reason'):
        assert saved[column] == original[column]
    assert load_archive(main, bundle['digest']) == bundle


def test_rerun_result_scope_is_exposed_when_original_snapshot_is_still_retained(tmp_path):
    from bktstr.research_ideas import canonical, digest
    from bktstr.services.research_transfer import import_bundle
    bundle, request, _ = archive_fixture(tmp_path / 'source')
    # A fresh rerun keeps the recipe application's identity but advances its test
    # window. Its newly acquired input may have expired; the original input stays.
    request.update(start='2026-08-18T13:30:00Z', end='2026-08-18T13:36:00Z', fresh_data=True)
    bundle['tables']['experiments'][0]['request_json'] = canonical(request)
    bundle['digest'] = digest({k: v for k, v in bundle.items() if k != 'digest'})
    main = ExperimentStore(tmp_path / 'main')
    import_bundle(main, bundle)
    scopes = export_bundle(main, inspect=True)['tables']['research_exposures']
    assert {row['start'] for row in scopes} == {'2026-08-17T13:30:00+00:00', '2026-08-18T13:30:00+00:00'}


def test_uncommitted_vault_file_is_invisible_and_retry_registers_exposure(tmp_path, monkeypatch):
    from bktstr.services import research_vault
    from bktstr.services.research_protocol import record_inspection
    _, request, exp = archive_fixture(tmp_path / 'source')
    source = ExperimentStore(tmp_path / 'source')
    record_inspection(ResearchCatalog(source), symbols=['SPY'], start=request['start'], end=request['end'],
        artifact_id=exp, actor='original-owner', reason='local review')
    bundle = export_bundle(source)
    main = ExperimentStore(tmp_path / 'main')
    original_write = research_vault.atomic_text

    def write_then_fail(path, text):
        original_write(path, text)
        raise OSError('simulated failure before catalog commit')

    monkeypatch.setattr(research_vault, 'atomic_text', write_then_fail)
    with pytest.raises(OSError, match='before catalog commit'):
        preserve_bundle(main, bundle)
    assert (main.root / 'research' / 'archives' / (bundle['digest'] + '.json')).exists()
    assert list_archives(main) == []
    with pytest.raises(ValueError, match='registered'):
        load_archive(main, bundle['digest'])
    with main._connect() as db:
        assert db.execute('SELECT count(*) FROM research_exposures').fetchone()[0] == 0
    monkeypatch.setattr(research_vault, 'atomic_text', original_write)
    preserve_bundle(main, bundle)
    assert len(list_archives(main)) == 1
    assert load_archive(main, bundle['digest']) == bundle
    with main._connect() as db:
        assert db.execute('SELECT count(*) FROM research_exposures').fetchone()[0] == 1
