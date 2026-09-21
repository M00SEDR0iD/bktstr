"""Frozen campaigns, transactional admission, and a shared data exposure ledger."""
from contextlib import closing
from datetime import datetime, timezone
import json
from typing import Literal
from uuid import uuid4

from pydantic import Field
from ..research_ideas import Definition, Object, Ref, Revision, canonical, digest
from ..dataset_snapshots import instant, load_snapshot
from .configured_research import prepare_request


class Split(Object):
    name: str = Field(min_length=1)
    stage: Literal['development', 'validation', 'final']
    start: str
    end: str


class Protocol(Definition):
    idea: Ref
    kind: Literal['study', 'backtest']
    baseline: Ref
    candidates: list[Ref] = Field(min_length=1)
    final_candidates: list[Ref] = Field(default_factory=list)
    applications: list[Ref] = Field(min_length=1)
    splits: list[Split] = Field(min_length=1)
    candidate_budget: int = Field(gt=0)
    attempt_budget: int = Field(gt=0)
    minimum_samples: int = Field(gt=0)
    stopping_rule: str = Field(min_length=1)
    primary_metric: Literal['mean', 'total_pnl_dollars']
    aggregation: Literal['equal_instrument']
    allowed_differences: list[str]
    analysis: dict | None = None


def _initialize(catalog):
    with catalog.transaction() as db:
        db.execute('CREATE TABLE IF NOT EXISTS research_protocols (id TEXT PRIMARY KEY, digest TEXT NOT NULL, document TEXT NOT NULL)')
        db.execute('CREATE TABLE IF NOT EXISTS research_attempts (logical_key TEXT PRIMARY KEY, protocol_id TEXT NOT NULL, candidate TEXT NOT NULL, application TEXT NOT NULL, split TEXT NOT NULL, replication TEXT NOT NULL, experiment_id TEXT UNIQUE NOT NULL, cancelled INTEGER NOT NULL DEFAULT 0)')
        db.execute('CREATE TABLE IF NOT EXISTS research_exposures (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, symbol TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, artifact_id TEXT NOT NULL, actor TEXT NOT NULL, reason TEXT NOT NULL)')


def register_protocol(document, catalog):
    _initialize(catalog)
    parsed = Protocol.model_validate(document).model_dump(mode='json')
    catalog.require(parsed['idea'], 'idea')
    candidates = [catalog.require(x) for x in parsed['candidates']]
    if len({x.digest for x in candidates}) != len(candidates) or len(candidates) > parsed['candidate_budget']:
        raise ValueError('duplicate candidates or candidate budget exceeded')
    if parsed['baseline'] not in parsed['candidates'] or any(x not in parsed['candidates'] for x in parsed['final_candidates']):
        raise ValueError('baseline and final candidates must be frozen candidates')
    expected_kind = 'study' if parsed['kind'] == 'study' else 'policy'
    for candidate in candidates:
        if candidate.kind != expected_kind and candidate.kind != 'variant':
            raise ValueError('candidate kind mismatch')
        if candidate.kind == 'variant' and (candidate.document['kind'] != expected_kind or candidate.document['idea'] != parsed['idea']):
            raise ValueError('variant belongs to another idea or kind')
    for ref in parsed['applications']:
        app = catalog.require(ref, 'application')
        snapshot = load_snapshot(app.document['dataset'], catalog.datasets)
        if not snapshot.document['controlled']:
            raise ValueError('controlled protocol requires complete dataset')
    previous_end, previous_stage, names = None, -1, set()
    stages = {'development': 0, 'validation': 1, 'final': 2}
    for split in parsed['splits']:
        start, end = instant(split['start']), instant(split['end'])
        if start >= end or (previous_end is not None and start < previous_end):
            raise ValueError('split overlap or invalid interval')
        if split['name'] in names or stages[split['stage']] < previous_stage:
            raise ValueError('split names and chronological stages must be distinct/ordered')
        if split['stage'] == 'final' and not parsed['final_candidates']:
            raise ValueError('final candidate must be frozen before final access')
        names.add(split['name'])
        split['start'], split['end'] = start.isoformat(), end.isoformat()
        previous_end, previous_stage = end, stages[split['stage']]
    if parsed['kind'] == 'study' and (parsed['analysis'] is None or parsed['primary_metric'] != 'mean'):
        raise ValueError('study analysis and primary mean required')
    if parsed['kind'] == 'backtest' and parsed['primary_metric'] != 'total_pnl_dollars':
        raise ValueError('backtest primary metric must be total_pnl_dollars')
    revision = Revision('protocol', canonical(parsed))
    with catalog.transaction() as db:
        previous = db.execute('SELECT digest FROM research_protocols WHERE id=?', (revision.id,)).fetchone()
        if previous and previous['digest'] != revision.digest:
            raise ValueError('immutable protocol; amendments need a new ID and retain history')
        db.execute('INSERT OR IGNORE INTO research_protocols VALUES (?,?,?)', (revision.id, revision.digest, revision.canonical_json))
    return revision


