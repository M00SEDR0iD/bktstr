"""Portable backup/restore and explicit offline experiment replay."""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

from ..dataset_snapshots import atomic_text
from ..research_ideas import canonical
from .experiments import ExperimentStore, ExperimentWorker
from .configured_research import submit_research_run, research_operations
from .backtest import to_json_value


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup_research(store, destination):
    destination = Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(store.root.resolve()):
        raise ValueError('backup needs a new directory outside the research root')
    destination.mkdir(parents=True)
    from .research_store import ResearchCatalog
    # Reserve the SQLite writer boundary while snapshotting and copying. Publication
    # records its exposure in SQLite before making a report visible.
    with ResearchCatalog(store).transaction():
        with closing(store._connect()) as source, closing(sqlite3.connect(destination / 'experiments.sqlite3')) as target:
            source.backup(target)
        for name in ('artifacts', 'research'):
            root = store.root / name
            if root.exists():
                for path in root.rglob('*'):
                    if path.is_symlink():
                        raise ValueError('archive cannot contain symlinks')
                shutil.copytree(root, destination / name)
    manifest = {str(p.relative_to(destination)).replace('\\','/'): _hash(p)
                for p in destination.rglob('*') if p.is_file()}
    atomic_text(destination / 'backup-manifest.json', canonical(manifest))
    return destination


def restore_research(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if destination.exists() or destination.is_relative_to(source):
        raise ValueError('restore requires a new directory outside the backup')
    manifest = json.loads((source / 'backup-manifest.json').read_text(encoding='utf-8'))
    if 'experiments.sqlite3' not in manifest:
        raise ValueError('backup database missing')
    for name, expected in manifest.items():
        path = (source / name).resolve()
        target = (destination / name).resolve()
        if not path.is_relative_to(source) or not target.is_relative_to(destination) or not path.is_file():
            raise ValueError('invalid archive path')
        if _hash(path) != expected:
            raise ValueError('backup hash mismatch')
    destination.mkdir(parents=True)
    for name in manifest:
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / name, target)
    restored = ExperimentStore(destination)
    # A copied process lease has no owner in the restored archive.
    with closing(restored._connect()) as db:
        db.execute('DELETE FROM worker_leases')
    restored.recover_incomplete()
    return restored


def replay_research(experiment_id, store):
    original = store.load_experiment(experiment_id)
    if original.operation not in {'event_study', 'configured_backtest'}:
        raise ValueError('only pinned research operations can be replayed')
    request = to_json_value(original.request)
    if request.get('acquisition'):
        from .research_store import ResearchCatalog
        from .research_storage import initialize
        catalog = ResearchCatalog(store)
        initialize(catalog)
        with closing(store._connect()) as db:
            row = db.execute('SELECT application FROM research_acquisitions WHERE experiment_id=?', (experiment_id,)).fetchone()
        if row is None:
            raise ValueError('original acquisition did not finish; use a fresh rerun')
        request['application'] = json.loads(row[0])
        request.pop('acquisition')
    request['replay_of'] = experiment_id
    replay, _ = store.create_experiment(original.operation, request, execution='async',
        idempotency_key='replay:' + experiment_id, parent_experiment_id=experiment_id)
    if replay.status in {'completed','failed'}:
        return replay
    worker = ExperimentWorker(store, research_operations(store))
    owned, acquired = worker._ensure_lease()
    if not owned:
        return replay
    if acquired:
        store.recover_incomplete(worker.owner_id, now=worker.clock())
    stop, heartbeat = worker._start_heartbeat()
    try:
        return worker.run(replay.experiment_id)
    finally:
        stop.set()
        heartbeat.join()
        worker.release_lease()
