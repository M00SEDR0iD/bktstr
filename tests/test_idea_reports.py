from test_configured_research import configured


def test_markdown_card_and_completed_test_report_are_saved(tmp_path):
    from bktstr.services.idea_reports import export_idea_markdown, export_experiment_markdown, list_research_experiments
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    record = submit_research_run(store, request | {'analysis':{'label':'r2'}}, 'report')
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    worker.release_lease()
    assert not list(catalog.reports.iterdir())
    card = export_idea_markdown(request['idea']['id'], store)
    report = export_experiment_markdown(record.experiment_id, store)
    assert card.is_file() and report.is_file()
    text = report.read_text(encoding='utf-8')
    for content in ('completed', 'r2', 'Replay', record.experiment_id, 'not executable trading profit'):
        assert content in text
    assert 'Disproof criteria' in card.read_text(encoding='utf-8')
    assert record.experiment_id in card.read_text(encoding='utf-8')
    history = list_research_experiments(store, idea_id=request['idea']['id'], limit=1)
    assert len(history['items']) == 1
    assert history['items'][0]['experiment_id'] == record.experiment_id


def test_pagination_and_failed_attempts_are_visible(tmp_path):
    from bktstr.services.idea_reports import list_research_experiments
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    for key in ('a','b'):
        submit_research_run(store, request, key)
    first = list_research_experiments(store, limit=1)
    second = list_research_experiments(store, limit=1, cursor=first['next_cursor'])
    assert first['items'][0]['experiment_id'] != second['items'][0]['experiment_id']


def test_render_reports_after_input_eviction_without_execution_or_files(tmp_path, monkeypatch):
    import json
    from bktstr.services.idea_reports import render_idea_html, render_idea_markdown, render_test_markdown
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    from bktstr import dataset_snapshots
    from bktstr.services.backtest import to_json_value
    store, catalog, request = configured(tmp_path)
    record = submit_research_run(store, request, 'on-demand')
    worker = ExperimentWorker(store, research_operations(store))
    worker.run_one()
    worker.release_lease()
    saved = store.load_experiment(record.experiment_id)
    result = to_json_value(saved.result) | {'dataset_metadata': {'source': 'synthetic retained source'}}
    with catalog.transaction() as db:
        db.execute('UPDATE experiments SET result_json=? WHERE experiment_id=?',
                   (json.dumps(result), record.experiment_id))
    for path in catalog.datasets.glob('*.json'):
        path.unlink()
    def forbidden(*args, **kwargs):
        raise AssertionError('Report rendering must not load input data or run a test')
    monkeypatch.setattr(dataset_snapshots, 'load_snapshot', forbidden)
    monkeypatch.setattr(ExperimentWorker, 'run_one', forbidden)
    html = render_idea_html(request['idea']['id'], store)
    assert 'synthetic retained source' in html
    assert record.experiment_id in html
    assert record.experiment_id in render_idea_markdown(request['idea']['id'], store)
    markdown = render_test_markdown(record.experiment_id, store)
    assert 'pinned input snapshot is unavailable' in markdown
    assert not list(catalog.reports.iterdir())
