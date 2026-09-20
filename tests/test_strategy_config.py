import asyncio
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from bktstr.strategy_config import compile_strategy, load_strategy
from bktstr.runtime import run_configured_strategy


def document():
    return json.loads(Path('examples/strategies/macro-context-v1.json').read_text())


def test_manifest_is_canonical_and_deeply_frozen():
    value = document()
    manifest = compile_strategy(value)
    assert compile_strategy(dict(reversed(list(value.items())))).digest == manifest.digest
    value['risk']['stop_pct'] = 9
    assert manifest.document['risk']['stop_pct'] == 1.0
    with pytest.raises(TypeError):
        manifest.document['risk']['stop_pct'] = 3
    with pytest.raises(FrozenInstanceError):
        manifest.digest = 'changed'
    assert load_strategy('examples/strategies/macro-context-v1.json') == manifest


@pytest.mark.parametrize('section,key,value', [
    ('risk', 'stop_pct', True), ('risk', 'max_hold_minutes', 1.5),
    ('risk', 'stop_pct', float('nan')), ('risk', 'position_size', -1),
    ('risk', 'unknown', 1), ('entry', 'rules', 'future_price.gt:0'),
    ('entry', 'rules', 'close.gt:nan'), ('session', 'entry_start_time', '25:00'),
    ('session', 'entry_start_time', '17:00'),
    ('model_policy', 'model', 'typesafe/jev-latest'),
    ('execution', 'version', 'latest'),
])
def test_invalid_documents_fail_before_provider(monkeypatch, section, key, value):
    import bktstr.runtime as runtime
    monkeypatch.setattr(runtime, 'cached_provider', lambda *a, **k: pytest.fail('provider accessed'))
    config = document()
    config[section][key] = value
    with pytest.raises((ValueError, TypeError)):
        asyncio.run(run_configured_strategy(config))


@pytest.mark.parametrize('section,key,value', [
    ('entry', 'rules', 'close.gt:100'), ('risk', 'stop_pct', 2),
    ('model_policy', 'question', 'A different question'),
    ('execution', 'version', '2.0.0'),
])
def test_substantive_changes_change_digest(section, key, value):
    config = document()
    original = compile_strategy(config)
    config[section][key] = value
    assert compile_strategy(config).digest != original.digest


def test_paper_limits_required_only_for_paper():
    config = document()
    compile_strategy(config)
    config['mode'] = 'paper'
    with pytest.raises(ValueError, match='paper_limits'):
        compile_strategy(config)


def test_unknown_root_and_unsupported_filter():
    config = document()
    config['typo'] = 1
    with pytest.raises(ValueError):
        compile_strategy(config)
    config.pop('typo')
    config['filters'] = [{'layer': 'macro', 'role': 'gate', 'rules': 'inflation.lt:3'}]
    with pytest.raises(ValueError):
        compile_strategy(config)


@pytest.mark.parametrize('version', ['01.0.0', '1.0.0-01', '1.0.0-alpha..one'])
def test_strict_semantic_versions(version):
    config = document()
    config['strategy_version'] = version
    with pytest.raises(ValueError, match='semantic version'):
        compile_strategy(config)


def test_duplicate_json_keys_rejected(tmp_path):
    path = tmp_path / 'invalid.json'
    path.write_text('{"risk": {}, "risk": {}}')
    with pytest.raises(ValueError, match='duplicate'):
        load_strategy(path)


def test_benchmark_dependencies_are_explicit():
    config = document()
    config['filters'] = [{'layer': 'regime', 'rules': 'relative_return20.gt:0'}]
    with pytest.raises(ValueError, match='benchmark'):
        compile_strategy(config)
    config['instruments']['benchmark'] = 'QQQ'
    assert compile_strategy(config).request.overrides['regime_rules'] == 'relative_return20.gt:0.0'


