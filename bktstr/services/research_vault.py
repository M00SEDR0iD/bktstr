"""Immutable historical archives whose native identities may conflict with live work.

Full directory backups include research/archives. The active-catalog JSON transfer
is intentionally nonrecursive; vault bundles are listed/downloaded individually.
"""
import json
import re
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from ..dataset_snapshots import atomic_text
from ..research_ideas import canonical, digest
from .experiments import ExperimentStore
from .idea_reports import render_idea_html, list_research_experiments
from .research_protocol import record_inspection, _initialize as initialize_protocols
from .research_store import ResearchCatalog
from .research_transfer import MAX_BUNDLE_BYTES, _validate, import_bundle, _record_bundle_inspection


class _RenderStore(ExperimentStore):
    """Close all SQLite handles before deleting the temporary store on Windows."""
    def __init__(self, root):
        self.connections = []
        try:
            super().__init__(root)
        except BaseException:
            self.close()
            raise

    def _connect(self):
        connection = super()._connect()
        self.connections.append(connection)
        return connection

    def close(self):
        for connection in self.connections:
            connection.close()
        self.connections.clear()


def _root(store):
    root = store.root / 'research' / 'archives'
    if root.is_symlink() or not root.resolve().is_relative_to(store.root.resolve()):
        raise ValueError('unsafe archive vault path')
    root.mkdir(parents=True, exist_ok=True)
    return root


def _path(store, archive_id):
    if not isinstance(archive_id, str) or not re.fullmatch('[0-9a-f]{64}', archive_id):
        raise ValueError('invalid archive digest')
    path = _root(store) / (archive_id + '.json')
    if path.is_symlink():
        raise ValueError('unsafe archive vault path')
    return path


def _summary(bundle):
    runs = bundle['tables']['experiments']
    times = sorted(row['created_at'] for row in runs)
    return dict(digest=bundle['digest'], experiments=len(runs),
        ideas=[dict(id=row['id'], version=row['version'], digest=row['digest'])
               for row in bundle['tables']['research_revisions'] if row['kind'] == 'idea'],
        first_run_at=times[0] if times else None, last_run_at=times[-1] if times else None,
        bytes=len(canonical(bundle).encode('utf-8')), mode='historical-read-only')


def _initialize_archives(store):
    catalog = ResearchCatalog(store)
    with catalog.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_archives (digest TEXT PRIMARY KEY)')
    return catalog


def preserve_bundle(store, bundle):
    """Preserve a verified bundle without merging or renaming native identities."""
    _validate(bundle)
    catalog = _initialize_archives(store)
    initialize_protocols(catalog)
    text = canonical(bundle)
    with catalog.transaction() as db:
        path = _path(store, bundle['digest'])
        if path.exists():
            if path.read_text(encoding='utf-8') != text:
                raise ValueError('immutable archive vault collision')
        for original in bundle['tables']['research_exposures']:
            exposure = dict(original,
                id=digest(dict(archive=bundle['digest'], exposure=original['id'])),
                artifact_id='archive:' + bundle['digest'] + ':' + original['artifact_id'],
                protocol_id='')
            columns = ('id', 'created_at', 'symbol', 'start', 'end', 'artifact_id', 'actor', 'reason', 'protocol_id')
            previous = db.execute('SELECT * FROM research_exposures WHERE id=?', (exposure['id'],)).fetchone()
            if previous and any(previous[key] != exposure[key] for key in columns):
                raise ValueError('immutable archived exposure collision')
            db.execute('INSERT OR IGNORE INTO research_exposures VALUES (?,?,?,?,?,?,?,?,?)',
                       tuple(exposure[key] for key in columns))
        if not path.exists():
            atomic_text(path, text)
        # Only the committed catalog makes a file visible. A crash before commit
        # leaves an inert orphan that a later preserve can safely register.
        db.execute('INSERT OR IGNORE INTO research_archives VALUES (?)', (bundle['digest'],))
    return _summary(bundle)


def load_archive(store, archive_id, *, inspect=False):
    path = _path(store, archive_id)
    _initialize_archives(store)
    with closing(store._connect()) as db:
        if db.execute('SELECT 1 FROM research_archives WHERE digest=?', (archive_id,)).fetchone() is None:
            raise ValueError('archive is not registered')
    if path.stat().st_size > MAX_BUNDLE_BYTES:
        raise ValueError('archive exceeds the 64 MiB transfer limit')
    bundle = json.loads(path.read_text(encoding='utf-8'))
    _validate(bundle)
    if bundle['digest'] != archive_id:
        raise ValueError('archive vault digest mismatch')
    if inspect:
        catalog = ResearchCatalog(store)
        initialize_protocols(catalog)
        with catalog.transaction() as db:
            _record_bundle_inspection(db, bundle)
    return bundle


def list_archives(store):
    _initialize_archives(store)
    with closing(store._connect()) as db:
        identities = [row[0] for row in db.execute('SELECT digest FROM research_archives ORDER BY digest')]
    return [_summary(load_archive(store, identity)) for identity in identities]


def render_archive_idea(store, archive_id, idea_id):
    """Render saved results in isolation, then persist exposures in the live ledger."""
    bundle = load_archive(store, archive_id)
    exposures = []
    with TemporaryDirectory(prefix='bktstr-vault-') as directory:
        isolated = _RenderStore(Path(directory))
        try:
            import_bundle(isolated, bundle)
            content = render_idea_html(idea_id, isolated)
            archive_catalog = ResearchCatalog(isolated)
            cursor = None
            while True:
                page = list_research_experiments(isolated, idea_id=idea_id, limit=200, cursor=cursor)
                for attempt in page['items']:
                    app = archive_catalog.require(attempt['application'], 'application')
                    exposures.append(dict(symbols=list(app.document['instruments'].values()),
                        start=attempt['start'], end=attempt['end'],
                        artifact_id='archive:' + archive_id + ':' + attempt['experiment_id']))
                cursor = page['next_cursor']
                if cursor is None:
                    break
        finally:
            isolated.close()
    catalog = ResearchCatalog(store)
    # Do not copy archived protocol IDs: a same-name live protocol must not gain
    # an exemption from exposure caused by viewing a different historical archive.
    for exposure in exposures:
        record_inspection(catalog, **exposure, actor='owner', reason='historical archive idea report')
    return content
