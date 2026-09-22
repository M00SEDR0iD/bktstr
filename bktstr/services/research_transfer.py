"""Bounded, merge-safe transfer of research records and content-addressed inputs.

Only the fixed schema below is accepted. SQL, filesystem paths, leases, generated
reports, and duplicate experiment generations never travel in an archive.
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from uuid import uuid4

from ..dataset_snapshots import atomic_text
from ..research_ideas import canonical, digest, parse_revision
from .research_store import ResearchCatalog
from .research_protocol import _initialize as initialize_protocols
from .research_storage import inventory

MAX_BUNDLE_BYTES = 64 * 1024 * 1024
SCHEMA = 'bktstr.research-transfer.v1'
# Table names and columns are code-owned; payload keys are never SQL identifiers.
TABLES = {
    'experiments': 'experiment_id operation status execution created_at started_at completed_at request_json result_json error_json provenance_json idempotency_key parent_experiment_id',
    'research_revisions': 'kind id version digest document',
    'research_assessments': 'id idea_id created_at document',
    'research_protocols': 'id digest document family',
    'research_attempts': 'logical_key protocol_id candidate application split replication experiment_id cancelled family semantic_candidate',
    'research_exposures': 'id created_at symbol start end artifact_id actor reason protocol_id',
    'research_reservations': 'protocol_id symbol start end',
    'research_families': 'id candidate_budget attempt_budget',
    'research_budget_amendments': 'protocol_id family document',
    'research_cancellations': 'experiment_id',
    'research_admission_failures': 'id protocol_id created_at document',
    'research_datasets': 'dataset created_at metadata recipe pinned evicted_at',
    'research_storage_events': 'created_at dataset action',
    'research_acquisitions': 'experiment_id application',
}
TABLES = {name: columns.split() for name, columns in TABLES.items()}
KEYS = {name: [columns[0]] for name, columns in TABLES.items()}
KEYS['research_revisions'] = ['kind', 'id', 'version']
KEYS['research_reservations'] = ['protocol_id', 'symbol', 'start', 'end']
KEYS['research_storage_events'] = TABLES['research_storage_events']


def _catalog(store):
    catalog = ResearchCatalog(store)
    initialize_protocols(catalog)
    inventory(catalog)
    return catalog


def _size(bundle, *, max_bytes=MAX_BUNDLE_BYTES):
    try:
        size = len(canonical(bundle).encode('utf-8'))
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError('archive must contain finite JSON values') from exc
    if max_bytes is not None and size > max_bytes:
        raise ValueError('archive exceeds 64 MiB size limit; use an offline backup for larger stores')


def _object_path(root, object_id):
    if not isinstance(object_id, str) or not re.fullmatch('[0-9a-f]{64}', object_id):
        raise ValueError('invalid archive object digest')
    path = root / (object_id + '.json')
    if root.is_symlink() or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('unsafe archive object path')
    return path


def _record_bundle_inspection(db, bundle):
    """Record raw-input/result access with no protocol exemption, in caller's transaction."""
    scopes = []
    retained = bundle['objects']['datasets']
    for dataset, document in retained.items():
        schedule = document['schedule']
        scopes.append((list(document['coverage']), schedule[0]['open'], schedule[-1]['close'], dataset))
    applications = {r['digest']: json.loads(r['document']) for r in bundle['tables']['research_revisions']
                    if r['kind'] == 'application'}
    for row in bundle['tables']['experiments']:
        if row['operation'] not in {'event_study', 'configured_backtest'}:
            continue
        request = json.loads(row['request_json'])
        app = applications.get(request.get('application', {}).get('digest'))
        if app is None:
            raise ValueError('archive research result is missing its application')
        # A fresh-data rerun can keep the original application's identity while
        # advancing dates. Its result scope is independent of retained inputs.
        scopes.append((list(app['instruments'].values()), request['start'], request['end'], row['experiment_id']))
    from ..dataset_snapshots import instant
    for symbols, start, end, artifact in scopes:
        for symbol in sorted(set(symbols)):
            db.execute('INSERT INTO research_exposures VALUES (?,?,?,?,?,?,?,?,?)',
                (uuid4().hex, datetime.now(timezone.utc).isoformat(), symbol,
                 instant(start).isoformat(), instant(end).isoformat(), artifact, 'owner', 'archive download', ''))


