"""Explicit provider acquisition and fresh, linked research attempts."""
import asyncio
from contextlib import closing
from dataclasses import replace
from datetime import date
import json
import os
import re
from typing import Literal

import pandas as pd
from pydantic import Field, model_validator

from ..dataset_snapshots import freeze_dataset, instant, validate_schedule
from ..research_ideas import Object, canonical
from .backtest import to_json_value
from .research_store import ResearchCatalog
from .research_storage import initialize, inventory, remember_dataset


class AcquisitionRecipe(Object):
    provider: Literal['massive'] = 'massive'
    symbols: list[str] = Field(min_length=1, max_length=2)
    timeframe: Literal['1m'] = '1m'
    adjustment: Literal['adjusted'] = 'adjusted'
    timezone: Literal['America/New_York'] = 'America/New_York'
    session: Literal['explicit'] = 'explicit'
    schedule: list[dict] = Field(min_length=1, max_length=520)
    schedule_source: str = Field(min_length=1, max_length=200)
    missing_data: Literal['reject', 'record'] = 'reject'

    @model_validator(mode='after')
    def validate_recipe(self):
        if len(set(self.symbols)) != len(self.symbols) or any(not re.fullmatch(r'[A-Z][A-Z0-9.\-]{0,14}', x) for x in self.symbols):
            raise ValueError('unique uppercase symbols required')
        object.__setattr__(self, 'schedule', validate_schedule(self.schedule))
        if (date.fromisoformat(self.schedule[-1]['date']) - date.fromisoformat(self.schedule[0]['date'])).days > 730:
            raise ValueError('acquisition range exceeds 730 days')
        return self


def acquire_dataset(catalog, recipe):
    recipe = AcquisitionRecipe.model_validate(recipe).model_dump(mode='json')
    from ..providers import MassiveProvider
    provider = MassiveProvider(os.getenv('MASSIVE_API_KEY', ''))
    first, last = date.fromisoformat(recipe['schedule'][0]['date']), date.fromisoformat(recipe['schedule'][-1]['date'])
    expected = pd.DatetimeIndex([t for s in recipe['schedule'] for t in
        pd.date_range(s['open'], s['close'], freq='min', inclusive='left')])
    async def fetch():
        frames = {}
        for symbol in recipe['symbols']:
            frame = await provider.fetch_bars(symbol, first, last, '1m')
            if frame.empty:
                frame.index = pd.DatetimeIndex([], tz='UTC')
            if frame.index.tz is None:
                raise ValueError('provider must return timezone-aware bars')
            frame.index = frame.index.tz_convert('UTC')
            frames[symbol] = frame.loc[frame.index.isin(expected)].copy()
        return frames
    frames = asyncio.run(fetch())  # Deliberately bypass CachedProvider.
    initialize(catalog)
    with catalog.transaction() as db:
        snapshot = freeze_dataset(frames, recipe['schedule'], catalog.datasets,
            source='massive', controlled=recipe['missing_data'] == 'reject',
            adjustment=recipe['adjustment'], schedule_source=recipe['schedule_source'])
        remember_dataset(catalog, snapshot, recipe, db=db)
    return snapshot


def submit_rerun(experiment_id, store, idempotency_key, *, acquisition=None, start=None, end=None):
    from .configured_research import prepare_request
    original = store.load_experiment(experiment_id)
    if original.operation not in {'event_study', 'configured_backtest'} or original.status not in {'completed','failed'}:
        raise ValueError('rerun requires a terminal research experiment')
    catalog = ResearchCatalog(store)
    original_request = to_json_value(original.request)
    if acquisition is None:
        acquisition = original_request.get('acquisition')
    if acquisition is None:
        app = catalog.require(original_request['application'], 'application')
        acquisition = next((x['recipe'] for x in inventory(catalog) if x['dataset'] == app.document['dataset']), None)
    if acquisition is None:
        raise ValueError('an explicit acquisition recipe is required for uploaded or unknown data')
    acquisition = AcquisitionRecipe.model_validate(acquisition).model_dump(mode='json')
    app = catalog.require(original_request['application'], 'application')
    if set(acquisition['symbols']) != set(app.document['instruments'].values()):
        raise ValueError('rerun instruments must match the original application')
    request = {k: original_request[k] for k in ('operation','idea','specification','application','start','end','analysis') if k in original_request}
    request['start'], request['end'] = start or request['start'], end or request['end']
    opened, closed = acquisition['schedule'][0]['open'], acquisition['schedule'][-1]['close']
    if instant(request['start']) < instant(opened) or instant(request['end']) > instant(closed):
        raise ValueError('rerun period outside acquisition schedule; supply explicit start/end')
    request = prepare_request(store, request)
    request.update(acquisition=acquisition, rerun_of=experiment_id,
                   source_protocol=original_request.get('protocol') or original_request.get('source_protocol'))
    # Fresh inference/data is exploratory, never an exact replay or a new holdout.
    record, _ = store.create_experiment(original.operation, request, execution='async',
        idempotency_key=idempotency_key, parent_experiment_id=experiment_id)
    return record


def resolve_acquisition(record, store):
    if not record.request.get('acquisition'):
        return record
    catalog = ResearchCatalog(store)
    initialize(catalog)
    with closing(store._connect()) as db:
        row = db.execute('SELECT application FROM research_acquisitions WHERE experiment_id=?', (record.experiment_id,)).fetchone()
    if row:
        reference = json.loads(row[0])
    else:
        snapshot = acquire_dataset(catalog, to_json_value(record.request['acquisition']))
        app = catalog.require(dict(record.request['application']), 'application')
        from ..research_ideas import parse_revision
        acquired = parse_revision('application', app.document | {
            'id': 'acquired-' + record.experiment_id, 'version': '1.0.0', 'dataset': snapshot.id})
        reference = acquired.ref
        with catalog.transaction() as db:
            db.execute('INSERT INTO research_revisions VALUES (?,?,?,?,?)',
                       ('application', acquired.id, acquired.version, acquired.digest, acquired.canonical_json))
            db.execute('INSERT INTO research_acquisitions VALUES (?,?)', (record.experiment_id, canonical(reference)))
    request = to_json_value(record.request)
    request['application'] = reference
    return replace(record, request=request)
