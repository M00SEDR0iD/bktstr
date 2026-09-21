import json
import re

from test_configured_research import configured


def test_visual_export_keeps_all_attempts_and_escapes_embedded_content(tmp_path):
    from bktstr.services.idea_reports import export_idea_html
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    idea = catalog.require(request['idea'], 'idea')
    injected = catalog.register('idea', idea.document | {'version':'1.0.1', 'title':'</script><script>alert(1)</script>'})
    request = request | {'idea':injected.ref}
    run = submit_research_run(store, request, 'visual')
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    worker.release_lease()
    from bktstr.services.research_archive import replay_research
    replay = replay_research(run.experiment_id, store)
    path = export_idea_html(idea.id, store)
    text = path.read_text(encoding='utf-8')
    assert path.suffix == '.html'
    assert 'alert(1)</script>' not in text
    payload = json.loads(re.search(r'<script id="idea-data" type="application/json">(.*?)</script>', text, re.S)[1])
    assert payload['revisions'][-1]['title'] == injected.document['title']
    assert payload['attempts'][0]['experiment_id'] == run.experiment_id
    assert payload['attempts'][0]['result']['kind'] == 'event_study'
    replay_row = next(a for a in payload['attempts'] if a['experiment_id'] == replay.experiment_id)
    assert replay_row['replay_of'] == run.experiment_id
    assert 'EV' in text and 'Sharpe' in text
    assert (catalog.reports / (idea.id + '-idea-card.html')).is_file()


def test_html_endpoint_is_authenticated_and_records_exposure(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from bktstr.api.app import create_app
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    record = submit_research_run(store, request, 'visual-api')
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    worker.release_lease()
    monkeypatch.setenv('BKTSTR_API_KEY', 'test-key')
    app = create_app()
    app.state.experiment_store = store
    client = TestClient(app)
    path = '/api/v1/ideas/vwap-reclaim/html'
    assert client.get(path).status_code == 401
    with catalog.transaction() as db:
        before = db.execute('SELECT count(*) FROM research_exposures').fetchone()[0]
    response = client.get(path, headers={'Authorization':'Bearer test-key'})
    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert "connect-src 'none'" in response.headers['content-security-policy']
    assert record.experiment_id in response.text
    with catalog.transaction() as db:
        assert db.execute('SELECT count(*) FROM research_exposures').fetchone()[0] > before


def test_visual_export_handles_untested_idea(tmp_path):
    from bktstr.services.idea_reports import export_idea_html
    store, catalog, request = configured(tmp_path)
    result = export_idea_html(request['idea']['id'], store).read_text(encoding='utf-8')
    assert 'No tests recorded' in result