def export_bundle(store, *, max_bytes=MAX_BUNDLE_BYTES, inspect=False):
    """Export all terminal records under the writer boundary, without reports."""
    catalog = _catalog(store)
    with catalog.transaction() as db:
        if db.execute("SELECT 1 FROM experiments WHERE status NOT IN ('completed','failed') LIMIT 1").fetchone():
            raise ValueError('archive requires every experiment to be terminal')
        tables = {name: [dict(r) for r in db.execute(
            f'SELECT {",".join(columns)} FROM {name} ORDER BY {",".join(KEYS[name])}')]
            for name, columns in TABLES.items()}
        objects = {}
        for name, root in [('datasets', catalog.datasets), ('artifacts', catalog.artifacts)]:
            objects[name] = {}
            for candidate in sorted(root.glob('*.json')):
                path = _object_path(root, candidate.stem)
                value = json.loads(path.read_text(encoding='utf-8'))
                if digest(value) != candidate.stem:
                    raise ValueError('archive object digest mismatch')
                objects[name][candidate.stem] = value
        bundle = dict(schema=SCHEMA, tables=tables, objects=objects)
        if inspect:
            _record_bundle_inspection(db, bundle)
            tables['research_exposures'] = [dict(r) for r in db.execute(
                'SELECT ' + ','.join(TABLES['research_exposures']) + ' FROM research_exposures ORDER BY id')]
        bundle['digest'] = digest(bundle)
        _validate(bundle, max_bytes=max_bytes)
        return bundle


def _validate(bundle, *, max_bytes=MAX_BUNDLE_BYTES):
    _size(bundle, max_bytes=max_bytes)
    if not isinstance(bundle, dict) or set(bundle) != {'schema', 'tables', 'objects', 'digest'} or bundle['schema'] != SCHEMA:
        raise ValueError('unsupported archive schema')
    if digest({k: v for k, v in bundle.items() if k != 'digest'}) != bundle['digest']:
        raise ValueError('archive digest mismatch')
    if not isinstance(bundle['tables'], dict) or set(bundle['tables']) != set(TABLES):
        raise ValueError('archive table allowlist mismatch')
    for name, columns in TABLES.items():
        rows = bundle['tables'][name]
        if not isinstance(rows, list):
            raise ValueError('archive table rows must be lists')
        identities = set()
        for row in rows:
            if not isinstance(row, dict) or set(row) != set(columns):
                raise ValueError('archive column allowlist mismatch')
            if any(v is not None and not isinstance(v, (str, int, float)) for v in row.values()):
                raise ValueError('archive SQL values must be scalar')
            key = tuple(row[c] for c in KEYS[name])
            if any(v is None for v in key) or key in identities:
                raise ValueError('duplicate or missing archive identity')
            identities.add(key)
            integer_columns = {'cancelled', 'candidate_budget', 'attempt_budget', 'pinned'}
            for column in columns:
                if row[column] is not None and (
                    (column in integer_columns and type(row[column]) is not int) or
                    (column not in integer_columns and not isinstance(row[column], str))
                ):
                    raise ValueError('archive column type mismatch')
                if column.endswith('_json') or column in {'document', 'metadata', 'recipe'}:
                    if row[column] is not None:
                        try:
                            parsed = json.loads(row[column])
                            canonical(parsed)
                        except (ValueError, TypeError, RecursionError) as exc:
                            raise ValueError('invalid archive JSON column') from exc
            if name == 'experiments':
                if not isinstance(row['experiment_id'], str) or not re.fullmatch('exp_[0-9a-f]{32}', row['experiment_id']):
                    raise ValueError('invalid archive experiment identity')
                if row['status'] not in {'completed', 'failed'}:
                    raise ValueError('archive requires every experiment to be terminal')
                if row['execution'] not in {'sync', 'async', 'auto'} or not row['operation']:
                    raise ValueError('invalid archive experiment fields')
            elif name == 'research_revisions':
                try:
                    revision = parse_revision(row['kind'], json.loads(row['document']))
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError('invalid archive revision') from exc
                if (revision.id, revision.version, revision.digest) != (row['id'], row['version'], row['digest']):
                    raise ValueError('archive revision digest mismatch')
            elif name == 'research_protocols' and digest(json.loads(row['document'])) != row['digest']:
                raise ValueError('archive protocol digest mismatch')
            elif name == 'research_datasets':
                if not isinstance(row['dataset'], str) or not re.fullmatch('[0-9a-f]{64}', row['dataset']):
                    raise ValueError('invalid archive dataset identity')
                if row['pinned'] not in {0, 1} or not isinstance(json.loads(row['metadata']), dict):
                    raise ValueError('invalid archive dataset metadata')
    if not isinstance(bundle['objects'], dict) or set(bundle['objects']) != {'datasets', 'artifacts'}:
        raise ValueError('archive object allowlist mismatch')
    for objects in bundle['objects'].values():
        if not isinstance(objects, dict):
            raise ValueError('archive objects must be a mapping')
        for key, value in objects.items():
            if not isinstance(key, str) or not re.fullmatch('[0-9a-f]{64}', key) or digest(value) != key:
                raise ValueError('archive object digest mismatch')
    metadata = {row['dataset']: row for row in bundle['tables']['research_datasets']}
    for key, value in bundle['objects']['datasets'].items():
        if not isinstance(value, dict) or key not in metadata or json.loads(metadata[key]['metadata']) != {k: v for k, v in value.items() if k != 'bars'}:
            raise ValueError('archive dataset inventory mismatch')
    for key, row in metadata.items():
        if row['evicted_at'] is None and key not in bundle['objects']['datasets']:
            raise ValueError('archive is missing a retained dataset')
    for row in bundle['tables']['experiments']:
        result = json.loads(row['result_json']) if row['result_json'] else {}
        if not isinstance(row['request_json'], str) or not isinstance(result, dict) or not isinstance(json.loads(row['request_json']), dict):
            raise ValueError('archive experiment payload must be an object')
        for field in ('events_artifact', 'labels_artifact'):
            if field in result and (not isinstance(result[field], str) or result[field] not in bundle['objects']['artifacts']):
                raise ValueError('archive is missing a retained result artifact')


