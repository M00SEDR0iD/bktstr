import json
import pytest


def test_full_research_demo_backup_restore_and_replay(tmp_path):
    from scripts.research_demo import run_demo
    from bktstr.services.research_archive import backup_research, restore_research, replay_research
    from bktstr.services.experiments import ExperimentStore
    result = run_demo(tmp_path / 'original')
    assert result['study']['status'] == result['policy']['status'] == 'completed'
    assert len(result['study']['cells']) == 6
    assert len(result['policy']['cells']) == 8
    assert result['card'].is_file()
    store = ExperimentStore(tmp_path / 'original')
    backup_research(store, tmp_path / 'backup')
    restored = restore_research(tmp_path / 'backup', tmp_path / 'restored')
    first = result['study']['cells'][0]['experiment_id']
    replay = replay_research(first, restored)
    original = restored.load_experiment(first)
    assert replay.status == 'completed'
    assert replay.result == original.result
    assert (tmp_path / 'restored' / 'research' / 'reports' / f'{first}-results.md').is_file()


def test_restore_rejects_tampered_bundle(tmp_path):
    from bktstr.services.research_archive import backup_research, restore_research
    from bktstr.services.experiments import ExperimentStore
    store = ExperimentStore(tmp_path / 'original')
    backup_research(store, tmp_path / 'backup')
    (tmp_path / 'backup' / 'experiments.sqlite3').write_bytes(b'broken')
    with pytest.raises(ValueError, match='hash'):
        restore_research(tmp_path / 'backup', tmp_path / 'restored')