def get_protocol(protocol_id, catalog):
    _initialize(catalog)
    with closing(catalog.store._connect()) as db:
        row = db.execute('SELECT * FROM research_protocols WHERE id=?', (protocol_id,)).fetchone()
    if row is None:
        raise ValueError('unknown protocol')
    revision = Revision('protocol', row['document'])
    if revision.digest != row['digest']:
        raise ValueError('protocol digest mismatch')
    return revision


def _exposed(db, symbols, start, end):
    for symbol in symbols:
        for row in db.execute('SELECT start,end FROM research_exposures WHERE symbol=?', (symbol,)):
            if instant(row['start']) < instant(end) and instant(start) < instant(row['end']):
                return True
    return False


def record_inspection(catalog, *, symbols, start, end, artifact_id, actor, reason):
    _initialize(catalog)
    if not actor.strip() or not reason.strip() or instant(start) >= instant(end):
        raise ValueError('inspection requires actor, reason, valid scope')
    with catalog.transaction() as db:
        for symbol in sorted(set(symbols)):
            db.execute('INSERT INTO research_exposures VALUES (?,?,?,?,?,?,?,?)',
                (uuid4().hex, datetime.now(timezone.utc).isoformat(), symbol,
                 instant(start).isoformat(), instant(end).isoformat(), artifact_id, actor, reason))


def inspect_experiment(catalog, record, *, actor='owner', reason='result review'):
    """Call before every controlled result/label export, including legacy retrieval."""
    if record.operation not in {'event_study', 'configured_backtest'} or record.status not in {'completed', 'failed'}:
        return
    app = catalog.require(dict(record.request['application']), 'application')
    record_inspection(catalog, symbols=list(app.document['instruments'].values()),
        start=record.request['start'], end=record.request['end'], artifact_id=record.experiment_id,
        actor=actor, reason=reason)


def admit_attempt(protocol_id, variant_ref, application_ref, split, replication_id, catalog):
    protocol = get_protocol(protocol_id, catalog).document
    if variant_ref not in protocol['candidates'] or application_ref not in protocol['applications']:
        raise ValueError('candidate/application is not in frozen protocol')
    windows = [x for x in protocol['splits'] if x['name'] == split]
    if len(windows) != 1 or not replication_id:
        raise ValueError('unknown split or missing replication identity')
    window = windows[0]
    if window['stage'] == 'final' and variant_ref not in protocol['final_candidates']:
        raise ValueError('candidate is not frozen for final evaluation')
    app = catalog.require(application_ref, 'application')
    request = prepare_request(catalog.store, dict(operation='event_study' if protocol['kind'] == 'study' else 'configured_backtest',
        idea=protocol['idea'], specification=variant_ref, application=application_ref,
        start=window['start'], end=window['end'], analysis=protocol['analysis']))
    request['protocol'] = dict(id=protocol_id, split=split, stage=window['stage'], replication=replication_id)
    logical = digest(dict(protocol=protocol_id, candidate=variant_ref, application=application_ref,
                          split=split, replication=replication_id))
    with catalog.transaction() as db:
        previous = db.execute('SELECT experiment_id FROM research_attempts WHERE logical_key=?', (logical,)).fetchone()
        if previous:
            experiment_id = previous['experiment_id']
        else:
            used = db.execute('SELECT count(*) FROM research_attempts WHERE protocol_id=?', (protocol_id,)).fetchone()[0]
            if used >= protocol['attempt_budget']:
                raise ValueError('attempt budget exhausted')
            if window['stage'] == 'final' and _exposed(db, app.document['instruments'].values(), window['start'], window['end']):
                raise ValueError('final scope has already been exposed; cannot label untouched')
            experiment_id = 'exp_' + uuid4().hex
            db.execute('INSERT INTO experiments (experiment_id,operation,status,execution,created_at,request_json,idempotency_key) VALUES (?,?,?,?,?,?,?)',
                (experiment_id, request['operation'], 'queued', 'async', datetime.now(timezone.utc).isoformat(), canonical(request), 'research:' + logical))
            db.execute('INSERT INTO research_attempts VALUES (?,?,?,?,?,?,?,0)',
                (logical, protocol_id, variant_ref['digest'], application_ref['digest'], split, replication_id, experiment_id))
            catalog.store._set_artifact_generation(db, experiment_id)
    catalog.store._best_effort_publish(experiment_id)
    return catalog.store.load_experiment(experiment_id)


def cancel_attempt(experiment_id, catalog):
    _initialize(catalog)
    with catalog.transaction() as db:
        record = catalog.store._load_row(db, experiment_id)
        if record['status'] in {'completed', 'failed'}:
            return False
        changed = db.execute('UPDATE research_attempts SET cancelled=1 WHERE experiment_id=?', (experiment_id,)).rowcount
        return bool(changed)


def check_cancelled(experiment_id, catalog):
    _initialize(catalog)
    with closing(catalog.store._connect()) as db:
        row = db.execute('SELECT cancelled FROM research_attempts WHERE experiment_id=?', (experiment_id,)).fetchone()
    if row and row['cancelled']:
        from .experiments import ExperimentOperationError
        raise ExperimentOperationError('research_cancelled', 'Research attempt cancelled; budget remains consumed.')