def _same(name, previous, incoming):
    ignored = {'idempotency_key'} if name == 'experiments' else set()
    # An existing server pin/eviction policy is an independent mutable lifecycle.
    # The acquisition recipe and immutable metadata must still match exactly.
    if name == 'research_datasets':
        ignored = {'created_at', 'pinned', 'evicted_at'}
    return all(previous[c] == incoming[c] for c in TABLES[name] if c not in ignored)


def import_bundle(store, bundle, *, max_bytes=MAX_BUNDLE_BYTES):
    """Merge an archive atomically; conflicting identities never overwrite data."""
    _validate(bundle, max_bytes=max_bytes)
    catalog = _catalog(store)
    added = {name: 0 for name in TABLES}
    created_paths = []
    try:
        with catalog.transaction() as db:
            pending = []
            for name, columns in TABLES.items():
                for row in bundle['tables'][name]:
                    previous = db.execute(f'SELECT {",".join(columns)} FROM {name} WHERE ' +
                        ' AND '.join(f'{c}=?' for c in KEYS[name]), tuple(row[c] for c in KEYS[name])).fetchone()
                    if previous is not None:
                        if not _same(name, previous, row):
                            raise ValueError(f'immutable archive identity collision in {name}')
                    else:
                        pending.append((name, row))
            files = []
            for name, root in [('datasets', catalog.datasets), ('artifacts', catalog.artifacts)]:
                for object_id, document in bundle['objects'][name].items():
                    path = _object_path(root, object_id)
                    text = canonical(document)
                    if path.exists():
                        if path.read_text(encoding='utf-8') != text:
                            raise ValueError('immutable archive object collision')
                    else:
                        files.append((path, text))
            for name, source in pending:
                row = dict(source)
                if name == 'experiments':
                    row['idempotency_key'] = 'archive:' + row['experiment_id']
                columns = TABLES[name]
                db.execute(f'INSERT INTO {name} ({",".join(columns)}) VALUES ({",".join("?" for _ in columns)})',
                           tuple(row[c] for c in columns))
                if name == 'experiments':
                    store._set_artifact_generation(db, row['experiment_id'])
                added[name] += 1
            # Write only after every collision has been checked. A crash can leave
            # orphan content-addressed files, never a partially committed catalog.
            for path, text in files:
                atomic_text(path, text)
                created_paths.append(path)
            for dataset in bundle['objects']['datasets']:
                db.execute('UPDATE research_datasets SET evicted_at=NULL WHERE dataset=?', (dataset,))
    except BaseException as exc:
        for path in created_paths:
            path.unlink(missing_ok=True)
        if isinstance(exc, sqlite3.IntegrityError):
            raise ValueError('archive identity collision or invalid row') from exc
        raise
    for row in bundle['tables']['experiments']:
        store._best_effort_publish(row['experiment_id'])
    return dict(digest=bundle['digest'], experiments_added=added['experiments'],
                rows_added=sum(added.values()), objects_added=len(created_paths), tables=added)
