"""Durable event-study and configured-policy operations sharing the worker."""
from typing import Literal
from pydantic import Field
from ..research_ideas import Object, Ref
from ..dataset_snapshots import load_snapshot, instant
from ..event_research import build_events, label_events
from .research_store import ResearchCatalog
from .backtest import to_json_value


class ResearchRunRequest(Object):
    operation: Literal['event_study', 'configured_backtest']
    idea: Ref
    specification: Ref
    application: Ref
    start: str
    end: str
    analysis: dict | None = None


def prepare_request(store, request):
    parsed = ResearchRunRequest.model_validate(request).model_dump(mode='json')
    if instant(parsed['start']) >= instant(parsed['end']):
        raise ValueError('start must precede end')
    parsed['start'], parsed['end'] = instant(parsed['start']).isoformat(), instant(parsed['end']).isoformat()
    catalog = ResearchCatalog(store)
    catalog.require(parsed['idea'], 'idea')
    spec = catalog.require(parsed['specification'])
    required = 'study' if parsed['operation'] == 'event_study' else 'policy'
    if spec.kind not in {required, 'variant'}:
        raise ValueError('operation/specification kind mismatch')
    catalog.require(parsed['application'], 'application')
    return parsed


def submit_research_run(store, request, idempotency_key):
    prepared = prepare_request(store, request)
    record, _ = store.create_experiment(prepared['operation'], prepared, execution='async',
                                       idempotency_key=idempotency_key)
    return record


def _execute_study(record, store):
    catalog = ResearchCatalog(store)
    request = to_json_value(record.request)
    study = catalog.require(request['specification'])
    if study.kind == 'variant':
        from ..idea_resolution import resolve_variant
        study = resolve_variant(study, catalog)
    app = catalog.require(request['application'], 'application')
    snapshot = load_snapshot(app.document['dataset'], catalog.datasets)
    events = build_events(study, app, snapshot, start=request['start'], end=request['end'])
    labels = label_events(events, study.document['labels'], snapshot)
    result = dict(kind='event_study', event_count=len(events.document['rows']),
        events_artifact=catalog.save_artifact(events.document), labels_artifact=catalog.save_artifact(labels.document),
        study=study.document, application=app.document,
        interpretation='Forward observations, not executable trading profit.')
    if request.get('analysis') is not None:
        from .event_studies import summarize_study
        result['analysis'] = summarize_study(events, labels, request['analysis'])
    provenance = dict(dataset=snapshot.id, build=snapshot.document['build'],
                      consumed_inputs=[snapshot.id, study.digest, app.digest], attached_evidence=[])
    return result, provenance


def research_operations(store):
    return {'event_study': lambda record: _execute_study(record, store)}
