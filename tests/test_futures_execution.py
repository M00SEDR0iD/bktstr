import pandas as pd
import pytest


def recipe(**changes):
    return dict(signal={'kind': 'rsi', 'threshold': 30.0}, stop_points=10.0,
                risk_budget=400.0, max_contracts=2, reward_risk=1.5,
                commission_per_side=2.5, slippage_ticks=1, warmup_minutes=0,
                last_entry_buffer=0, max_hold_minutes=60, cooldown_minutes=0,
                execution_model='futures-ohlcv.1.0.0', **changes)


def terms():
    return dict(multiplier=20.0, tick_size=0.25, starting_balance=50000.0,
                failure_floor=48000.0, profit_target=3000.0, max_trades=10,
                contracts={'2026-09-01': 'NQU6'}, excluded_sessions=[])


def bars(rows):
    return pd.DataFrame(rows, columns=['open', 'high', 'low', 'close', 'volume'],
                        index=pd.date_range('2026-09-01T13:30Z', periods=len(rows), freq='min'))


def test_next_open_integer_contracts_costs_and_stop_first():
    from bktstr.futures_execution import execute_session
    frame = bars([[100, 101, 99, 100, 10], [100, 120, 85, 101, 10]])
    result = execute_session(frame, [1, 0], recipe(), terms(), 'NQU6')
    t = result['trades'][0]
    assert t['entry_time'] == frame.index[1].isoformat()
    assert t['contracts'] == 2 and t['entry_price'] == 100.25
    assert t['exit_price'] == 90.0 and t['reason'] == 'stop'
    assert t['initial_risk_dollars'] == 400
    assert t['pnl_dollars'] == -420  # 10.25 points * $20 * 2 plus $10 fees
    assert t['net_r'] == -1.05


def test_stop_gap_fills_beyond_stop():
    from bktstr.futures_execution import execute_session
    frame = bars([[100, 101, 99, 100, 10], [100, 102, 99, 100, 10], [80, 82, 79, 81, 10]])
    t = execute_session(frame, [1, 0, 0], recipe(), terms(), 'NQU6')['trades'][0]
    assert t['exit_price'] == 79.75
    assert t['pnl_dollars'] == -830


def test_short_target_and_minimum_contract_rejection():
    from bktstr.futures_execution import execute_session
    frame = bars([[100, 101, 99, 100, 10], [100, 101, 80, 85, 10]])
    t = execute_session(frame, [-1, 0], recipe(), terms(), 'NQU6')['trades'][0]
    assert t['exit_price'] == 85.0 and t['pnl_dollars'] == 580
    cfg = recipe(); cfg['risk_budget'] = 100.0
    result = execute_session(frame, [-1, 0], cfg, terms(), 'NQU6')
    assert result['trades'] == []
    assert result['decisions'][0]['reason'] == 'risk_budget_below_one_contract'


def test_signals_are_causal_and_invalid_tick_rr_rejected():
    from bktstr.futures_execution import signals, execute_session
    frame = bars([[100 + (i % 5), 105, 95, 100 + (i % 5), 10] for i in range(60)])
    for kind, threshold in [('rsi', 30.0), ('bollinger', 2.0), ('vwap', 1.5)]:
        cfg = recipe(); cfg['signal'] = {'kind': kind, 'threshold': threshold}
        assert list(signals(frame, cfg)[:40]) == list(signals(frame.iloc[:40], cfg))
    cfg = recipe(); cfg['stop_points'] = 0.25
    with pytest.raises(ValueError, match='tick'):
        execute_session(frame, [0] * len(frame), cfg, terms(), 'NQU6')


def test_challenge_floor_precedes_closed_target_and_counts_timeout():
    from bktstr.futures_execution import evaluate_attempt
    base = dict(entry_time='2026-09-01T13:31:00+00:00', exit_time='2026-09-01T13:32:00+00:00',
                pnl_dollars=3000.0, min_net_excursion=-2000.0,
                max_net_excursion=3000.0, intratrade_drawdown_bound=2000.0)
    failed = evaluate_attempt([base], terms())
    assert failed['status'] == 'failed'
    assert failed['ending_balance'] is None and failed['failure_equity_bound'] == 48000
    assert evaluate_attempt([base | {'min_net_excursion': -100.0}], terms())['status'] == 'passed'
    flat = base | {'pnl_dollars': 0.0, 'min_net_excursion': -10.0, 'max_net_excursion': 0.0}
    assert evaluate_attempt([flat] * 10, terms())['status'] == 'timeout'
    assert evaluate_attempt([flat], terms())['status'] == 'censored'


