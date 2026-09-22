from datetime import datetime, timedelta, timezone
import pytest
from test_configured_research import configured


def test_eviction_keeps_metadata_results_and_pins(tmp_path):
    from bktstr.services.research_storage import inventory, set_pin, cleanup
    store, catalog, request = configured(tmp_path)
    items = inventory(catalog)
    assert len(items) == 1 and items[0]['pinned']
    dataset = items[0]['dataset']
    future = datetime.now(timezone.utc) + timedelta(days=40)
    assert cleanup(catalog, now=future)['datasets'] == []
    set_pin(catalog, dataset, False)
    preview = cleanup(catalog, now=future)
    assert preview['datasets'] == [dataset]
    assert (catalog.datasets / (dataset + '.json')).exists()
    cleanup(catalog, now=future, apply=True)
    assert not (catalog.datasets / (dataset + '.json')).exists()
    saved = inventory(catalog)[0]
    assert saved['metadata']['source'] == 'synthetic'
    assert saved['metadata']['schedule'] and not saved['available']
    assert catalog.require(request['application']).document['dataset'] == dataset


def test_pending_work_blocks_cleanup(tmp_path):
    from bktstr.services.research_storage import inventory, set_pin, cleanup
    from bktstr.services.configured_research import submit_research_run
    store, catalog, request = configured(tmp_path)
    dataset = inventory(catalog)[0]['dataset']
    set_pin(catalog, dataset, False)
    submit_research_run(store, request, 'queued')
    result = cleanup(catalog, apply=True, now=datetime.now(timezone.utc) + timedelta(days=40))
    assert result['blocked_by_pending_work']
    assert (catalog.datasets / (dataset + '.json')).exists()


def test_pin_missing_dataset_fails(tmp_path):
    from bktstr.services.research_storage import inventory, set_pin, cleanup
    store, catalog, _ = configured(tmp_path)
    dataset = inventory(catalog)[0]['dataset']
    set_pin(catalog, dataset, False)
    cleanup(catalog, apply=True, now=datetime.now(timezone.utc) + timedelta(days=40))
    with pytest.raises(ValueError, match='unavailable'):
        set_pin(catalog, dataset, True)


def test_report_without_snapshot_or_network(tmp_path):
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    from bktstr.services.research_storage import inventory, set_pin, cleanup
    from bktstr.services.idea_reports import render_idea_html
    store, catalog, request = configured(tmp_path)
    run = submit_research_run(store, request | {'analysis': {'label': 'r2'}}, 'report')
    ExperimentWorker(store, research_operations(store)).run_one()
    original = store.load_experiment(run.experiment_id).result
    dataset = inventory(catalog)[0]['dataset']
    set_pin(catalog, dataset, False)
    cleanup(catalog, apply=True, now=datetime.now(timezone.utc) + timedelta(days=40))
    assert 'synthetic' in render_idea_html(request['idea']['id'], store)
    assert store.load_experiment(run.experiment_id).result == original
    assert not list(catalog.reports.iterdir())
