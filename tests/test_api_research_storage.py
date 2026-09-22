from fastapi.testclient import TestClient
from test_configured_research import configured
from test_research_reruns import recipe


def test_storage_and_rerun_api(tmp_path, monkeypatch):
    from bktstr.api.app import create_app
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    monkeypatch.setenv('BKTSTR_API_KEY', 'test-storage')
    store, catalog, request = configured(tmp_path)
    run = submit_research_run(store, request, 'original')
    ExperimentWorker(store, research_operations(store)).run_one()
    app = create_app()
    app.state.experiment_store = store
    client = TestClient(app)
    assert client.get('/api/v1/research/storage').status_code == 401
    headers = {'Authorization': 'Bearer test-storage', 'Idempotency-Key': 'new'}
    storage = client.get('/api/v1/research/storage', headers=headers).json()
    dataset = storage['datasets'][0]['dataset']
    assert storage['results_retention'] == 'permanent'
    response = client.post(f'/api/v1/research/datasets/{dataset}/pin', headers=headers, json={'pinned':False})
    assert response.status_code == 200
    assert client.post('/api/v1/research/storage/cleanup', headers=headers, json={}).json()['dry_run']
    response = client.post(f'/api/v1/experiments/{run.experiment_id}/rerun', headers=headers, json={'acquisition':recipe()})
    assert response.status_code == 202, response.text
    assert response.json()['request']['rerun_of'] == run.experiment_id
    assert response.json()['status'] == 'queued'


def test_archive_routes_preserve_history_and_render(tmp_path, monkeypatch):
    from bktstr.api.app import create_app
    from bktstr.services.research_transfer import export_bundle
    from bktstr.services.experiments import ExperimentStore
    monkeypatch.setenv('BKTSTR_API_KEY', 'test-storage')
    store, catalog, request = configured(tmp_path / 'source')
    bundle = export_bundle(store)
    app = create_app()
    app.state.experiment_store = ExperimentStore(tmp_path / 'target')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer test-storage'}
    assert client.post('/api/v1/research/archives', json=bundle).status_code == 401
    response = client.post('/api/v1/research/archives', json=bundle, headers=headers)
    assert response.status_code == 201, response.text
    archive_id = bundle['digest']
    assert client.get(f'/api/v1/research/archives/{archive_id}', headers=headers).json() == bundle
    assert client.get(f'/api/v1/research/archives/{archive_id}/ideas/{request["idea"]["id"]}/html', headers=headers).status_code == 200
    assert client.post('/api/v1/research/archive/import', json=bundle, headers=headers).status_code == 200
    exported = client.get('/api/v1/research/archive/export', headers=headers)
    assert exported.status_code == 200, exported.text
    assert exported.json()['tables']['research_exposures']
