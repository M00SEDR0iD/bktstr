"""Versioned, deterministic futures OHLCV simulation and evaluation accounting."""
from datetime import date
import math
import re
import statistics
from typing import Literal

import numpy as np
import pandas as pd
from pydantic import Field, model_validator
from .research_ideas import Object


class FuturesTerms(Object):
    multiplier: float = Field(gt=0)
    tick_size: float = Field(gt=0)
    starting_balance: float = Field(gt=0)
    failure_floor: float = Field(gt=0)
    profit_target: float = Field(gt=0)
    max_trades: int = Field(gt=0, le=1000)
    contracts: dict[str, str] = Field(min_length=1)
    excluded_sessions: list[str] = Field(default_factory=list)

    @model_validator(mode='after')
    def valid(self):
        if self.failure_floor >= self.starting_balance:
            raise ValueError('failure floor must be below starting balance')
        for day, contract in self.contracts.items():
            date.fromisoformat(day)
            if not re.fullmatch(r'[A-Z0-9]{1,10}[FGHJKMNQUVXZ][0-9]{1,4}', contract):
                raise ValueError('explicit delivery contract required')
        for day in self.excluded_sessions:
            date.fromisoformat(day)
        if set(self.excluded_sessions) & set(self.contracts):
            raise ValueError('excluded sessions cannot be executable sessions')
        return self


class Signal(Object):
    kind: Literal['vwap', 'bollinger', 'rsi']
    threshold: float = Field(gt=0, lt=50)


class FuturesRecipe(Object):
    execution_model: Literal['futures-ohlcv.1.0.0']
    signal: Signal
    stop_points: float = Field(gt=0)
    risk_budget: float = Field(gt=0)
    max_contracts: int = Field(gt=0, le=100)
    reward_risk: float = Field(gt=0)
    commission_per_side: float = Field(ge=0)
    slippage_ticks: int = Field(ge=0, le=100)
    warmup_minutes: int = Field(ge=0, le=390)
    last_entry_buffer: int = Field(ge=0, le=390)
    max_hold_minutes: int = Field(gt=0, le=390)
    cooldown_minutes: int = Field(ge=0, le=390)


def signals(frame, recipe):
    """Completed-bar detectors, reset by caller for each session; no outcomes."""
    cfg = FuturesRecipe.model_validate(recipe)
    close = frame.close
    if cfg.signal.kind == 'rsi':
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False, min_periods=14).mean()
        value = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        value = value.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
        lower, upper = cfg.signal.threshold, 100 - cfg.signal.threshold
    else:
        deviation = close.rolling(20, min_periods=20).std(ddof=0).replace(0, np.nan)
        if cfg.signal.kind == 'bollinger':
            center = close.rolling(20, min_periods=20).mean()
        else:
            typical = (frame.high + frame.low + close) / 3
            center = (typical * frame.volume).cumsum() / frame.volume.cumsum().replace(0, np.nan)
        value = (close - center) / deviation
        lower, upper = -cfg.signal.threshold, cfg.signal.threshold
    long = (value.shift(1) < lower) & (value >= lower)
    short = (value.shift(1) > upper) & (value <= upper)
    return np.where(long, 1, np.where(short, -1, 0))