def test_equity_revision_digest_preserved_and_futures_terms_required():
    from bktstr.research_ideas import parse_application, digest
    doc = dict(id='x', version='1.0.0', instruments={'subject': 'SPY'}, dataset='a'*64,
               profile='equity-minute', calendar='XNYS', timezone='America/New_York', timeframe='1m', currency='USD')
    assert parse_application(doc).digest == digest(doc)
    future = doc | {'instruments': {'subject': 'NQ'}, 'profile': 'futures-minute', 'futures': terms()}
    assert parse_application(future).document['futures']['multiplier'] == 20
    with pytest.raises(ValueError):
        parse_application(doc | {'profile': 'futures-minute'})


def test_futures_runs_through_existing_worker_and_persists(tmp_path):
    from bktstr.services.experiments import ExperimentStore, ExperimentWorker
    from bktstr.services.research_store import ResearchCatalog
    from bktstr.services.configured_research import submit_research_run, research_operations
    from bktstr.dataset_snapshots import freeze_dataset
    store = ExperimentStore(tmp_path); catalog = ResearchCatalog(store)
    frame = bars([[100, 101, 99, 100, 10]] * 40)
    schedule = [{'date': '2026-09-01', 'open': frame.index[0].isoformat(), 'close': (frame.index[-1]+pd.Timedelta(minutes=1)).isoformat()}]
    snapshot = freeze_dataset({'NQ': frame}, schedule, catalog.datasets, source='synthetic-futures')
    idea = catalog.register('idea', dict(id='futures', version='1.0.0', title='Reversion', thesis='Test', mechanism='Test', falsification='Test', applicability='Futures', roles=['subject']))
    policy = catalog.register('policy', dict(id='p', version='1.0.0', recipe=recipe(), rationale='test', limitations='OHLC'))
    app = catalog.register('application', dict(id='a', version='1.0.0', instruments={'subject':'NQ'}, dataset=snapshot.id, profile='futures-minute', futures=terms()))
    record = submit_research_run(store, dict(operation='configured_backtest', idea=idea.ref, specification=policy.ref,
        application=app.ref, start=schedule[0]['open'], end=schedule[0]['close']), 'futures-test')
    worker = ExperimentWorker(store, research_operations(store))
    result = worker.run_one(); worker.release_lease()
    assert result.status == 'completed', result.error
    saved = store.load_experiment(record.experiment_id)
    assert saved.result['metrics']['trade_count'] == 0
    assert saved.result['metric_definitions']['execution_model'] == 'futures-ohlcv.1.0.0'
    assert saved.result['decisions_artifact']
    from bktstr.services.idea_reports import render_idea_html, render_test_markdown
    import json, re
    html = render_idea_html(idea.id,store)
    embedded = json.loads(re.search(r'<script id="idea-data" type="application/json">(.*?)</script>',html,re.S).group(1))
    assert embedded['attempts'][0]['result']['challenge']['session_starts'][0]['status'] == 'censored'
    assert embedded['attempts'][0]['result']['application']['futures']['starting_balance'] == 50000
    markdown = render_test_markdown(record.experiment_id,store)
    assert 'per-side commissions' in markdown and 'Evaluation attempts' in markdown
    from bktstr.services.research_protocol import register_protocol, run_protocol
    second = catalog.register('policy', policy.document | {'id':'p2', 'recipe':recipe() | {'risk_budget':250.0}})
    register_protocol(dict(id='futures-campaign',version='1.0.0',idea=idea.ref,kind='backtest',
        baseline=policy.ref,candidates=[policy.ref,second.ref],applications=[app.ref],
        splits=[dict(name='development',stage='development',start=schedule[0]['open'],end=schedule[0]['close'])],
        candidate_budget=2,attempt_budget=2,minimum_samples=1,stopping_rule='fixed matrix',
        primary_metric='ev_r_per_trade',allowed_differences=['risk_budget'],aggregation='equal_instrument'),catalog)
    comparison = run_protocol('futures-campaign',store)
    assert comparison['status'] == 'completed'


def test_hold_limit_and_cutoff_do_not_create_late_positions():
    from bktstr.futures_execution import execute_session
    frame = bars([[100, 101, 99, 100, 10]]*5)
    cfg = recipe(); cfg['max_hold_minutes'] = 2; cfg['last_entry_buffer'] = 2
    result = execute_session(frame, [1,0,1,0,0], cfg, terms(), 'NQU6')
    assert len(result['trades']) == 1
    assert result['trades'][0]['exit_time'] == frame.index[2].isoformat()
    assert result['trades'][0]['reason'] == 'time'
    assert result['trades'][0]['pnl_dollars'] == -30
    assert result['decisions'][1]['reason'] == 'entry_cutoff'


