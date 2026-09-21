"""Position-independent event observations and separately materialized outcomes."""
from dataclasses import dataclass
import json
import math
import pandas as pd
from .dataset_snapshots import instant
from .engine import add_indicators
from .research_components import resolve_study
from .research_ideas import Revision, canonical, digest, Label
from .rules import evaluate_rules, parse_rules


@dataclass(frozen=True)
class EventDataset:
    canonical_json: str

    @property
    def document(self): return json.loads(self.canonical_json)

    @property
    def id(self): return digest(self.document)


@dataclass(frozen=True)
class LabelDataset:
    canonical_json: str

    @property
    def document(self): return json.loads(self.canonical_json)

    @property
    def id(self): return digest(self.document)


def build_events(study, application, snapshot, *, start=None, end=None):
    study = resolve_study(study)
    app = application.document if isinstance(application, Revision) else application
    symbol = app['instruments']['subject']
    frame = add_indicators(snapshot.frame(symbol))
    session = pd.Series(frame.index.date, index=frame.index)
    selected = evaluate_rules(frame, parse_rules(study.document['event_rules']), session)
    rows = []
    for timestamp, row in frame.loc[selected].iterrows():
        cutoff = instant(timestamp) + pd.Timedelta(minutes=1)
        if (start is not None and cutoff < instant(start)) or (end is not None and cutoff >= instant(end)):
            continue
        values, missing = {}, {}
        for column in sorted(set(study.document['contexts']) | {'close'}):
            value = float(row[column]) if pd.notna(row[column]) else None
            if value is None or not math.isfinite(value):
                value = None
                missing[column] = 'insufficient_history_or_missing_input'
            values[column] = value
        # Context/label changes keep the same candidate IDs when the detector agrees.
        identity = dict(dataset=snapshot.id, symbol=symbol, timestamp=timestamp.isoformat(),
                        detector=study.document['event_rules'], version=study.document['component_version'])
        rows.append(dict(id=digest(identity), symbol=symbol, session=str(timestamp.date()),
            bar_open=instant(timestamp).isoformat(), cutoff=cutoff.isoformat(), values=values,
            available_at={key: cutoff.isoformat() for key in values}, missing=missing))
    return EventDataset(canonical(dict(study=study.document, study_digest=study.digest,
        dataset=snapshot.id, symbol=symbol, start=start, end=end,
        coverage=snapshot.document['coverage'][symbol], rows=rows)))


def label_events(events, label_specs, outcome_inputs, *, end=None):
    if not isinstance(events, EventDataset):
        raise ValueError('causal event dataset required')
    snapshot = outcome_inputs
    if snapshot.id != events.document['dataset']:
        raise ValueError('outcome dataset mismatch')
    definitions = [Label.model_validate(x).model_dump(mode='json') for x in label_specs]
    frame = snapshot.frame(events.document['symbol'])
    schedule = {s['date']: instant(s['close']) for s in snapshot.document['schedule']}
    scored_end = end or events.document['end']
    rows = []
    for event in events.document['rows']:
        values, reasons, spans = {}, {}, {}
        cutoff = instant(event['cutoff'])
        reference = event['values']['close']
        for label in definitions:
            key = label['id']
            target = cutoff + pd.Timedelta(minutes=label['minutes'])
            spans[key] = target.isoformat()
            reason = None
            if scored_end and target > instant(scored_end):
                reason = 'split_boundary'
            elif target > schedule[event['session']]:
                reason = 'session_boundary'
            expected = pd.date_range(cutoff, target, freq='min', inclusive='left')
            if reason is None and not expected.isin(frame.index).all():
                reason = 'missing_price'
            if reason:
                values[key], reasons[key] = None, reason
                continue
            future = frame.loc[expected]
            if label['kind'] == 'return':
                result = (float(future.iloc[-1]['close']) / reference - 1) * 100
            elif label['kind'] == 'mfe':
                result = max(0., (float(future.high.max()) / reference - 1) * 100)
            else:
                result = min(0., (float(future.low.min()) / reference - 1) * 100)
            values[key] = result
        rows.append(dict(event_id=event['id'], session=event['session'], symbol=event['symbol'],
                         values=values, reasons=reasons, available_at=spans))
    return LabelDataset(canonical(dict(event_dataset=events.id, definitions=definitions, rows=rows,
        interpretation='Forward observations in percent; not executable trading returns.')))
