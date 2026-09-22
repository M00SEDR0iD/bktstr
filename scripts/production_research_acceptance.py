"""Authenticated online-research acceptance; creates explicitly labelled test runs."""
import argparse
import json
import os
from pathlib import Path
import time
from uuid import uuid4
from urllib.parse import urlsplit

import httpx


def run(expected_commit, output):
    origin = os.environ.get('BKTSTR_BASE_URL', '').rstrip('/')
    parsed = urlsplit(origin)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('trusted HTTPS origin required')
    key = os.environ.get('BKTSTR_API_KEY')
    if not key:
        raise ValueError('credential helper required')
    with httpx.Client(base_url=origin, headers={'Authorization':'Bearer ' + key}, timeout=120, follow_redirects=False) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if not response.is_success:
                raise ValueError(f'{method} {path}: HTTP {response.status_code}')
            return response
        def get(path): return request('GET', path).json()
        def post(path, body, token=None):
            return request('POST', path, json=body, headers={'Idempotency-Key':token} if token else {}).json()
        def wait(experiment):
            for _ in range(150):
                result = get('/api/v1/experiments/' + experiment['experiment_id'])
                if result['status'] == 'failed':
                    raise ValueError('Acceptance research failed: ' + result['experiment_id'])
                if result['status'] == 'completed': return result
                time.sleep(2)
            raise ValueError('research timed out')
        health = get('/health')
        if health.get('git_commit') != expected_commit or health.get('version') != '0.7.0':
            raise ValueError('unexpected production version or commit')
        if not get('/api/v1/research/storage')['persistent_volume']:
            raise ValueError('production research is not on the persistent volume')
        suffix = 'acceptance-' + uuid4().hex[:12]
        acquisition = dict(provider='massive', symbols=['NVDA'], adjustment='adjusted',
            schedule_source='explicit acceptance window within 2026-08-17 XNYS regular session',
            schedule=[dict(date='2026-08-17', open='2026-08-17T13:30:00Z', close='2026-08-17T14:30:00Z')])
        dataset = post('/api/v1/research/datasets/acquire', acquisition)
        idea = post('/api/v1/ideas', dict(id=suffix, version='1.0.0', title='Production research acceptance',
            thesis='Acceptance check, not a trading hypothesis', mechanism='Exercise production persistence',
            falsification='Stored results or reports fail retrieval', applicability='Deployment verification only', roles=['subject']))
        app = post('/api/v1/research/revisions/application', dict(id=suffix,version='1.0.0',
            instruments={'subject':'NVDA'}, dataset=dataset['dataset']))
        study = post('/api/v1/research/revisions/study', dict(id=suffix,version='1.0.0',
            event_rules='close.cross_above:vwap', contexts=['close'], labels=[dict(id='r2',kind='return',minutes=2)]))
        body = dict(operation='event_study', idea=idea, specification=study, application=app,
                    start=acquisition['schedule'][0]['open'], end=acquisition['schedule'][0]['close'])
        first = wait(post('/api/v1/event-studies', body, suffix + '-study'))
        rerun_submission = post('/api/v1/experiments/' + first['experiment_id'] + '/rerun', {}, suffix + '-rerun')
        duplicate = post('/api/v1/experiments/' + first['experiment_id'] + '/rerun', {}, suffix + '-rerun')
        if duplicate['experiment_id'] != rerun_submission['experiment_id']:
            raise ValueError('rerun idempotency failed')
        rerun = wait(rerun_submission)
        if rerun['request'].get('rerun_of') != first['experiment_id'] or rerun['result']['dataset_metadata']['source'] != 'massive':
            raise ValueError('fresh rerun provenance missing')
        recipe = json.loads(Path('examples/strategies/macro-context-v1.json').read_text(encoding='utf-8'))
        recipe.pop('instruments'); recipe.pop('evaluation')
        policy = post('/api/v1/research/revisions/policy', dict(id=suffix, version='1.0.0', recipe=recipe,
            evidence=[first['experiment_id']], rationale='Deployment acceptance only', limitations='Not trading evidence'))
        policy_run = wait(post('/api/v1/configured-backtests', body | {'operation':'configured_backtest','specification':policy}, suffix+'-policy'))
        if not {'ev_r_per_trade','sharpe','max_drawdown_pct'} <= policy_run['result']['metrics'].keys():
            raise ValueError('policy metrics missing')
        html = request('GET', '/api/v1/ideas/' + suffix + '/html').text
        markdown = request('GET', '/api/v1/experiments/' + policy_run['experiment_id'] + '/markdown').text
        if policy_run['experiment_id'] not in html or 'EV (R/trade)' not in markdown:
            raise ValueError('saved report incomplete')
        if get('/api/v1/experiments/' + first['experiment_id'])['result'] != first['result']:
            raise ValueError('rerun changed original result')
        backup = post('/api/v1/research/storage/backup', {})
        report = dict(version=health['version'], git_commit=expected_commit, persistent_volume=True,
            idea=suffix, study=first['experiment_id'], fresh_rerun=rerun['experiment_id'],
            configured_backtest=policy_run['experiment_id'], source='massive', raw_cache_bypassed=True,
            saved_reports=True, original_unchanged=True, backup=backup['backup'])
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(report))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.expected_commit, args.output)
    except (ValueError, httpx.HTTPError) as exc:
        print(str(exc) if isinstance(exc, ValueError) else 'Acceptance connection failed')
        raise SystemExit(1)