def test_missing_minutes_and_unmapped_contract_fail_closed():
    from bktstr.futures_execution import execute_session
    frame = bars([[100,101,99,100,10]]*4)
    with pytest.raises(ValueError, match='consecutive'):
        execute_session(frame.iloc[[0,2,3]], [1,0,0], recipe(), terms(), 'NQU6')
    with pytest.raises(ValueError, match='mapping'):
        execute_session(frame, [1,0,0,0], recipe(), terms(), 'NQZ6')
    last = execute_session(frame, [0,0,0,1], recipe(), terms(), 'NQU6')
    assert last['decisions'][-1]['reason'] == 'session_ended'


def test_incomplete_session_censors_challenge_before_next_trade():
    from bktstr.futures_execution import evaluate_attempt
    account = terms(); account['excluded_sessions'] = ['2026-09-02']
    a = dict(entry_time='2026-09-01T13:31:00+00:00', exit_time='2026-09-01T13:32:00+00:00',
             pnl_dollars=1500.0,min_net_excursion=-100.0,max_net_excursion=1500.0,intratrade_drawdown_bound=100.0)
    b = a | {'entry_time':'2026-09-03T13:31:00+00:00','exit_time':'2026-09-03T13:32:00+00:00'}
    result = evaluate_attempt([a,b], account)
    assert result['status'] == 'censored' and result['trades'] == 1


@pytest.mark.parametrize('kind,threshold', [('vwap',1.5),('bollinger',1.5),('rsi',30.0)])
def test_each_detector_fires_both_sides(kind, threshold):
    from bktstr.futures_execution import signals
    cfg = recipe(); cfg['signal'] = dict(kind=kind, threshold=threshold)
    sequences = ([100.0]*20+[90.0,100.0], [100.0]*20+[110.0,100.0]) if kind != 'rsi' else (
        list(range(100,70,-1))+[100], list(range(100,130))+[100])
    for sequence, expected in zip(sequences, (1,-1)):
        frame = bars([[x,x+1,x-1,x,10] for x in sequence])
        assert signals(frame,cfg)[-1] == expected


def test_intrabar_bound_tracks_peak_before_later_loss():
    from bktstr.futures_execution import execute_session
    frame = bars([[100,101,99,100,10],[100,105,99,103,10],[103,104,98,100,10]])
    trade = execute_session(frame,[1,0,0],recipe(),terms(),'NQU6')['trades'][0]
    assert trade['max_net_excursion'] == 170
    assert trade['min_net_excursion'] == -110
    assert trade['intratrade_drawdown_bound'] == 280


def test_tenth_trade_target_and_no_trade_censoring():
    from bktstr.futures_execution import evaluate_attempt
    row = dict(entry_time='2026-09-01T13:31:00+00:00',exit_time='2026-09-01T13:32:00+00:00',
               pnl_dollars=300.0,min_net_excursion=-10.0,max_net_excursion=300.0,intratrade_drawdown_bound=10.0)
    assert evaluate_attempt([row]*10,terms())['status'] == 'passed'
    smaller = row | {'pnl_dollars':290.0}
    assert evaluate_attempt([smaller]*11,terms())['status'] == 'timeout'
    assert evaluate_attempt([],terms())['status'] == 'censored'


def test_sessions_reset_indicators_and_close_before_roll(tmp_path):
    from bktstr.dataset_snapshots import freeze_dataset
    from bktstr.futures_execution import run_scheduled
    sequence = [100]*20+[90,100,100]
    first = bars([[x,x+1,x-1,x,10] for x in sequence])
    second = first.copy(); second.index = first.index + pd.Timedelta(days=1)
    second.iloc[0] = [90,91,89,90,10]
    schedule = [dict(date=str(f.index[0].date()),open=f.index[0].isoformat(),close=(f.index[-1]+pd.Timedelta(minutes=1)).isoformat()) for f in (first,second)]
    snapshot = freeze_dataset({'NQ':pd.concat([first,second])},schedule,tmp_path,source='synthetic')
    account = terms(); account['contracts']['2026-09-02'] = 'NQZ6'
    cfg = recipe(); cfg['signal'] = dict(kind='bollinger',threshold=1.5)
    result = run_scheduled(snapshot,dict(instruments={'subject':'NQ'},futures=account),cfg,schedule[0]['open'],schedule[-1]['close'])
    assert len(result['trades']) == 2
    assert [t['contract'] for t in result['trades']] == ['NQU6','NQZ6']
    assert [t['entry_time'] for t in result['trades']] == [first.index[-1].isoformat(),second.index[-1].isoformat()]
    assert all(t['reason']=='session_end' for t in result['trades'])
