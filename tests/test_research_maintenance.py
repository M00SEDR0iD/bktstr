import pytest


def test_railway_requires_volume_root(monkeypatch, tmp_path):
    from bktstr.services.experiments import experiment_root
    monkeypatch.setenv('RAILWAY_ENVIRONMENT_ID', 'production-test')
    monkeypatch.delenv('RAILWAY_VOLUME_MOUNT_PATH', raising=False)
    monkeypatch.delenv('BKTSTR_EXPERIMENT_DIR', raising=False)
    with pytest.raises(RuntimeError, match='persistent'):
        experiment_root()
    monkeypatch.setenv('RAILWAY_VOLUME_MOUNT_PATH', str(tmp_path))
    assert experiment_root() == tmp_path / 'bktstr-experiments'
    monkeypatch.setenv('BKTSTR_EXPERIMENT_DIR', str(tmp_path.parent / 'ephemeral'))
    with pytest.raises(RuntimeError, match='volume'):
        experiment_root()


def test_maintenance_makes_restorable_server_backup(tmp_path):
    from test_configured_research import configured
    from bktstr.services.research_maintenance import maintain
    import gzip, json
    store, catalog, request = configured(tmp_path)
    result = maintain(store)
    assert result['backup']
    path = catalog.root / 'backups' / result['backup']
    with gzip.open(path, 'rt', encoding='utf-8') as stream:
        bundle = json.load(stream)
    assert bundle['tables']['research_revisions']
    from bktstr.services.research_transfer import import_bundle
    from bktstr.services.experiments import ExperimentStore
    from bktstr.services.research_store import ResearchCatalog
    restored = ExperimentStore(tmp_path / 'restored')
    import_bundle(restored, bundle)
    assert ResearchCatalog(restored).require(request['idea']).document == catalog.require(request['idea']).document
    assert maintain(store)['backup'] == result['backup']
