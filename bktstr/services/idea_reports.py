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
from .policy_metrics import HEADLINE_METRICS


def _text(value):
    return html.escape(str(value)).replace('|', '\\|').replace('\n', ' ')


def _display(value):
    if value is None:
        return 'Unavailable'
    if isinstance(value, float):
        return f'{value:.6g}'
    if isinstance(value, dict):
        return '; '.join(f'{_text(k).replace("_", " ")}: {_display(v)}' for k, v in value.items()) or 'None'
    if isinstance(value, list):
        return ', '.join(_display(v) for v in value)
    return _text(value)


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
            start=request['start'], end=request['end'], replay_of=request.get('replay_of'),
            rerun_of=request.get('rerun_of')))
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
        linked = [p['id'] for p in protocols if p['idea']['id'] == idea_id]
        blocked = [dict(protocol_id=r['protocol_id'], created_at=r['created_at'], **json.loads(r['document']))
                   for r in db.execute('SELECT * FROM research_admission_failures ORDER BY created_at,id') if r['protocol_id'] in linked]
        family_ids = {r['family'] for r in db.execute('SELECT * FROM research_protocols') if r['id'] in linked}
        families = []
        for family in sorted(family_ids):
            budget = dict(db.execute('SELECT * FROM research_families WHERE id=?', (family,)).fetchone())
            budget['attempts_used'] = db.execute('SELECT count(*) FROM research_attempts WHERE family=?', (family,)).fetchone()[0]
            budget['candidates_used'] = db.execute('SELECT count(DISTINCT semantic_candidate) FROM research_attempts WHERE family=?', (family,)).fetchone()[0]
            budget['amendments'] = [json.loads(r[0]) for r in db.execute('SELECT document FROM research_budget_amendments WHERE family=?', (family,))]
            families.append(budget)
    return dict(idea_id=idea_id, revisions=[x.document for x in revisions], variants=variants,
        modifiers=modifiers, attempts=evidence, blocked_admissions=blocked, assessments=catalog.assessments(idea_id),
        protocols=[p for p in protocols if p['idea']['id'] == idea_id],
        search_history=dict(attempts=len(evidence), specifications=len({x['specification']['digest'] for x in evidence}),
                            archive_exposure_events=exposures, research_families=families),
        limitations=['Counts include failed and repeated work; external/manual inspection must be disclosed.',
                     'Research associations and simulated trading profit are separate evidence.'])


