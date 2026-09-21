"""Offline, synthetic acceptance demonstration. No prices or profits are market evidence."""
import argparse
import json
from pathlib import Path
import shutil
from datetime import timedelta

import pandas as pd
import numpy as np

from bktstr.dataset_snapshots import freeze_dataset, atomic_text
from bktstr.services.experiments import ExperimentStore
from bktstr.services.research_store import ResearchCatalog
from bktstr.services.research_protocol import register_protocol, run_protocol
from bktstr.services.idea_reports import export_idea_markdown


def write_demo_reports(catalog, destination, study_results, policy_results, card):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in catalog.reports.glob('*.md'):
        shutil.copy2(path, destination / path.name)
    names = {r.digest:r.id for kind in ('study', 'policy', 'variant') for r in catalog.revisions(kind)}
    lines = ['# Synthetic research demonstration', '',
        'This demonstrates software behavior. Every price is synthetic; these results are not evidence of a trading edge.', '',
        '[Open the idea card](vwap-reclaim-idea-card.md)', '',
        f'Study campaign: {study_results["status"]}, {len(study_results["cells"])} attempts.', '',
        f'Policy campaign: {policy_results["status"]}, {len(policy_results["cells"])} attempts.', '',
        'Development, validation, and final sessions are chronological and disjoint.', '',
        'The two artificial instruments use scaled versions of the same prices. Matching results demonstrate consistent application, not independent market confirmation.', '',
        '## Study comparisons', '',
        'Differences are candidate minus baseline mean five-minute return, in percentage points. Intervals use session-block resampling and remain exploratory.', '',
        '| Variation | Instrument | Difference | Interval | Common / added / removed events |',
        '| --- | --- | --- | --- | --- |']
    for row in study_results['comparisons']:
        interval = 'Unavailable' if row['interval'] is None else ' to '.join(f'{v:.6f}' for v in row['interval'])
        lines.append(f'| {names[row["candidate"]]} | {row["symbol"]} | {row["effect"]:.6f} | {interval} | {row["common_events"]} / {row["added_events"]} / {row["removed_events"]} |')
    lines += ['', '## Policy comparisons', '',
        'Validation-period differences are candidate minus baseline simulated PnL in dollars, including the configured execution assumptions. Each instrument is tested independently.', '',
        '| Variation | Instrument | PnL difference ($) | Status |', '| --- | --- | --- | --- |']
    for row in policy_results['comparisons']:
        lines.append(f'| {names[row["candidate"]]} | {row["symbol"]} | {row["effect"]:.3f} | {row["status"]} |')
    lines += ['', '## Assessment', '',
        'The workflow completed and retained every declared attempt. These manufactured observations support no market conclusion. Review the linked test reports for exact rules, dates, assumptions, limitations, and replay references.', '']
    atomic_text(destination / 'README.md', '\n'.join(lines))
    return destination / card.name


