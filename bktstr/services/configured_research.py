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
    from .research_reruns import resolve_acquisition
    record = resolve_acquisition(record, store)
    catalog = ResearchCatalog(store)
    from .research_protocol import check_cancelled, validate_attempt_execution
    check_cancelled(record.experiment_id, catalog)
    validate_attempt_execution(record, catalog)
    request = to_json_value(record.request)
    study = catalog.require(request['specification'])
    if study.kind == 'variant':
        from ..idea_resolution import resolve_variant
        study = resolve_variant(study, catalog)
    app = catalog.require(request['application'], 'application')
    snapshot = load_snapshot(app.document['dataset'], catalog.datasets)
    from .research_storage import remember_dataset
    metadata = remember_dataset(catalog, snapshot)
    events = build_events(study, app, snapshot, start=request['start'], end=request['end'])
    labels = label_events(events, study.document['labels'], snapshot)
    result = dict(kind='event_study', dataset_metadata=metadata, event_count=len(events.document['rows']),
        events_artifact=catalog.save_artifact(events.document), labels_artifact=catalog.save_artifact(labels.document),
        study=study.document, application=app.document,
        interpretation='Forward observations, not executable trading profit.')
    if request.get('analysis') is not None:
        from .event_studies import summarize_study, fit_quantile_groups
        grouping = request['analysis'].get('grouping')
        if grouping and grouping.get('fitted_artifact'):
            from ..event_research import EventDataset
            from ..research_ideas import canonical
            training = EventDataset(canonical(catalog.load_artifact(grouping['fitted_artifact'])))
            if fit_quantile_groups(training, grouping['context'], grouping['quantiles']) != grouping:
                raise ValueError('fitted group provenance mismatch')
        result['analysis'] = summarize_study(events, labels, request['analysis'],
            stage=request.get('protocol', {}).get('stage', 'development'))
    check_cancelled(record.experiment_id, catalog)
    provenance = dict(dataset=snapshot.id, build=snapshot.document['build'],
                      consumed_inputs=[snapshot.id, study.digest, app.digest], attached_evidence=[])
    return result, provenance


def _execute_policy(record, store):
    from .research_reruns import resolve_acquisition
    record = resolve_acquisition(record, store)
    import asyncio
    from ..idea_resolution import resolve_variant, bind_policy
    from ..dataset_snapshots import SnapshotProvider, validate_scope
    from ..runtime import run_configured_strategy
    from .research_protocol import check_cancelled, validate_attempt_execution
    catalog = ResearchCatalog(store)
    check_cancelled(record.experiment_id, catalog)
    validate_attempt_execution(record, catalog)
    request = to_json_value(record.request)
    policy = catalog.require(request['specification'])
    if policy.kind == 'variant':
        policy = resolve_variant(policy, catalog)
    app = catalog.require(request['application'], 'application')
    manifest = bind_policy(policy, app, (request['start'], request['end']))
    for evidence_id in policy.document['evidence'] + policy.document['contrary_evidence']:
        evidence = store.load_experiment(evidence_id)
        if evidence.operation != 'event_study' or evidence.status != 'completed' or evidence.request['idea']['id'] != request['idea']['id']:
            raise ValueError('policy evidence must be a completed study for this idea')
    snapshot = load_snapshot(app.document['dataset'], catalog.datasets)
    from .research_storage import remember_dataset
    metadata = remember_dataset(catalog, snapshot)
    validate_scope(snapshot, request['start'], request['end'], app.document['instruments'].values())
    # Legacy execution uses complete sessions. Reject intra-session split boundaries.
    for session in snapshot.document['schedule']:
        if instant(session['open']) < instant(request['end']) and instant(session['close']) > instant(request['start']):
            if instant(session['open']) < instant(request['start']) or instant(session['close']) > instant(request['end']):
                raise ValueError('policy split must include complete pinned sessions')
    result = asyncio.run(run_configured_strategy(manifest, inputs=SnapshotProvider(snapshot)))
    check_cancelled(record.experiment_id, catalog)
    from .policy_metrics import policy_metrics
    outcomes = policy_metrics(trades=to_json_value(result.trades),
        bars=snapshot.frame(app.document['instruments']['subject']),
        schedule=[s for s in snapshot.document['schedule'] if instant(s['open']) >= instant(request['start']) and instant(s['close']) <= instant(request['end'])],
        risk=manifest.document['risk'], slippage_bps=manifest.document['execution']['slippage_bps'])
    payload = dict(kind='configured_backtest', dataset_metadata=metadata, policy=policy.document, application=app.document,
        manifest={'digest':manifest.digest, 'document':to_json_value(manifest.document)},
        summary=to_json_value(result.summary), trades=outcomes['trades'],
        metrics=outcomes['metrics'], metric_definitions=outcomes['definitions'],
        metric_unavailable_reasons=outcomes['unavailable_reasons'], daily_equity=outcomes['daily_equity'],
        event_mapping='unavailable: policy and event-study paths are separate; no implied one-to-one mapping',
        limitations=['Fixed-bps costs and next-bar execution; existing stop/gap assumptions remain.',
                     'Independent symbol simulation, not a shared-cash portfolio.'] + outcomes['limitations'])
    provenance = dict(dataset=snapshot.id, build=snapshot.document['build'],
        consumed_inputs=[snapshot.id, policy.digest, app.digest],
        attached_evidence=policy.document['evidence'] + policy.document['contrary_evidence'],
        runtime=to_json_value(result.provenance))
    return payload, provenance


def research_operations(store):
    return {'event_study': lambda record: _execute_study(record, store),
            'configured_backtest': lambda record: _execute_policy(record, store)}
