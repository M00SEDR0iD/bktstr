from fastapi.testclient import TestClient
from test_configured_research import configured


def test_idea_routes_auth_history_markdown_and_existing_polling(tmp_path, monkeypatch):
    monkeypatch.setenv('BKTSTR_API_KEY', 'test-research-key')
    from bktstr.api.app import create_app
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    record = submit_research_run(store, request, 'api')
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    worker.release_lease()
    app = create_app()
    app.state.experiment_store = store
    client = TestClient(app)
    assert client.get('/api/v1/ideas').status_code == 401
    headers = {'Authorization':'Bearer test-research-key'}
    response = client.get('/api/v1/ideas', headers=headers)
    assert response.status_code == 200
    assert response.json()[0]['id'] == request['idea']['id']
    assert client.get('/api/v1/ideas/vwap-reclaim/markdown', headers=headers).status_code == 200
    response = client.get('/api/v1/experiments/'+record.experiment_id, headers=headers)
    assert response.status_code == 200
    assert response.json()['operation'] == 'event_study'
    response = client.get('/api/v1/experiments?idea_id=vwap-reclaim', headers=headers)
    assert response.json()['items'][0]['experiment_id'] == record.experiment_id
    assert client.post('/api/v1/research/revisions/study', json={'bad':'value'}, headers=headers).status_code == 422
