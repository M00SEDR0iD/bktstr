import math
import statistics

import pandas as pd
import pytest


def inputs():
    index = pd.DatetimeIndex([f'2026-08-{d:02d}T13:{m:02d}:00Z' for d in (3, 4, 5) for m in (30, 31)])
    bars = pd.DataFrame({'open': [100.] * 6, 'close': [90., 110., 100., 105., 100., 100.]}, index=index)
    schedule = [dict(date=f'2026-08-{d:02d}', open=f'2026-08-{d:02d}T13:30:00Z', close=f'2026-08-{d:02d}T13:32:00Z') for d in (3, 4, 5)]
    trades = [dict(entry_time=index[0].isoformat(), exit_time=index[1].isoformat(), entry_price=100., position_size=1000., side='long', pnl_dollars=100.),
              dict(entry_time=index[2].isoformat(), exit_time=index[3].isoformat(), entry_price=100., position_size=1000., side='short', pnl_dollars=-50.)]
    return dict(trades=trades, bars=bars, schedule=schedule, risk=dict(stop_pct=20., target_pct=40., starting_capital=1000.), slippage_bps=0.)


def test_r_expectancy_rr_marked_drawdown_and_daily_sharpe():
    from bktstr.services.policy_metrics import policy_metrics
    result = policy_metrics(**inputs())
    m = result['metrics']
    assert m['ev_r_per_trade'] == pytest.approx(.125)
    assert m['ev_dollars_per_trade'] == 25
    assert m['planned_reward_risk'] == m['realized_reward_risk'] == 2
    assert m['max_drawdown_pct'] == 10
    assert m['max_drawdown_dollars'] == 100
    daily = [.1, -50/1100, 0.]
    assert m['sharpe'] == pytest.approx(statistics.mean(daily) / statistics.stdev(daily) * math.sqrt(252))
    assert [row['return'] for row in result['daily_equity']] == pytest.approx(daily)
    assert [t['initial_risk_dollars'] for t in result['trades']] == [200, 200]
    assert [t['net_r'] for t in result['trades']] == [.5, -.25]
    assert result['definitions']['drawdown_sampling'] == 'minute_close_mark_to_market'


def test_size_changes_do_not_improve_r_expectancy():
    from bktstr.services.policy_metrics import policy_metrics
    a = inputs()
    b = inputs()
    for t in b['trades']:
        t['position_size'] *= 2
        t['pnl_dollars'] *= 2
    x, y = policy_metrics(**a)['metrics'], policy_metrics(**b)['metrics']
    assert y['ev_r_per_trade'] == x['ev_r_per_trade']
    assert y['ev_dollars_per_trade'] == x['ev_dollars_per_trade'] * 2


def test_empty_and_one_sided_samples_are_not_fabricated():
    from bktstr.services.policy_metrics import policy_metrics
    values = inputs()
    empty = policy_metrics(**(values | {'trades': []}))['metrics']
    assert empty['ev_r_per_trade'] is None
    assert empty['ev_dollars_per_trade'] is None
    assert empty['realized_reward_risk'] is None
    assert empty['sharpe'] is None
    assert empty['max_drawdown_pct'] == 0
    only_win = policy_metrics(**(values | {'trades':values['trades'][:1]}))['metrics']
    assert only_win['realized_reward_risk'] is None


def test_breakeven_counts_in_ev_and_nonpositive_equity_blocks_sharpe():
    from bktstr.services.policy_metrics import policy_metrics
    values = inputs()
    values['trades'][1]['pnl_dollars'] = 0.
    assert policy_metrics(**values)['metrics']['ev_r_per_trade'] == .25
    values['trades'][1]['pnl_dollars'] = -1200.
    result = policy_metrics(**values)
    assert result['metrics']['sharpe'] is None
    assert result['metrics']['max_drawdown_pct'] > 100
    assert 'nonpositive_equity' in result['unavailable_reasons']['sharpe']


