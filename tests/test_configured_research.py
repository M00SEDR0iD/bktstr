import pytest
from test_dataset_snapshots import sample_frames, sample_schedule
from test_research_components import study_doc
from test_research_ideas import idea_doc


def configured(tmp_path):
    from bktstr.services.experiments import ExperimentStore
    from bktstr.services.research_store import ResearchCatalog
    from bktstr.dataset_snapshots import freeze_dataset
    store = ExperimentStore(tmp_path)
    catalog = ResearchCatalog(store)
    idea = catalog.register('idea', idea_doc())
    study = catalog.register('study', study_doc(contexts=['close']))
    snap = freeze_dataset(sample_frames(), sample_schedule(), catalog.datasets, source='synthetic')
    app = catalog.register('application', dict(id='spy', version='1.0.0', instruments={'subject':'SPY'}, dataset=snap.id))
    request = dict(operation='event_study', idea=idea.ref, specification=study.ref,
                   application=app.ref, start='2026-08-17T13:30:00Z', end='2026-08-17T13:36:00Z')
    return store, catalog, request


def test_durable_study_survives_restart_and_retries(tmp_path):
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentStore, ExperimentWorker
    store, catalog, request = configured(tmp_path)
    record = submit_research_run(store, request, 'same')
    again = submit_research_run(store, request, 'same')
    assert record.experiment_id == again.experiment_id
    worker = ExperimentWorker(store, research_operations(store))
    result = worker.run_one()
    worker.release_lease()
    assert result.status == 'completed', result.error
    reloaded = ExperimentStore(tmp_path).load_experiment(record.experiment_id)
    assert reloaded.result['event_count'] == 2
    assert reloaded.result['events_artifact'] != reloaded.result['labels_artifact']


def test_conflicting_revision_and_corrupt_artifact_fail(tmp_path):
    from bktstr.services.research_store import ResearchCatalog
    store, catalog, request = configured(tmp_path)
    with pytest.raises(ValueError, match='immutable'):
        catalog.register('idea', idea_doc() | {'title':'changed'})
    artifact = catalog.save_artifact({'value': 2})
    (catalog.artifacts / f'{artifact}.json').write_text('{}')
    with pytest.raises(ValueError, match='digest'):
        catalog.load_artifact(artifact)