def test_daily_crossings_rejected_before_provider(monkeypatch):
    import bktstr.runtime as runtime
    monkeypatch.setattr(runtime, 'cached_provider', lambda *a, **k: pytest.fail('provider accessed'))
    config = document()
    config['filters'] = [{'layer': 'regime', 'rules': 'day_close.cross_above:day_sma20'}]
    with pytest.raises(ValueError, match='cross operators'):
        asyncio.run(run_configured_strategy(config))


@pytest.mark.parametrize('feature', ['execution', 'paper', 'model'])
def test_future_features_cannot_execute(monkeypatch, feature):
    import bktstr.runtime as runtime
    monkeypatch.setattr(runtime, 'cached_provider', lambda *a, **k: pytest.fail('provider accessed'))
    config = document()
    if feature == 'execution':
        config['execution']['version'] = '2.0.0'
    elif feature == 'model':
        config['model_policy'] = {'enabled': True, 'model': 'typesafe/jev-1.13', 'question': 'Risk on?'}
    else:
        config['mode'] = 'paper'
        config['paper_limits'] = {
            'duration_minutes': 60, 'position_limit': 1, 'gross_limit': 1000,
            'daily_loss_limit': 100, 'stale_after_seconds': 120,
            'model_budget': 0, 'end_policy': 'flatten',
        }
        compile_strategy(config)
    with pytest.raises(ValueError):
        asyncio.run(run_configured_strategy(config))


def test_regime_gate_controls_entries(monkeypatch, tmp_path):
    from bktstr.providers import MassiveProvider
    from tests.v05_fixtures import intraday_fixture, daily_fixture
    monkeypatch.setenv('MASSIVE_API_KEY', 'fixture')
    monkeypatch.setenv('BKTSTR_CACHE_DIR', str(tmp_path / 'raw'))
    monkeypatch.setenv('BKTSTR_DERIVED_CACHE_DIR', str(tmp_path / 'derived'))
    async def fetch(self, symbol, start, end, timeframe='1m'):
        return daily_fixture(start, end, 100, 0.1) if timeframe == '1d' else intraday_fixture()
    monkeypatch.setattr(MassiveProvider, 'fetch_bars', fetch)
    config = document()
    config['entry']['rules'] = 'close.gt:0'
    config['filters'] = [{'layer': 'regime', 'rules': 'day_close.gt:0'}]
    assert asyncio.run(run_configured_strategy(config)).trades
    config['filters'][0]['rules'] = 'day_close.lt:0'
    assert not asyncio.run(run_configured_strategy(config)).trades


@pytest.mark.parametrize('cache_enabled', [True, False])
def test_generic_runs_through_existing_engine(monkeypatch, tmp_path, cache_enabled):
    from bktstr.providers import MassiveProvider
    from tests.v05_fixtures import intraday_fixture
    from bktstr.strategies import baseline_strategy_definition
    baseline = baseline_strategy_definition()
    monkeypatch.setenv('MASSIVE_API_KEY', 'fixture')
    monkeypatch.setenv('BKTSTR_CACHE_DIR', str(tmp_path / 'raw'))
    monkeypatch.setenv('BKTSTR_DERIVED_CACHE_DIR', str(tmp_path / 'derived'))
    monkeypatch.setenv('BKTSTR_DERIVED_CACHE_ENABLED', str(cache_enabled).lower())
    async def fetch(*args, **kwargs):
        return intraday_fixture()
    monkeypatch.setattr(MassiveProvider, 'fetch_bars', fetch)
    config = document()
    config['entry']['rules'] = 'close.gt:0'
    config['risk']['max_hold_minutes'] = 1
    result = asyncio.run(run_configured_strategy(config))
    assert result.trades
    assert result.resolved_strategy.strategy_id == 'bktstr.minute-strategy'
    assert result.provenance['strategy_manifest']['digest'] == compile_strategy(config).digest
    with pytest.raises(TypeError):
        result.provenance['strategy_manifest']['document']['risk']['stop_pct'] = 99
    assert baseline_strategy_definition() == baseline