def render_experiment_markdown(record, *, snapshot_available=None):
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
        f'Protocol: {_display(request.get("protocol", "Uncontrolled exploration"))}', '']
    if result.get('kind') == 'configured_backtest':
        objective = ('Primary objective: net EV in R/trade.' if result.get('metric_definitions')
                     else 'Historical result: original objective retained; current R-based metrics were not recorded.')
        headline = ['## Primary outcomes', '', objective, '',
                    '| Metric | Result |', '| --- | --- |']
        for key, label in HEADLINE_METRICS:
            headline.append(f'| {label} | {_display(result.get("metrics", {}).get(key))} |')
        headline += ['', f'Trades: {result.get("metrics", {}).get("trade_count", result["summary"].get("trades"))}. '
                      f'Scored sessions: {_display(result.get("metrics", {}).get("sessions"))}.', '',
                      'R is initial planned stop risk. Net results include modeled slippage; commissions and borrow fees are not modeled.', '',
                      'Drawdown samples minute-close marked equity. Sharpe uses all scored daily returns, 252 sessions/year and a zero risk-free rate.', '',
                      'Historical results without this metric definition remain unavailable; they are not recalculated silently.', '']
        for key, reason in result.get('metric_unavailable_reasons', {}).items():
            headline += [f'- {_text(key)} unavailable: {_text(reason)}']
        headline += ['']
        at = lines.index('## What was tested')
        lines[at:at] = headline
    if request.get('replay_of'):
        lines += [f'Exact replay of {_text(request["replay_of"])}. This is not an independent final test.', '']
    if request.get('rerun_of'):
        lines += [f'Fresh-data rerun of {_text(request["rerun_of"])}. Original results remain unchanged.', '']
    if record.error:
        lines += ['## Failure or cancellation', '', _text(record.error['message']), '']
    if result.get('kind') == 'event_study':
        lines += ['## Observations', '', 'Forward observations, not executable trading profit.', '',
                  f'Eligible events: {result["event_count"]}', '']
        analysis = result.get('analysis')
        if analysis:
            lines += ['| Measure | Result |', '| --- | --- |']
            for key in ('primary_label', 'usable', 'sessions', 'blocks', 'mean', 'median', 'interval', 'uncertainty_status', 'context_difference', 'censored'):
                label = key.replace('_', ' ').capitalize()
                if key in {'mean', 'median'}:
                    label += ' (%)'
                if key == 'interval':
                    label = 'Mean interval (%)'
                lines.append(f'| {label} | {_display(analysis.get(key))} |')
            lines += ['', 'Percent outcomes use the event close as reference. Confidence intervals do not establish profitability.', '']
        lines += ['### Exact study definition', '', '```json', json.dumps(result['study'], indent=2), '```', '']
    elif result.get('kind') == 'configured_backtest':
        lines += ['## Supporting engine summary', '',
                  'Legacy engine drawdown below uses closed trades and a negative sign. Use the marked-equity maximum drawdown above for new comparisons.', '',
                  '| Measure | Result |', '| --- | --- |']
        for key, value in result['summary'].items():
            lines.append(f'| {_text(key).replace("_", " ").capitalize()} | {_display(value)} |')
        lines += ['', '### Metric definitions', '', '```json', json.dumps(result.get('metric_definitions', {}), indent=2), '```', '',
                  '### Policy and rationale', '', '```json', json.dumps(result['policy'], indent=2), '```', '']
    lines += ['## Limitations', '']
    for limitation in result.get('limitations', []) + result.get('analysis', {}).get('limitations', []):
        lines.append('- ' + _text(limitation))
    lines += ['- Synthetic demonstrations verify behavior; they are not market evidence.',
              '- All inspected results remain in the archive. Repeated tuning does not create a fresh holdout.', '',
              '## Replay and fresh-data reruns', '',
              'A fresh-data rerun retrieves data again and saves a new result. Viewing this report does not execute a test.', '',
              ('The pinned input snapshot is unavailable; exact replay is unavailable.' if snapshot_available is False else
               'Exact replay requires the pinned input snapshot and original numerical build. Snapshot presence alone does not verify replay compatibility.'), '',
              f'Dataset digest: {_text(provenance.get("dataset", "unavailable"))}', '',
              f'Numerical build: {_text(provenance.get("build", "unavailable"))}', '',
              '```json', json.dumps(request, indent=2), '```', '',
              '## Artifact references', '', '```json', json.dumps({k:v for k,v in result.items() if k.endswith('_artifact')}, indent=2), '```', '']
    return '\n'.join(lines)


def render_test_markdown(experiment_id, store):
    catalog = ResearchCatalog(store)
    record = store.load_experiment(experiment_id)
    if record.operation not in {'event_study', 'configured_backtest'}:
        raise ValueError('not an idea research experiment')
    inspect_experiment(catalog, record, reason='Markdown test report publication')
    dataset = (record.provenance or {}).get('dataset') or catalog.require(record.request['application'], 'application').document['dataset']
    return render_experiment_markdown(record, snapshot_available=(catalog.datasets / f'{dataset}.json').is_file())


def export_experiment_markdown(experiment_id, store):
    content = render_test_markdown(experiment_id, store)
    path = ResearchCatalog(store).reports / f'{experiment_id}-results.md'
    atomic_text(path, content)
    return path