def run_demo(root, reports=None):
    store = ExperimentStore(root)
    catalog = ResearchCatalog(store)
    repo = Path(__file__).resolve().parents[1]
    idea = catalog.register('idea', json.loads((repo / 'examples/ideas/vwap-continuation.json').read_text()))
    schedule, frames = [], {'SPY':[], 'QQQ':[]}
    days = pd.bdate_range('2026-08-03', periods=12)
    for day_number, day in enumerate(days):
        opened = pd.Timestamp(str(day.date()) + 'T13:30:00Z')
        index = pd.date_range(opened, periods=35, freq='min')
        schedule.append(dict(date=str(day.date()), open=opened.isoformat(), close=(opened + timedelta(minutes=35)).isoformat()))
        for symbol, scale in [('SPY',1.), ('QQQ',2.)]:
            n = np.arange(35)
            close = scale * (100 + day_number*.03 + np.sin(n*1.3)*.7 + n*.006)
            frames[symbol].append(pd.DataFrame(dict(open=close, high=close+.2*scale,
                low=close-.2*scale, close=close, volume=1000 + (n*173)%1500), index=index))
    snapshot = freeze_dataset({s:pd.concat(parts) for s,parts in frames.items()}, schedule, catalog.datasets,
        source='SYNTHETIC deterministic waves, not market data', schedule_source='SYNTHETIC 35-minute sessions')
    applications = [catalog.register('application', dict(id=s.lower(), version='1.0.0',
        instruments={'subject':s}, dataset=snapshot.id)) for s in frames]
    study = catalog.register('study', dict(id='vwap-study', version='1.0.0',
        event_rules='close.cross_above:vwap', contexts=['volume_ratio20','rsi14'],
        labels=[dict(id='return_5m', kind='return', minutes=5), dict(id='mfe_5m', kind='mfe', minutes=5), dict(id='mae_5m', kind='mae', minutes=5)]))
    study_candidates = [study.ref]
    for name, rule in [('participation','close.cross_above:vwap,volume_ratio20.gt:1'),
                       ('momentum','close.cross_above:vwap,rsi14.gt:50')]:
        modifier = catalog.register('modifier', dict(id='study-'+name, version='1.0.0', kind='study',
            category='technical_context', rationale='Inspect a declared context selection', changes={'event_rules':rule}))
        variant = catalog.register('variant', dict(id='study-'+name, version='1.0.0', kind='study',
            idea=idea.ref, base=study.ref, modifiers=[modifier.ref], rationale='One context change'))
        study_candidates.append(variant.ref)
    shared = dict(version='1.0.0', idea=idea.ref, applications=[x.ref for x in applications],
                  candidate_budget=3, minimum_samples=3, stopping_rule='One declared matrix; no tuning', aggregation='equal_instrument')
    study_protocol = register_protocol(dict(**shared, id='demo-event-study', kind='study',
        baseline=study.ref, candidates=study_candidates, attempt_budget=6,
        splits=[dict(name='development',stage='development',start=schedule[0]['open'],end=schedule[5]['close'])],
        primary_metric='mean', allowed_differences=['event_rules'], analysis={'label':'return_5m','grouping':{'context':'volume_ratio20','edges':[1.]}}), catalog)
    study_results = run_protocol(study_protocol.id, store)
    evidence = [c['experiment_id'] for c in study_results['cells'] if c['status'] == 'completed']
    if len(evidence) != 6:
        raise RuntimeError('synthetic study failed: ' + str(study_results['cells']))
    catalog.assess(idea.id, author='synthetic acceptance demonstration', conclusion='Inconclusive for real markets. Proceed only to verify the policy workflow.',
                   evidence=evidence, limitations='All observations are manufactured fixtures; no investment conclusion.')
    recipe = json.loads((repo / 'examples/strategies/macro-context-v1.json').read_text())
    recipe.pop('instruments')
    recipe.pop('evaluation')
    recipe['risk']['max_hold_minutes'] = 5
    policy = catalog.register('policy', dict(id='vwap-policy', version='1.0.0', recipe=recipe,
        evidence=evidence, contrary_evidence=evidence, status='candidate',
        rationale='Workflow demonstration only; synthetic studies cannot justify a real trading edge.',
        limitations='Synthetic data, simplified execution, independent symbols.'))
    policies = [policy.ref]
    for name, changes in [('volume',{'entry':{'rules':'close.cross_above:vwap,volume_ratio20.gt:1'}}),
                          ('shorter-hold',{'risk':{'max_hold_minutes':3}})]:
        modifier = catalog.register('modifier', dict(id='policy-'+name, version='1.0.0', kind='policy',
            category='entry' if name == 'volume' else 'risk', rationale='Declared policy sensitivity', changes=changes))
        variant = catalog.register('variant', dict(id='policy-'+name, version='1.0.0', kind='policy',
            idea=idea.ref, base=policy.ref, modifiers=[modifier.ref], rationale='One policy change'))
        policies.append(variant.ref)
    policy_protocol = register_protocol(dict(**shared, id='demo-policy', kind='backtest',
        baseline=policy.ref, candidates=policies, final_candidates=[policy.ref], attempt_budget=8,
        splits=[dict(name='validation',stage='validation',start=schedule[6]['open'],end=schedule[8]['close']),
                dict(name='final',stage='final',start=schedule[9]['open'],end=schedule[11]['close'])],
        primary_metric='total_pnl_dollars', allowed_differences=['entry.rules','risk.max_hold_minutes']), catalog)
    policy_results = run_protocol(policy_protocol.id, store)
    card = export_idea_markdown(idea.id, store)
    if reports:
        card = write_demo_reports(catalog, reports, study_results, policy_results, card)
    return dict(study=study_results, policy=policy_results, card=card)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--reports')
    args = parser.parse_args()
    result = run_demo(args.root, args.reports)
    print(json.dumps({'study':result['study']['status'], 'policy':result['policy']['status'], 'idea_card':str(result['card'])}))
