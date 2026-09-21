"""Human-reviewable Markdown cards and test reports derived from durable evidence."""
from contextlib import closing
import base64
import html
import json
from pathlib import Path

from ..dataset_snapshots import atomic_text
from ..research_ideas import canonical
from .research_store import ResearchCatalog
from .research_protocol import inspect_experiment
from .backtest import to_json_value


def _text(value):
    return html.escape(str(value)).replace('|', '\\|').replace('\n', ' ')


def list_research_experiments(store, *, idea_id=None, kind=None, variant=None, instrument=None,
                              campaign=None, status=None, start=None, end=None, limit=50, cursor=None):
    if not 1 <= limit <= 200:
        raise ValueError('limit must be between 1 and 200')
    after = None
    if cursor:
        try:
            after = json.loads(base64.urlsafe_b64decode(cursor).decode())
            if not isinstance(after, list) or len(after) != 2 or not all(isinstance(x, str) for x in after):
                raise ValueError()
        except Exception as error:
            raise ValueError('invalid history cursor') from error
    with closing(store._connect()) as db:
        rows = db.execute("SELECT experiment_id,created_at,operation,status,request_json FROM experiments WHERE operation IN ('event_study','configured_backtest') ORDER BY created_at,experiment_id").fetchall()
    catalog = ResearchCatalog(store)
    matched = []
    for row in rows:
        key = [row['created_at'], row['experiment_id']]
        request = json.loads(row['request_json'])
        if after and key <= after: continue
        if idea_id and request['idea']['id'] != idea_id: continue
        if kind and row['operation'] != kind: continue
        if status and row['status'] != status: continue
        if variant and request['specification']['id'] != variant: continue
        if campaign and request.get('protocol', {}).get('id') != campaign: continue
        if start and row['created_at'] < start: continue
        if end and row['created_at'] >= end: continue
        app = catalog.require(request['application'], 'application')
        if instrument and instrument not in app.document['instruments'].values(): continue
        matched.append(dict(experiment_id=row['experiment_id'], created_at=row['created_at'],
            operation=row['operation'], status=row['status'], idea=request['idea'],
            specification=request['specification'], application=request['application'],
            instruments=app.document['instruments'], protocol=request.get('protocol'),
            start=request['start'], end=request['end']))
    items = matched[:limit]
    next_cursor = None
    if len(matched) > limit:
        last = items[-1]
        next_cursor = base64.urlsafe_b64encode(canonical([last['created_at'], last['experiment_id']]).encode()).decode()
    return dict(items=items, next_cursor=next_cursor)


def idea_report(idea_id, store):
    catalog = ResearchCatalog(store)
    revisions = [x for x in catalog.revisions('idea') if x.id == idea_id]
    if not revisions:
        raise ValueError('unknown idea')
    attempts, cursor = [], None
    while True:
        page = list_research_experiments(store, idea_id=idea_id, limit=200, cursor=cursor)
        attempts.extend(page['items'])
        cursor = page['next_cursor']
        if cursor is None: break
    evidence = []
    for attempt in attempts:
        record = store.load_experiment(attempt['experiment_id'])
        inspect_experiment(catalog, record, reason='idea report')
        evidence.append(dict(**attempt, result=to_json_value(record.result), error=to_json_value(record.error)))
    variants = [x.document for x in catalog.revisions('variant') if x.document['idea']['id'] == idea_id]
    modifiers = []
    for variant in variants:
        for ref in variant['modifiers']:
            doc = catalog.require(ref, 'modifier').document
            if doc not in modifiers: modifiers.append(doc)
    from .research_protocol import _initialize
    _initialize(catalog)
    with closing(store._connect()) as db:
        exposures = db.execute('SELECT count(*) FROM research_exposures').fetchone()[0]
        protocols = [json.loads(row[0]) for row in db.execute('SELECT document FROM research_protocols ORDER BY id')]
    return dict(idea_id=idea_id, revisions=[x.document for x in revisions], variants=variants,
        modifiers=modifiers, attempts=evidence, assessments=catalog.assessments(idea_id),
        protocols=[p for p in protocols if p['idea']['id'] == idea_id],
        search_history=dict(attempts=len(evidence), specifications=len({x['specification']['digest'] for x in evidence}),
                            archive_exposure_events=exposures),
        limitations=['Counts include failed and repeated work; external/manual inspection must be disclosed.',
                     'Research associations and simulated trading profit are separate evidence.'])


