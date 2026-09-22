"""Durable dataset inventory and conservative, result-preserving input retention."""
from contextlib import closing
from datetime import datetime, timedelta, timezone
import json
import re

from ..dataset_snapshots import load_snapshot
from ..research_ideas import canonical


def initialize(catalog):
    with catalog.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_datasets (dataset TEXT PRIMARY KEY, created_at TEXT NOT NULL, metadata TEXT NOT NULL, recipe TEXT, pinned INTEGER NOT NULL, evicted_at TEXT)')
        db.execute('CREATE TABLE IF NOT EXISTS research_storage_events (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, dataset TEXT NOT NULL, action TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS research_acquisitions (experiment_id TEXT PRIMARY KEY, application TEXT NOT NULL)')


def remember_dataset(catalog, snapshot, recipe=None, *, db=None):
    """Save provenance without bars. Unknown/uploaded inputs are pinned by default."""
    metadata = {k: v for k, v in snapshot.document.items() if k != 'bars'}
    values = (snapshot.id, datetime.now(timezone.utc).isoformat(), canonical(metadata),
              canonical(recipe) if recipe else None, int(recipe is None))
    def save(connection):
        connection.execute('INSERT OR IGNORE INTO research_datasets VALUES (?,?,?,?,?,NULL)', values)
        connection.execute('UPDATE research_datasets SET created_at=? WHERE dataset=? AND evicted_at IS NOT NULL', (values[1], snapshot.id))
        connection.execute('UPDATE research_datasets SET evicted_at=NULL WHERE dataset=?', (snapshot.id,))
    if db is not None:
        save(db)
    else:
        initialize(catalog)
        with catalog.transaction() as connection:
            save(connection)
    return metadata


def _path(catalog, dataset):
    if not re.fullmatch('[0-9a-f]{64}', dataset):
        raise ValueError('invalid dataset digest')
    root = catalog.datasets
    path = root / (dataset + '.json')
    if root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(catalog.store.root.resolve()):
        raise ValueError('unsafe dataset path')
    return path


def inventory(catalog):
    initialize(catalog)
    # Additive migration: legacy snapshots retain their original content and pin.
    with catalog.transaction() as db:
        known = {r[0] for r in db.execute('SELECT dataset FROM research_datasets')}
        for path in catalog.datasets.glob('*.json'):
            if path.stem not in known:
                _path(catalog, path.stem)
                remember_dataset(catalog, load_snapshot(path.stem, catalog.datasets, verify_build=False), db=db)
        rows = db.execute('SELECT * FROM research_datasets ORDER BY created_at,dataset').fetchall()
    return [dict(dataset=r['dataset'], created_at=r['created_at'],
                 metadata=json.loads(r['metadata']), recipe=json.loads(r['recipe']) if r['recipe'] else None,
                 pinned=bool(r['pinned']), evicted_at=r['evicted_at'],
                 available=_path(catalog, r['dataset']).is_file(),
                 bytes=_path(catalog, r['dataset']).stat().st_size if _path(catalog, r['dataset']).is_file() else 0)
            for r in rows]


def dataset_metadata(catalog, dataset):
    initialize(catalog)
    with closing(catalog.store._connect()) as db:
        row = db.execute('SELECT metadata FROM research_datasets WHERE dataset=?', (dataset,)).fetchone()
    if row:
        return json.loads(row['metadata'])
    snapshot = load_snapshot(dataset, catalog.datasets, verify_build=False)
    return remember_dataset(catalog, snapshot)


def set_pin(catalog, dataset, pinned):
    inventory(catalog)
    with catalog.transaction() as db:
        row = db.execute('SELECT dataset FROM research_datasets WHERE dataset=?', (dataset,)).fetchone()
        if row is None or (pinned and not _path(catalog, dataset).is_file()):
            raise ValueError('dataset unavailable; fresh retrieval is not exact recovery')
        db.execute('UPDATE research_datasets SET pinned=? WHERE dataset=?', (int(pinned), dataset))
        db.execute('INSERT INTO research_storage_events(created_at,dataset,action) VALUES (?,?,?)',
                   (datetime.now(timezone.utc).isoformat(), dataset, 'pin' if pinned else 'unpin'))
    return dict(dataset=dataset, pinned=pinned)


def cleanup(catalog, *, apply=False, retention_days=30, now=None):
    if not 1 <= retention_days <= 3650:
        raise ValueError('retention_days must be between 1 and 3650')
    inventory(catalog)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('aware cleanup timestamp required')
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    with catalog.transaction() as db:
        # Conservative global barrier: no eviction while any work is pending.
        # The transaction also excludes snapshot publication and backup creation.
        pending = db.execute("SELECT count(*) FROM experiments WHERE status IN ('queued','running')").fetchone()[0]
        protected = set()
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'research_protocols' in tables:
            for row in db.execute('SELECT document FROM research_protocols'):
                for ref in json.loads(row[0])['applications']:
                    app = db.execute("SELECT document FROM research_revisions WHERE kind='application' AND digest=?", (ref['digest'],)).fetchone()
                    if app:
                        protected.add(json.loads(app[0])['dataset'])
        candidates = [] if pending else [r['dataset'] for r in db.execute(
            'SELECT dataset FROM research_datasets WHERE pinned=0 AND created_at<? AND evicted_at IS NULL ORDER BY dataset', (cutoff,))
            if r['dataset'] not in protected and _path(catalog, r['dataset']).is_file()]
        bytes_removed = sum(_path(catalog, x).stat().st_size for x in candidates)
        if apply:
            for dataset in candidates:
                _path(catalog, dataset).unlink(missing_ok=True)
                db.execute('UPDATE research_datasets SET evicted_at=? WHERE dataset=?', (now.isoformat(), dataset))
                db.execute('INSERT INTO research_storage_events(created_at,dataset,action) VALUES (?,?,?)',
                           (now.isoformat(), dataset, 'evict-input'))
        return dict(dry_run=not apply, datasets=candidates, bytes=bytes_removed,
                    blocked_by_pending_work=bool(pending), protected_by_protocol=sorted(protected),
                    results_deleted=0)
