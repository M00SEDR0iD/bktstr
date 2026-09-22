import pytest
from test_configured_research import configured
from test_dataset_snapshots import sample_frames, sample_schedule


def recipe():
    return dict(provider='massive', symbols=['SPY'], schedule=sample_schedule(),
                schedule_source='test-fixture', adjustment='adjusted')


def test_rerun_fetches_fresh_and_preserves_original(tmp_path, monkeypatch):
    from bktstr.services.research_reruns import submit_rerun
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    from bktstr.providers import MassiveProvider
    store, catalog, request = configured(tmp_path)
    first = submit_research_run(store, request, 'original')
    ExperimentWorker(store, research_operations(store)).run_one()
    old = store.load_experiment(first.experiment_id)
    calls = []
    async def fetch(self, symbol, start, end, timeframe):
        calls.append(symbol)
        return sample_frames()[symbol] * 1.01
    monkeypatch.setenv('MASSIVE_API_KEY', 'test-not-a-secret')
    monkeypatch.setattr(MassiveProvider, 'fetch_bars', fetch)
    new = submit_rerun(first.experiment_id, store, 'rerun-1', acquisition=recipe())
    again = submit_rerun(first.experiment_id, store, 'rerun-1', acquisition=recipe())
    assert new.experiment_id == again.experiment_id
    assert not calls
    result = ExperimentWorker(store, research_operations(store)).run_one()
    assert result.status == 'completed', result.error
    assert calls == ['SPY']
    from bktstr.services.idea_reports import render_test_markdown
    (catalog.datasets / (old.provenance['dataset'] + '.json')).unlink()
    assert 'exact replay is unavailable' not in render_test_markdown(result.experiment_id, store)
    assert result.request['rerun_of'] == first.experiment_id
    assert result.provenance['dataset'] != old.provenance['dataset']
    assert store.load_experiment(first.experiment_id).result == old.result
    assert result.result['dataset_metadata']['source'] == 'massive'
    assert not result.request.get('protocol')
    from bktstr.services.research_archive import replay_research
    replayed = replay_research(result.experiment_id, store)
    assert replayed.status == 'completed', replayed.error
    assert replayed.result == result.result
    assert calls == ['SPY']


def test_unknown_uploaded_recipe_cannot_be_invented(tmp_path):
    from bktstr.services.research_reruns import submit_rerun
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    first = submit_research_run(store, request, 'original')
    ExperimentWorker(store, research_operations(store)).run_one()
    with pytest.raises(ValueError, match='acquisition recipe'):
        submit_rerun(first.experiment_id, store, 'missing')


def test_failed_fetch_is_a_saved_attempt(tmp_path, monkeypatch):
    from bktstr.services.research_reruns import submit_rerun
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    from bktstr.providers import MassiveProvider
    store, catalog, request = configured(tmp_path)
    first = submit_research_run(store, request, 'original')
    ExperimentWorker(store, research_operations(store)).run_one()
    async def fetch(*args):
        raise ValueError('provider unavailable')
    monkeypatch.setenv('MASSIVE_API_KEY', 'test-not-a-secret')
    monkeypatch.setattr(MassiveProvider, 'fetch_bars', fetch)
    run = submit_rerun(first.experiment_id, store, 'failed', acquisition=recipe())
    result = ExperimentWorker(store, research_operations(store)).run_one()
    assert result.experiment_id == run.experiment_id and result.status == 'failed'
    assert store.load_experiment(run.experiment_id).request['acquisition']['provider'] == 'massive'


def test_acquisition_application_and_checkpoint_commit_together(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from bktstr.services.research_reruns import submit_rerun, resolve_acquisition
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    from bktstr.services.research_store import ResearchCatalog
    from bktstr.providers import MassiveProvider
    store, catalog, request = configured(tmp_path)
    first = submit_research_run(store, request, 'original')
    ExperimentWorker(store, research_operations(store)).run_one()
    monkeypatch.setenv('MASSIVE_API_KEY', 'test-not-a-secret')
    calls = []
    async def fetch(self, symbol, *args):
        calls.append(symbol)
        return sample_frames()[symbol] * (1 + len(calls) / 100)
    monkeypatch.setattr(MassiveProvider, 'fetch_bars', fetch)
    run = submit_rerun(first.experiment_id, store, 'crash', acquisition=recipe())
    transaction = ResearchCatalog.transaction
    class Interrupted:
        def __init__(self, db): self.db = db
        def execute(self, sql, *args):
            if sql.startswith('INSERT INTO research_acquisitions'):
                raise RuntimeError('simulated crash before checkpoint')
            return self.db.execute(sql, *args)
    @contextmanager
    def interrupted(self):
        with transaction(self) as db:
            yield Interrupted(db)
    with monkeypatch.context() as patch:
        patch.setattr(ResearchCatalog, 'transaction', interrupted)
        with pytest.raises(RuntimeError, match='simulated crash'):
            resolve_acquisition(run, store)
    assert not [a for a in catalog.revisions('application') if a.id == 'acquired-' + run.experiment_id]
    resolved = resolve_acquisition(run, store)
    assert resolved.request['application']['id'] == 'acquired-' + run.experiment_id