def render_experiment_markdown(record):
    result = to_json_value(record.result) or {}
    request = to_json_value(record.request)
    provenance = to_json_value(record.provenance) or {}
    lines = [f'# Test results: {_text(record.experiment_id)}', '',
        f'Status: **{record.status.value}**', '',
        f'Operation: {_text(record.operation)}', '',
        f'Idea: {_text(request["idea"]["id"])}', '',
        f'Period: {_text(request["start"])} to {_text(request["end"])}', '',
        '## What was tested', '',
        f'Specification: {_text(request["specification"]["id"])} at {_text(request["specification"]["version"])}', '',
        f'Application: {_text(request["application"]["id"])}', '',
        f'Protocol: {_text(request.get("protocol", "Uncontrolled exploration"))}', '']
    if record.error:
        lines += ['## Failure or cancellation', '', _text(record.error['message']), '']
    if result.get('kind') == 'event_study':
        lines += ['## Observations', '', 'Forward observations, not executable trading profit.', '',
                  f'Eligible events: {result["event_count"]}', '']
        analysis = result.get('analysis')
        if analysis:
            lines += ['| Measure | Result |', '| --- | --- |']
            for key in ('primary_label', 'usable', 'sessions', 'blocks', 'mean', 'median', 'interval', 'uncertainty_status', 'context_difference', 'censored'):
                lines.append(f'| {_text(key)} | {_text(analysis.get(key))} |')
            lines += ['', 'Percent outcomes use the event close as reference. Confidence intervals do not establish profitability.', '']
        lines += ['### Exact study definition', '', '```json', json.dumps(result['study'], indent=2), '```', '']
    elif result.get('kind') == 'configured_backtest':
        lines += ['## Simulated trading results', '', '| Measure | Result |', '| --- | --- |']
        for key, value in result['summary'].items():
            lines.append(f'| {_text(key)} | {_text(value)} |')
        lines += ['', '### Policy and rationale', '', '```json', json.dumps(result['policy'], indent=2), '```', '']
    lines += ['## Limitations', '']
    for limitation in result.get('limitations', []) + result.get('analysis', {}).get('limitations', []):
        lines.append('- ' + _text(limitation))
    lines += ['- Synthetic demonstrations verify behavior; they are not market evidence.',
              '- All inspected results remain in the archive. Repeated tuning does not create a fresh holdout.', '',
              '## Replay', '', 'Use the stored request with the pinned data and original numerical build. No network fallback is allowed.', '',
              f'Dataset digest: {_text(provenance.get("dataset", "unavailable"))}', '',
              f'Numerical build: {_text(provenance.get("build", "unavailable"))}', '',
              '```json', json.dumps(request, indent=2), '```', '',
              '## Artifact references', '', '```json', json.dumps({k:v for k,v in result.items() if k.endswith('_artifact')}, indent=2), '```', '']
    return '\n'.join(lines)


def export_experiment_markdown(experiment_id, store):
    catalog = ResearchCatalog(store)
    record = store.load_experiment(experiment_id)
    if record.operation not in {'event_study', 'configured_backtest'}:
        raise ValueError('not an idea research experiment')
    inspect_experiment(catalog, record, reason='Markdown test report publication')
    path = catalog.reports / f'{record.experiment_id}-results.md'
    atomic_text(path, render_experiment_markdown(record))
    return path


def export_idea_markdown(idea_id, store):
    catalog = ResearchCatalog(store)
    report = idea_report(idea_id, store)
    lines = [f'# Idea card: {_text(idea_id)}', '', 'Status: research record; no live-trading approval.', '']
    for idea in report['revisions']:
        lines += [f'## {_text(idea["title"])} / {_text(idea["version"])}', '',
            '### Thesis', '', _text(idea['thesis']), '', '### Proposed mechanism', '', _text(idea['mechanism']), '',
            '### Disproof criteria', '', _text(idea['falsification']), '', '### Applicability', '', _text(idea['applicability']), '']
    lines += ['## Categorized variations', '']
    for modifier in report['modifiers']:
        lines += [f'- {_text(modifier["kind"])} / {_text(modifier["category"])}: {_text(modifier["id"])}. {_text(modifier["rationale"])}']
        lines += ['', '```json', json.dumps(modifier['changes'], indent=2), '```', '']
    lines += ['', '```json', json.dumps(report['variants'], indent=2), '```', '',
              '## Tests and results', '', '| Experiment | Kind | Specification | Status |', '| --- | --- | --- | --- |']
    for attempt in report['attempts']:
        experiment_id = attempt['experiment_id']
        export_experiment_markdown(experiment_id, store)
        lines.append(f'| [{experiment_id}]({experiment_id}-results.md) | {_text(attempt["operation"])} | {_text(attempt["specification"]["id"])} | {_text(attempt["status"])} |')
    lines += ['', '## Assessment history', '', '```json', json.dumps(report['assessments'], indent=2), '```', '',
              '## Search history', '', '```json', json.dumps(report['search_history'], indent=2), '```', '',
              'A failed or inconclusive study remains part of this card. Results are specific to the tested inputs.', '']
    path = catalog.reports / f'{idea_id}-idea-card.md'
    atomic_text(path, '\n'.join(lines))
    return path


def publish_research_reports(store, record):
    if record.operation in {'event_study', 'configured_backtest'}:
        export_experiment_markdown(record.experiment_id, store)
        export_idea_markdown(record.request['idea']['id'], store)