def render_idea_markdown(idea_id, store, *, file_links=False):
    report = idea_report(idea_id, store)
    def test_link(experiment_id):
        return f'{experiment_id}-results.md' if file_links else f'/api/v1/experiments/{experiment_id}/markdown'
    lines = [f'# Idea card: {_text(idea_id)}', '', 'Status: research record; no live-trading approval.', '']
    lines += ['## Primary outcomes', '',
              'Iterate on net EV (R/trade). Review RR, Sharpe, maximum drawdown, sample size and held-out evidence alongside it. Higher EV alone does not promote a variant.', '',
              '| Test / specification | Instrument | Period | EV (R/trade) | EV ($/trade) | Planned RR | Realized RR (R) | Daily Sharpe | Max drawdown (%) | Max drawdown ($) | Trades |',
              '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for attempt in report['attempts']:
        result = attempt.get('result') or {}
        if result.get('kind') != 'configured_backtest':
            continue
        m = result.get('metrics', {})
        experiment_id = attempt['experiment_id']
        period = attempt['protocol']['split'] if attempt['protocol'] else 'exploratory'
        values = ' | '.join(_display(m.get(key)) for key, _ in HEADLINE_METRICS)
        name = f'{attempt["specification"]["id"]} @ {attempt["specification"]["version"]}'
        period += f' / {attempt["start"][:10]} to {attempt["end"][:10]}'
        lines.append(f'| [{_text(name)}]({test_link(experiment_id)}) | {_text(attempt["instruments"]["subject"])} | {_text(period)} | {values} | {_display(result["summary"].get("trades"))} |')
    lines += ['', 'Policy metrics require a trading simulation. Event studies retain forward-outcome statistics. Results stay separate by instrument and period; they are not a portfolio score.', '',
              'Drawdown uses minute-close marked equity. Sharpe uses daily returns including inactive sessions, 252 sessions/year, and zero risk-free return. RR reports reward divided by risk.', '']
    for idea in report['revisions']:
        lines += [f'## {_text(idea["title"])} / {_text(idea["version"])}', '',
            '### Thesis', '', _text(idea['thesis']), '', '### Proposed mechanism', '', _text(idea['mechanism']), '',
            '### Disproof criteria', '', _text(idea['falsification']), '', '### Applicability', '', _text(idea['applicability']), '']
    studies = [attempt['result']['study'] for attempt in report['attempts']
               if attempt.get('result') and attempt['result'].get('kind') == 'event_study']
    if studies:
        baseline = studies[0]
        lines += ['## Research specification', '',
                  f'First tested event rule: `{baseline["event_rules"]}`', '',
                  'Context: ' + ', '.join(_text(x) for x in baseline['contexts']) + '.', '',
                  '| Outcome | Measurement | Horizon |', '| --- | --- | --- |']
        for label in baseline['labels']:
            lines.append(f'| {_text(label["id"])} | {_text(label["kind"])} from event close | {label["minutes"]} minutes |')
        lines += ['', 'Future outcomes are separate from decision-time inputs. Missing and boundary-crossing outcomes remain visible in the test reports.', '']
    lines += ['## Categorized variations', '']
    for modifier in report['modifiers']:
        lines += [f'- {_text(modifier["kind"])} / {_text(modifier["category"])}: {_text(modifier["id"])}. {_text(modifier["rationale"])}']
        lines += ['', '```json', json.dumps(modifier['changes'], indent=2), '```', '']
    lines += ['', '| Variant | Kind | Based on | Modifiers |', '| --- | --- | --- | --- |']
    for variant in report['variants']:
        parent = variant['parent'] or variant['base']
        lines.append(f'| {_text(variant["id"])} | {_text(variant["kind"])} | {_text(parent["id"])} @ {_text(parent["version"])} | {", ".join(_text(x["id"]) for x in variant["modifiers"])} |')
    lines += ['', '## Tests and results', '', '| Test | Instrument | Kind | Specification | Period | Status |', '| --- | --- | --- | --- | --- | --- |']
    for attempt in report['attempts']:
        experiment_id = attempt['experiment_id']
        period = attempt['protocol']['split'] if attempt['protocol'] else 'exploratory'
        lines.append(f'| [{experiment_id[4:12]}]({test_link(experiment_id)}) | {_text(attempt["instruments"]["subject"])} | {_text(attempt["operation"])} | {_text(attempt["specification"]["id"])} | {_text(period)} | {_text(attempt["status"])} |')
    lines += ['', '## Blocked admissions', '']
    for blocked in report['blocked_admissions']:
        lines.append(f'- {_text(blocked["protocol_id"])} / {_text(blocked["split"])}: {_text(blocked["reason"])}')
    if not report['blocked_admissions']: lines.append('None recorded.')
    lines += ['', '## Assessment history', '']
    for assessment in report['assessments']:
        lines += [f'### {_text(assessment["author"])}', '', _text(assessment['conclusion']), '',
                  'Limitations: ' + _text(assessment['limitations']), '',
                  'Evidence: ' + ', '.join(f'[{x}]({test_link(x)})' for x in assessment['evidence']), '']
    if not report['assessments']: lines.append('No assessment recorded yet.')
    history = report['search_history']
    lines += ['', '## Search history', '',
              f'{history["attempts"]} recorded experiments; {history["specifications"]} distinct specification revisions.', '',
              '| Research family | Candidates used / budget | Attempts used / budget | Budget amendments |', '| --- | --- | --- | --- |']
    for family in history['research_families']:
        lines.append(f'| {_text(family["id"])} | {family["candidates_used"]} / {family["candidate_budget"]} | {family["attempts_used"]} / {family["attempt_budget"]} | {len(family["amendments"])} |')
        for amendment in family['amendments']:
            lines += ['', f'Budget amendment {_text(amendment["id"])}: {_text(amendment["amendment_reason"])}', '']
    lines += ['', 'A failed or inconclusive study remains part of this card. Results are specific to the tested inputs.', '']
    return '\n'.join(lines)


def export_idea_markdown(idea_id, store):
    content = render_idea_markdown(idea_id, store, file_links=True)
    # Explicit file exports retain the companion files targeted by relative links.
    cursor = None
    while True:
        page = list_research_experiments(store, idea_id=idea_id, limit=200, cursor=cursor)
        for attempt in page['items']:
            export_experiment_markdown(attempt['experiment_id'], store)
        cursor = page['next_cursor']
        if cursor is None:
            break
    path = ResearchCatalog(store).reports / f'{idea_id}-idea-card.md'
    atomic_text(path, content)
    return path


def publish_research_reports(store, record):
    """Compatibility hook: completion persists results; reports render on request."""


def render_idea_html(idea_id, store):
    """Self-contained human edition; canonical results and exposure rules are shared."""
    report = idea_report(idea_id, store)
    from ..dataset_snapshots import load_snapshot
    catalog = ResearchCatalog(store)
    sources = {}
    # Keep every attempt, but omit large trade arrays and duplicate runtime manifests.
    for attempt in report['attempts']:
        result = attempt.get('result')
        dataset = (result or {}).get('application', {}).get('dataset') or catalog.require(attempt['application'], 'application').document['dataset']
        saved_source = (result or {}).get('dataset_metadata', {}).get('source')
        if saved_source:
            sources[dataset] = saved_source
        if dataset not in sources:
            try:
                from .research_storage import dataset_metadata
                metadata = dataset_metadata(catalog, dataset)
            except (ValueError, FileNotFoundError):
                metadata = {}
            if metadata and metadata.get('source'):
                sources[dataset] = metadata['source']
        if dataset not in sources:
            try:
                sources[dataset] = load_snapshot(dataset, catalog.datasets, verify_build=False).document['source']
            except (ValueError, FileNotFoundError):
                sources[dataset] = 'Source metadata unavailable; inspect the saved provenance.'
        attempt['data_source'] = sources[dataset]
        attempt['input_snapshot_retained'] = (catalog.datasets / f'{dataset}.json').is_file()
        if result:
            attempt['result'] = {key: result[key] for key in (
                'kind', 'metrics', 'metric_definitions', 'metric_unavailable_reasons',
                'daily_equity', 'policy', 'study', 'analysis', 'event_count',
                'summary', 'limitations') if key in result}
    embedded = json.dumps(report, ensure_ascii=True, allow_nan=False)
    embedded = embedded.replace('&', '\\u0026').replace('<', '\\u003c').replace('>', '\\u003e')
    template = Path(__file__).with_name('idea_card.html').read_text(encoding='utf-8')
    return template.replace('__IDEA_REPORT_JSON__', embedded)


def export_idea_html(idea_id, store):
    content = render_idea_html(idea_id, store)
    path = ResearchCatalog(store).reports / f'{idea_id}-idea-card.html'
    atomic_text(path, content)
    return path
