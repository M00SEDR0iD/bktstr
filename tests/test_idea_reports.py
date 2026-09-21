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
    assert (catalog.reports / f'{record.experiment_id}-results.md').is_file()
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
