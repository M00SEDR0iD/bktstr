"""Content-addressed OHLCV and explicit session schedules for offline research."""
from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
from uuid import uuid4

import numpy as np
import pandas as pd
from .research_ideas import canonical, digest

OHLCV = ['open', 'high', 'low', 'close', 'volume']


def build_identity():
    import platform
    import pydantic
    from importlib.metadata import version, PackageNotFoundError
    try:
        timezone_data = version('tzdata')
    except PackageNotFoundError:
        timezone_data = 'system-zoneinfo'
    root = Path(__file__).parent
    names = ['engine.py', 'rules.py', 'measurements.py', 'orchestrator.py', 'regime.py',
             'strategies.py', 'strategy_config.py', 'research_components.py', 'event_research.py',
             'runtime.py', 'dataset_snapshots.py', 'idea_resolution.py', 'research_ideas.py',
             'service.py', 'services/event_studies.py', 'services/configured_research.py',
             'services/research_protocol.py', 'services/research_archive.py', 'services/policy_metrics.py']
    return digest(dict(sources={name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                   for name in names if (root / name).exists()},
                   python=platform.python_version(), pandas=pd.__version__, numpy=np.__version__,
                   pydantic=pydantic.__version__, timezone_data=timezone_data))


def instant(value):
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        raise ValueError('timezone-aware timestamps required')
    return result.tz_convert('UTC')


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.' + uuid4().hex + '.tmp')
    try:
        with temporary.open('w', encoding='utf-8', newline='\n') as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def validate_schedule(schedule):
    normalized, previous = [], None
    for session in schedule:
        if set(session) != {'date', 'open', 'close'}:
            raise ValueError('session requires date, open, close')
        opened, closed = instant(session['open']), instant(session['close'])
        if opened >= closed or opened.second or closed.second or opened.microsecond or closed.microsecond:
            raise ValueError('invalid minute session schedule')
        if previous is not None and opened <= previous:
            raise ValueError('session schedules must be sorted and disjoint')
        day = date.fromisoformat(session['date'])
        if opened.tz_convert('America/New_York').date() != day or closed.tz_convert('America/New_York').date() != day:
            raise ValueError('session date mismatch')
        normalized.append(dict(date=day.isoformat(), open=opened.isoformat(), close=closed.isoformat()))
        previous = closed
    if not normalized:
        raise ValueError('explicit session schedule required')
    return normalized


@dataclass(frozen=True)
class DatasetSnapshot:
    canonical_json: str

    @property
    def document(self): return json.loads(self.canonical_json)

    @property
    def id(self): return digest(self.document)

    def frame(self, symbol):
        if symbol not in self.document['bars']:
            raise ValueError('instrument not in pinned dataset')
        rows = self.document['bars'][symbol]
        frame = pd.DataFrame(rows, columns=['timestamp', *OHLCV])
        frame.index = pd.DatetimeIndex(pd.to_datetime(frame.pop('timestamp'), utc=True))
        return frame.astype(float)


def freeze_dataset(frames, schedule, artifact_store, *, source, controlled=True,
                   adjustment='unadjusted', schedule_source='explicit-user-supplied'):
    if not source or not schedule_source or adjustment not in {'unadjusted', 'adjusted'}:
        raise ValueError('source, schedule provenance, and adjustment required')
    schedule = validate_schedule(schedule)
    expected = pd.DatetimeIndex([t for s in schedule for t in
        pd.date_range(s['open'], s['close'], freq='min', inclusive='left')])
    bars, coverage = {}, {}
    if not frames:
        raise ValueError('at least one instrument required')
    for symbol, original in sorted(frames.items()):
        if not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', symbol):
            raise ValueError('invalid symbol')
        if not isinstance(original.index, pd.DatetimeIndex) or original.index.tz is None:
            raise ValueError('aware bar-open timestamps required')
        frame = original.loc[:, OHLCV].copy()
        frame.index = frame.index.tz_convert('UTC')
        if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
            raise ValueError('duplicate or unsorted bars')
        if not np.isfinite(frame.to_numpy(dtype=float)).all() or (frame[OHLCV[:4]] <= 0).any().any() or (frame.volume < 0).any():
            raise ValueError('invalid OHLCV values')
        if (frame.high < frame[['open', 'close', 'low']].max(axis=1)).any() or (frame.low > frame[['open', 'close', 'high']].min(axis=1)).any():
            raise ValueError('inconsistent OHLC range')
        missing, extra = expected.difference(frame.index), frame.index.difference(expected)
        if len(extra) or (controlled and len(missing)):
            raise ValueError('dataset coverage differs from pinned session schedule')
        coverage[symbol] = dict(expected=len(expected), actual=len(frame), missing=len(missing),
                               missing_timestamps=[x.isoformat() for x in missing])
        bars[symbol] = [[t.isoformat(), *[float(x) for x in row]] for t, row in zip(frame.index, frame.to_numpy())]
    snapshot = DatasetSnapshot(canonical(dict(schema_version='1.0.0', source=source,
        adjustment=adjustment, timestamp_convention='bar_open', calendar='XNYS',
        timezone='America/New_York', timeframe='1m', currency='USD', warmup='scored_sessions_only', schedule=schedule,
        schedule_source=schedule_source, controlled=controlled, coverage=coverage,
        build=build_identity(), bars=bars)))
    destination = Path(artifact_store) / f'{snapshot.id}.json'
    if destination.exists() and destination.read_text(encoding='utf-8') != snapshot.canonical_json:
        raise ValueError('existing snapshot corruption')
    atomic_text(destination, snapshot.canonical_json)
    return snapshot


def load_snapshot(snapshot_id, artifact_store, *, verify_build=True):
    if not re.fullmatch(r'[0-9a-f]{64}', snapshot_id):
        raise ValueError('invalid snapshot digest')
    document = json.loads((Path(artifact_store) / f'{snapshot_id}.json').read_text(encoding='utf-8'))
    if digest(document) != snapshot_id:
        raise ValueError('snapshot digest mismatch')
    if verify_build and document['build'] != build_identity():
        raise ValueError('snapshot formula/build mismatch; replay requires original build')
    return DatasetSnapshot(canonical(document))


def validate_scope(snapshot, start, end, symbols):
    schedule = snapshot.document['schedule']
    opened = instant(schedule[0]['open'])
    closed = instant(schedule[-1]['close'])
    start = opened if start is None else instant(start)
    end = closed if end is None else instant(end)
    if start < opened or end > closed or start >= end:
        raise ValueError('requested scope is outside pinned dataset coverage')
    selected = [s for s in schedule if instant(s['open']) < end and instant(s['close']) > start]
    if not selected or any(s not in snapshot.document['bars'] for s in symbols):
        raise ValueError('requested scope has no pinned sessions or instrument')
    return start, end, selected


class SnapshotProvider:
    provider_name = 'frozen-snapshot'

    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.last_stats = {'snapshot_id': snapshot.id, 'offline': True}

    async def fetch_bars(self, symbol, start, end, timeframe):
        if timeframe != '1m':
            raise ValueError('requested timeframe not present in snapshot')
        days = [date.fromisoformat(s['date']) for s in self.snapshot.document['schedule']]
        if start < min(days) or end > max(days) or end < start:
            raise ValueError('requested dates outside pinned scope')
        frame = self.snapshot.frame(symbol)
        dates = frame.index.tz_convert('America/New_York').date
        return frame.loc[(dates >= start) & (dates <= end)].copy()


def snapshot_provider(snapshot_id, artifact_store):
    return SnapshotProvider(load_snapshot(snapshot_id, artifact_store))