def execute_session(frame, signal_values, recipe, terms, contract):
    cfg = FuturesRecipe.model_validate(recipe)
    account = FuturesTerms.model_validate(terms)
    tick, multiplier = account.tick_size, account.multiplier
    for value in (cfg.stop_points, cfg.stop_points * cfg.reward_risk):
        if abs(value / tick - round(value / tick)) > 1e-8:
            raise ValueError('stop and target must be exact tick multiples')
    if len(frame) != len(signal_values) or len(frame) == 0:
        raise ValueError('nonempty bars and aligned signals required')
    expected = pd.date_range(frame.index[0], periods=len(frame), freq='min')
    if frame.index.tz is None or not frame.index.equals(expected):
        raise ValueError('complete consecutive minute session required')
    values = frame[['open', 'high', 'low', 'close', 'volume']].to_numpy(float)
    if not np.isfinite(values).all() or (values[:, :4] <= 0).any() or (values[:, 4] < 0).any():
        raise ValueError('invalid futures OHLCV')
    if (values[:, 1] < values[:, [0, 2, 3]].max(axis=1)).any() or (values[:, 2] > values[:, [0, 1, 3]].min(axis=1)).any():
        raise ValueError('inconsistent futures OHLC')
    if not np.allclose(values[:, :4] / tick, np.round(values[:, :4] / tick), rtol=0, atol=1e-7):
        raise ValueError('prices must align to contract tick')
    if any(x not in (-1, 0, 1) for x in signal_values):
        raise ValueError('signals must be -1, 0 or 1')
    day = str(frame.index[0].tz_convert('America/New_York').date())
    if account.contracts.get(day) != contract:
        raise ValueError('session contract mapping mismatch')
    size = min(cfg.max_contracts, int(cfg.risk_budget // (cfg.stop_points * multiplier)))
    slip = cfg.slippage_ticks * tick
    trades, decisions, marks = [], [], []
    pos, realized, last_exit = None, 0.0, -10000
    for i, (opened, high, low, close, volume) in enumerate(values):
        # A signal becomes known at the next minute open, never its own open.
        signal = int(signal_values[i-1]) if i else 0
        if signal:
            reason = ('position_open' if pos else 'warmup' if i < cfg.warmup_minutes else
                      'entry_cutoff' if i >= len(frame)-cfg.last_entry_buffer else
                      'cooldown' if i <= last_exit + cfg.cooldown_minutes else
                      'risk_budget_below_one_contract' if size < 1 else 'accepted')
            decisions.append(dict(signal_time=frame.index[i-1].isoformat(), eligible_at=frame.index[i].isoformat(),
                                  side='long' if signal == 1 else 'short', reason=reason))
            if reason == 'accepted':
                entry = opened + signal * slip
                pos = dict(sign=signal, entry=entry, index=i, minimum=0.0, maximum=0.0, peak=0.0, dd=0.0)
        lower = upper = mark = realized
        if pos:
            sign, entry = pos['sign'], pos['entry']
            stop, target = entry-sign*cfg.stop_points, entry+sign*cfg.stop_points*cfg.reward_risk
            net = lambda price: sign*(price-entry)*multiplier*size - 2*cfg.commission_per_side*size
            gap_stop = sign*(opened-stop) <= 0
            stop_hit = low <= stop if sign == 1 else high >= stop
            target_hit = high >= target if sign == 1 else low <= target
            exit_price, reason = None, None
            if gap_stop:
                exit_price, reason = opened-sign*slip, 'stop_gap'
            elif stop_hit:
                exit_price, reason = stop-sign*slip, 'stop'
            elif target_hit:
                exit_price, reason = target-sign*slip, 'target'
            elif i-pos['index']+1 >= cfg.max_hold_minutes or i == len(frame)-1:
                exit_price = close-sign*slip
                reason = 'session_end' if i == len(frame)-1 else 'time'
            adverse = low if sign == 1 else high
            favorable = high if sign == 1 else low
            if gap_stop:
                adverse = favorable = opened
            else:
                adverse = max(adverse, stop) if sign == 1 else min(adverse, stop)
                favorable = min(favorable, target) if sign == 1 else max(favorable, target)
            net_low, net_high = net(adverse-sign*slip), net(favorable-sign*slip)
            if exit_price is not None:
                net_low, net_high = min(net_low, net(exit_price)), max(net_high, net(exit_price))
            pos['minimum'], pos['maximum'] = min(pos['minimum'], net_low), max(pos['maximum'], net_high)
            pos['peak'] = max(pos['peak'], net_high)
            pos['dd'] = max(pos['dd'], pos['peak']-net_low)
            lower, upper = realized+net_low, realized+net_high
            mark = realized + net(close-sign*slip)
            if exit_price is not None:
                pnl = net(exit_price)
                trades.append(dict(entry_time=frame.index[pos['index']].isoformat(), exit_time=frame.index[i].isoformat(),
                    session=day, contract=contract, side='long' if sign == 1 else 'short', contracts=size,
                    entry_price=entry, exit_price=exit_price, stop_price=stop, target_price=target, reason=reason,
                    pnl_dollars=pnl, initial_risk_dollars=cfg.stop_points*multiplier*size,
                    net_r=pnl/(cfg.stop_points*multiplier*size), commission=2*cfg.commission_per_side*size,
                    min_net_excursion=pos['minimum'], max_net_excursion=pos['maximum'], intratrade_drawdown_bound=pos['dd']))
                realized += pnl
                mark, pos, last_exit = realized, None, i
        marks.append(dict(timestamp=frame.index[i].isoformat(), net=mark, low=lower, high=upper))
    if signal_values[-1]:
        decisions.append(dict(signal_time=frame.index[-1].isoformat(),
            eligible_at=(frame.index[-1]+pd.Timedelta(minutes=1)).isoformat(),
            side='long' if signal_values[-1] == 1 else 'short', reason='session_ended'))
    return dict(trades=trades, decisions=decisions, marks=marks, pnl=realized)


def evaluate_attempt(trades, terms):
    account = FuturesTerms.model_validate(terms)
    balance = peak = account.starting_balance
    drawdown, count, status, failure_equity = 0.0, 0, 'censored', None
    first = trades[0]['entry_time'][:10] if trades else None
    for trade in trades[:account.max_trades]:
        if any(first <= day <= trade['exit_time'][:10] for day in account.excluded_sessions):
            break
        drawdown = max(drawdown, peak-(balance+trade['min_net_excursion']), trade['intratrade_drawdown_bound'])
        if balance+trade['min_net_excursion'] <= account.failure_floor:
            failure_equity = balance+trade['min_net_excursion']
            status = 'failed'; count += 1; break
        peak = max(peak, balance+trade['max_net_excursion'])
        balance += trade['pnl_dollars']; count += 1
        if balance >= account.starting_balance+account.profit_target:
            status = 'passed'; break
        if count == account.max_trades:
            status = 'timeout'
    return dict(status=status, trades=count, ending_balance=balance if status != 'failed' else None,
                last_closed_balance=balance, failure_equity_bound=failure_equity,
                drawdown_bound_dollars=drawdown, within_4pct_starting_capital=bool(drawdown < .04*account.starting_balance))


def summarize(trades, daily, terms, recipe):
    account = FuturesTerms.model_validate(terms)
    rs = [x['net_r'] for x in trades]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    equity = peak = account.starting_balance
    dd = 0.0
    for t in trades:
        dd = max(dd, peak-(equity+t['min_net_excursion']), t['intratrade_drawdown_bound'])
        peak = max(peak, equity+t['max_net_excursion']); equity += t['pnl_dollars']
    changes = [x['pnl'] / account.starting_balance for x in daily]
    sharpe = statistics.mean(changes)/statistics.stdev(changes)*math.sqrt(252) if len(changes)>1 and statistics.stdev(changes)>0 else None
    metrics = dict(ev_r_per_trade=statistics.mean(rs) if rs else None,
        ev_dollars_per_trade=statistics.mean(t['pnl_dollars'] for t in trades) if trades else None,
        planned_reward_risk=recipe['reward_risk'], realized_reward_risk=statistics.mean(wins)/abs(statistics.mean(losses)) if wins and losses else None,
        sharpe=sharpe, max_drawdown_dollars=dd, max_drawdown_pct=dd/account.starting_balance*100,
        trade_count=len(trades), sessions=len(daily), trades_per_session=len(trades)/len(daily) if daily else 0,
        multiple_trade_session_fraction=sum(x['trades']>=2 for x in daily)/len(daily) if daily else 0,
        total_pnl_dollars=sum(t['pnl_dollars'] for t in trades))
    blocks = [evaluate_attempt(trades[i:i+account.max_trades], terms) for i in range(0,len(trades),account.max_trades)]
    return metrics, blocks


def run_scheduled(snapshot, application, recipe, start, end):
    from .dataset_snapshots import instant, validate_scope
    from .research_ideas import digest
    cfg = FuturesRecipe.model_validate(recipe).model_dump(mode='json')
    terms = FuturesTerms.model_validate(application['futures']).model_dump(mode='json')
    document = snapshot.document
    if not document['controlled'] or document['adjustment'] != 'unadjusted':
        raise ValueError('futures requires complete raw unadjusted session data')
    _, _, schedule = validate_scope(snapshot, start, end, application['instruments'].values())
    if any(instant(s['open']) < instant(start) or instant(s['close']) > instant(end) for s in schedule):
        raise ValueError('futures split must include complete pinned sessions')
    frame = snapshot.frame(application['instruments']['subject'])
    trades, decisions, daily = [], [], []
    balance = peak = close_peak = terms['starting_balance']
    bound_dd = bound_pct = close_dd = close_pct = 0.0
    previous_balance = balance
    for session in schedule:
        raw = frame.loc[(frame.index >= instant(session['open'])) & (frame.index < instant(session['close']))]
        if len(raw) != int((instant(session['close'])-instant(session['open'])).total_seconds()/60):
            raise ValueError('incomplete futures session')
        contract = terms['contracts'].get(session['date'])
        if not contract:
            raise ValueError('missing session contract identity')
        result = execute_session(raw, signals(raw, cfg), cfg, terms, contract)
        trades.extend(result['trades']); decisions.extend(result['decisions'])
        for mark in result['marks']:
            peak = max(peak, balance+mark['high'])
            loss = peak-(balance+mark['low'])
            bound_dd = max(bound_dd, loss)
            bound_pct = max(bound_pct, 100*loss/peak)
            close_peak = max(close_peak, balance+mark['net'])
            close_dd = max(close_dd, close_peak-(balance+mark['net']))
            close_pct = max(close_pct, 100*(close_peak-(balance+mark['net']))/close_peak)
        balance += result['pnl']
        daily.append(dict(date=session['date'], pnl=result['pnl'], equity=balance,
            trades=len(result['trades']), **{'return': (balance-previous_balance)/previous_balance if previous_balance>0 else None}))
        previous_balance = balance
    metrics, blocks = summarize(trades, daily, terms, cfg)
    returns = [x['return'] for x in daily]
    metrics.update(max_drawdown_dollars=bound_dd, max_drawdown_pct=bound_pct,
        minute_close_drawdown_dollars=close_dd, minute_close_drawdown_pct=close_pct,
        sharpe=statistics.mean(returns)/statistics.stdev(returns)*math.sqrt(252)
        if len(returns)>1 and all(x is not None for x in returns) and statistics.stdev(returns)>0 else None)
    starts = []
    for s in schedule:
        candidates = [t for t in trades if t['session'] >= s['date']]
        # Incomplete sessions cannot be silently crossed before the first trade.
        excluded = [d for d in terms['excluded_sessions'] if d >= s['date']]
        if excluded:
            candidates = [t for t in candidates if t['session'] < min(excluded)]
        starts.append(dict(start_session=s['date'], **evaluate_attempt(candidates, terms)))
    unavailable = {k: 'insufficient observations' for k,v in metrics.items() if v is None}
    return dict(manifest=dict(digest=digest(cfg), document=cfg), trades=trades, metrics=metrics,
        summary=dict(total_pnl_dollars=metrics['total_pnl_dollars'], trades=len(trades), ending_equity=balance),
        metric_unavailable_reasons=unavailable, daily_equity=daily, decisions=decisions,
        challenge=dict(session_starts=starts, disjoint_trade_blocks=blocks),
        metric_definitions=dict(version='futures.1.0.0', execution_model=cfg['execution_model'], primary_metric='ev_r_per_trade',
            initial_risk='contracts * multiplier * planned stop points; before costs',
            costs='per-side commission and adverse tick slippage on both fills',
            drawdown_sampling='conservative intrabar high-before-low bound on liquidation equity',
            sharpe_sampling='all scored daily ending-equity returns; 252 sessions, zero risk-free, sample standard deviation'),
        limitations=['OHLC cannot establish intrabar order; drawdown is a conservative bound.',
            'Same-bar stop precedes target. No quote, queue, partial-fill, margin or prop-firm consistency simulation.',
            'Evaluation uses a fixed loss floor. Session-start attempts overlap and are dependent.',
            'XNYS denotes the chosen cash-hours research window, not the full CME trading calendar.'])
