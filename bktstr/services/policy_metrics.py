"""Versioned policy outcomes. Observational event labels never enter these metrics."""
import math
import statistics

import pandas as pd

from ..dataset_snapshots import instant


HEADLINE_METRICS = (
    ('ev_r_per_trade', 'EV (R/trade)'),
    ('ev_dollars_per_trade', 'EV ($/trade)'),
    ('planned_reward_risk', 'Planned reward/risk'),
    ('realized_reward_risk', 'Realized reward/risk (R)'),
    ('sharpe', 'Daily Sharpe (annualized)'),
    ('max_drawdown_pct', 'Maximum drawdown (%)'),
    ('max_drawdown_dollars', 'Maximum drawdown ($)'),
)


def policy_metrics(*, trades, bars, schedule, risk, slippage_bps):
    """Mark open positions at minute closes, settle exits at recorded net PnL.

    Inputs are the engine's non-overlapping single-instrument trades, original
    frozen minute bars, and the scored session schedule. Reconstruct entry shares
    from the raw open and configured slippage, avoiding rounded fill-price drift.
    """
    capital = float(risk['starting_capital'])
    stop = float(risk['stop_pct'])
    target = float(risk['target_pct'])
    if not all(math.isfinite(v) and v > 0 for v in (capital, stop, target)):
        raise ValueError('positive finite capital and risk required')
    if not math.isfinite(slippage_bps) or slippage_bps < 0:
        raise ValueError('invalid slippage')
    axis = pd.DatetimeIndex([t for s in schedule for t in pd.date_range(
        instant(s['open']), instant(s['close']), freq='min', inclusive='left')])
    if axis.empty or axis.has_duplicates or not axis.is_monotonic_increasing:
        raise ValueError('nonempty disjoint scored schedule required')
    if bars.index.has_duplicates or not axis.isin(bars.index).all():
        raise ValueError('missing or duplicate metric bars')
    frame = bars.loc[axis]
    realized = pd.Series(0., index=axis)
    unrealized = pd.Series(0., index=axis)
    enriched, previous_exit = [], None
    for trade in trades:
        entered, exited = instant(trade['entry_time']), instant(trade['exit_time'])
        if entered not in axis or exited not in axis or exited < entered:
            raise ValueError('trade outside scored minute schedule')
        if previous_exit is not None and entered <= previous_exit:
            raise ValueError('overlapping or unordered trades')
        previous_exit = exited
        side = trade['side']
        if side not in {'long', 'short'}:
            raise ValueError('unsupported trade side')
        sign = 1 if side == 'long' else -1
        notional = float(risk.get('position_size', trade['position_size']))
        pnl = float(trade['pnl_dollars'])
        if abs(notional - float(trade['position_size'])) > 0.000001:
            raise ValueError('trade notional differs from fixed-notional policy')
        if not math.isfinite(notional) or notional <= 0 or not math.isfinite(pnl):
            raise ValueError('invalid trade notional or PnL')
        entry = float(frame.loc[entered, 'open']) * (1 + sign * slippage_bps / 10000)
        if not math.isfinite(entry) or entry <= 0:
            raise ValueError('invalid entry price')
        initial_risk = notional * stop / 100
        enriched.append(dict(trade, initial_risk_dollars=initial_risk, net_r=pnl / initial_risk))
        entry_i, exit_i = axis.get_loc(entered), axis.get_loc(exited)
        unrealized.iloc[entry_i:exit_i] = sign * (frame['close'].iloc[entry_i:exit_i] - entry) * notional / entry
        realized.loc[exited] += pnl
    equity = capital + realized.cumsum() + unrealized
    if not all(math.isfinite(v) for v in equity):
        raise ValueError('nonfinite marked equity')
    peaks = equity.cummax().clip(lower=capital)
    drawdown = peaks - equity
    daily, prior = [], capital
    for session in schedule:
        session_equity = equity.loc[(axis >= instant(session['open'])) & (axis < instant(session['close']))]
        close = float(session_equity.iloc[-1])
        daily.append(dict(date=session['date'], equity=close, return_=((close - prior) / prior if prior > 0 else None)))
        prior = close
    daily = [dict(date=row['date'], equity=row['equity'], **{'return': row['return_']}) for row in daily]
    returns = [row['return'] for row in daily]
    reasons, sharpe = {}, None
    if equity.min() <= 0:
        reasons['sharpe'] = 'nonpositive_equity: account returns cannot support this Sharpe convention'
    elif len(returns) < 2:
        reasons['sharpe'] = 'fewer_than_two_sessions'
    elif statistics.stdev(returns) == 0:
        reasons['sharpe'] = 'zero_daily_return_variance'
    else:
        sharpe = statistics.mean(returns) / statistics.stdev(returns) * math.sqrt(252)
    rs = [t['net_r'] for t in enriched]
    winners, losers = [r for r in rs if r > 0], [r for r in rs if r < 0]
    rr = statistics.mean(winners) / abs(statistics.mean(losers)) if winners and losers else None
    if rr is None:
        reasons['realized_reward_risk'] = 'requires_at_least_one_win_and_one_loss'
    if not rs:
        reasons['ev_r_per_trade'] = reasons['ev_dollars_per_trade'] = 'no_trades'
    metrics = dict(ev_r_per_trade=statistics.mean(rs) if rs else None,
        ev_dollars_per_trade=statistics.mean(t['pnl_dollars'] for t in enriched) if rs else None,
        planned_reward_risk=target / stop, realized_reward_risk=rr, sharpe=sharpe,
        max_drawdown_pct=float((drawdown / peaks * 100).max()),
        max_drawdown_dollars=float(drawdown.max()), trade_count=len(rs),
        wins=len(winners), losses=len(losers), breakeven=len(rs)-len(winners)-len(losers),
        sessions=len(daily))
    return dict(metrics=metrics, trades=enriched, daily_equity=daily,
        unavailable_reasons=reasons,
        definitions=dict(version='1.0.0', primary_metric='ev_r_per_trade',
            initial_risk='filled_entry_notional * initial_stop_pct / 100; before exit costs',
            ev='mean(net trade PnL / initial planned dollar risk); breakevens included',
            costs='Net of modeled entry/exit slippage only; commissions and borrow fees are not modeled',
            realized_reward_risk='mean positive net R / absolute mean negative net R',
            drawdown_sampling='minute_close_mark_to_market', drawdown_sign='positive loss magnitude',
            sharpe_sampling='all scored session equity returns, including inactive sessions',
            sharpe_annualization=252, sharpe_risk_free_annual=0.0, sharpe_ddof=1),
        limitations=['Minute-close drawdown can miss intra-minute adverse excursions.',
            'Sharpe uses 252 sessions/year and zero risk-free return; serial dependence can distort annualization.',
            'EV is a sample estimate; increased EV alone is not evidence for promotion.',
            'R uses planned stop risk; gaps and costs can cause losses greater than 1R.'])
