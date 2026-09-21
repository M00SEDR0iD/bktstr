import json
from pathlib import Path
import pytest
from test_configured_research import configured


def policy_doc(**patch):
    recipe = json.loads(Path('examples/strategies/macro-context-v1.json').read_text())
    recipe.pop('instruments')
    recipe.pop('evaluation')
    return dict(id='policy', version='1.0.0', recipe=recipe,
                rationale='Exploratory toy policy', limitations='Synthetic inputs; no edge claim') | patch


def test_policy_rebinding_preserves_recipe_and_compiles(tmp_path):
    from bktstr.idea_resolution import bind_policy
    store, catalog, request = configured(tmp_path)
    policy = catalog.register('policy', policy_doc())
    app = catalog.require(request['application'])
    manifest = bind_policy(policy, app, (request['start'], request['end']))
    assert manifest.document['instruments']['subject'] == 'SPY'
    assert manifest.document['entry']['rules'] == 'close.cross_above:vwap'


def test_modifier_conflicts_and_pinned_parent(tmp_path):
    from bktstr.idea_resolution import resolve_variant
    store, catalog, request = configured(tmp_path)
    refs = []
    for name, value in [('a', 'close.gt:1'), ('b', 'close.gt:2')]:
        refs.append(catalog.register('modifier', dict(id=name, version='1.0.0', kind='study',
            category='event', rationale='test', changes={'event_rules':value})).ref)
    variant = catalog.register('variant', dict(id='v', version='1.0.0', kind='study',
        idea=request['idea'], base=request['specification'], modifiers=refs, rationale='conflict'))
    with pytest.raises(ValueError, match='conflict'):
        resolve_variant(variant, catalog)


def test_policy_outcome_leak_is_rejected_by_compiler(tmp_path):
    from bktstr.idea_resolution import bind_policy
    store, catalog, request = configured(tmp_path)
    doc = policy_doc()
    doc['recipe']['entry']['rules'] = 'r2.gt:0'
    policy = catalog.register('policy', doc)
    with pytest.raises(ValueError):
        bind_policy(policy, catalog.require(request['application']), (request['start'], request['end']))


def test_durable_policy_uses_offline_engine(tmp_path):
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.services.experiments import ExperimentWorker
    store, catalog, request = configured(tmp_path)
    policy = catalog.register('policy', policy_doc())
    record = submit_research_run(store, request | {'operation':'configured_backtest', 'specification':policy.ref}, 'policy')
    worker = ExperimentWorker(store, research_operations(store))
    result = worker.run_one()
    worker.release_lease()
    assert result.status == 'completed', result.error
    assert result.result['kind'] == 'configured_backtest'
    assert result.result['manifest']['digest']
    assert result.result['summary']['trades'] >= 1