def test_slippage_initial_risk_and_same_bar_exit():
    from bktstr.services.policy_metrics import policy_metrics
    values = inputs()
    trade = values['trades'][0]
    trade['exit_time'] = trade['entry_time']
    trade['pnl_dollars'] = -4.
    result = policy_metrics(**(values | {'trades':[trade], 'slippage_bps':2.}))
    assert result['metrics']['ev_r_per_trade'] == -.02
    assert result['metrics']['max_drawdown_dollars'] == 4
    assert result['daily_equity'][0]['equity'] == 996


def test_missing_marked_bar_fails_instead_of_understating_drawdown():
    from bktstr.services.policy_metrics import policy_metrics
    values = inputs()
    values['bars'] = values['bars'].iloc[1:]
    with pytest.raises(ValueError, match='missing'):
        policy_metrics(**values)


def test_new_campaign_cannot_optimize_dollar_pnl(tmp_path):
    from test_configured_research import configured
    from test_idea_resolution import policy_doc
    from test_research_protocol import protocol_doc
    from bktstr.services.research_protocol import register_protocol
    store, catalog, request = configured(tmp_path)
    base = catalog.register('policy', policy_doc())
    doc = protocol_doc(request, kind='backtest', baseline=base.ref, candidates=[base.ref],
                       analysis=None, primary_metric='total_pnl_dollars')
    with pytest.raises(ValueError, match='ev_r_per_trade'):
        register_protocol(doc, catalog)


def test_legacy_protocol_retry_preserves_frozen_pnl_objective(tmp_path):
    import json
    from test_configured_research import configured
    from test_idea_resolution import policy_doc
    from test_research_protocol import protocol_doc
    from bktstr.research_ideas import canonical, digest
    from bktstr.services.research_protocol import register_protocol, get_protocol
    store, catalog, request = configured(tmp_path)
    base = catalog.register('policy', policy_doc())
    new = register_protocol(protocol_doc(request, kind='backtest', baseline=base.ref, candidates=[base.ref],
                            analysis=None, primary_metric='ev_r_per_trade'), catalog)
    old = new.document | {'primary_metric':'total_pnl_dollars'}
    with catalog.transaction() as db:
        db.execute('UPDATE research_protocols SET document=?,digest=? WHERE id=?', (canonical(old), digest(old), new.id))
    assert register_protocol(old, catalog).document == old
    assert get_protocol(new.id, catalog).document['primary_metric'] == 'total_pnl_dollars'


def test_policy_campaign_defaults_to_r_and_reports_it(tmp_path):
    from test_configured_research import configured
    from test_idea_resolution import policy_doc
    from test_research_protocol import protocol_doc
    from bktstr.services.research_protocol import register_protocol, run_protocol
    from bktstr.services.idea_reports import export_idea_markdown
    store, catalog, request = configured(tmp_path)
    base = catalog.register('policy', policy_doc())
    variant_doc = policy_doc(id='size-change')
    variant_doc['recipe']['risk']['position_size'] *= 2
    changed = catalog.register('policy', variant_doc)
    doc = protocol_doc(request, kind='backtest', baseline=base.ref, candidates=[base.ref, changed.ref],
                       candidate_budget=2, attempt_budget=2, analysis=None, allowed_differences=['risk.position_size'])
    doc.pop('primary_metric')
    protocol = register_protocol(doc, catalog)
    assert protocol.document['primary_metric'] == 'ev_r_per_trade'
    result = run_protocol(protocol.id, store)
    assert result['status'] == 'completed', result['cells']
    comparison = result['comparisons'][0]
    assert comparison['metric'] == 'ev_r_per_trade'
    assert comparison['effect'] == pytest.approx(0, abs=1e-6)
    assert set(comparison['metric_changes']) >= {'ev_r_per_trade', 'realized_reward_risk', 'sharpe', 'max_drawdown_pct'}
    card = export_idea_markdown(request['idea']['id'], store).read_text(encoding='utf-8')
    assert card.index('EV (R/trade)') < card.index('Tests and results')
    report = (catalog.reports / (result['cells'][0]['experiment_id'] + '-results.md')).read_text(encoding='utf-8')
    assert report.index('EV (R/trade)') < report.index('What was tested')
