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
    execution_model: Literal['futures-ohlcv.1.0.0', 'futures-ohlcv.1.1.0', 'futures-ohlcv.1.2.0']
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
    opening_bias: bool | None = None
    cash_start_offset: int | None = Field(default=None, ge=0, le=390)
    quantity_step: int | None = Field(default=None, gt=0, le=100)
    atr_period: int | None = Field(default=None, gt=0, le=390)
    atr_reference_points: float | None = Field(default=None, gt=0)

    signal_period: int | None = Field(default=None, ge=2, le=390)
    efficiency_period: int | None = Field(default=None, ge=2, le=390)
    max_efficiency_ratio: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode='after')
    def versioned_options(self):
        controls = {'signal_period', 'efficiency_period', 'max_efficiency_ratio'}
        if self.execution_model != 'futures-ohlcv.1.2.0' and controls & self.model_fields_set:
            raise ValueError('signal controls require futures-ohlcv.1.2.0')
        if (self.efficiency_period is None) != (self.max_efficiency_ratio is None):
            raise ValueError('efficiency period and maximum must be specified together')
        additions = {'opening_bias', 'cash_start_offset', 'quantity_step', 'atr_period', 'atr_reference_points'}
        if self.execution_model == 'futures-ohlcv.1.0.0':
            if additions & self.model_fields_set:
                raise ValueError('new execution options require futures-ohlcv.1.1.0')
        else:
            if any(getattr(self, k) is None for k in ('opening_bias', 'cash_start_offset', 'quantity_step')):
                raise ValueError('1.1 requires explicit opening bias, cash offset and quantity step')
            if (self.atr_period is None) != (self.atr_reference_points is None):
                raise ValueError('ATR period and reference must be specified together')
            if self.opening_bias and self.warmup_minutes < 1:
                raise ValueError('opening candle must close before entry')
            if self.max_contracts < self.quantity_step:
                raise ValueError('quantity step exceeds contract cap')
        return self


def signals(frame, recipe):
    """Completed-bar detectors, reset by caller for each session; no outcomes."""
    cfg = FuturesRecipe.model_validate(recipe)
    close = frame.close
    period = cfg.signal_period or (14 if cfg.signal.kind == 'rsi' else 20)
    if cfg.signal.kind == 'rsi':
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False, min_periods=period).mean()
        value = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
        value = value.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
        lower, upper = cfg.signal.threshold, 100 - cfg.signal.threshold
    else:
        deviation = close.rolling(period, min_periods=period).std(ddof=0).replace(0, np.nan)
        if cfg.signal.kind == 'bollinger':
            center = close.rolling(period, min_periods=period).mean()
        else:
            typical = (frame.high + frame.low + close) / 3
            weights = frame.volume.copy()
            if cfg.cash_start_offset:
                weights.iloc[:cfg.cash_start_offset] = 0
            center = (typical * weights).cumsum() / weights.cumsum().replace(0, np.nan)
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
    base_size = cfg.risk_budget / (cfg.stop_points * multiplier)
    legacy_size = min(cfg.max_contracts, int(cfg.risk_budget // (cfg.stop_points * multiplier)))
    offset, step = cfg.cash_start_offset or 0, cfg.quantity_step or 1
    if offset >= len(frame):
        raise ValueError('cash open outside supplied session')
    atr_values = None
    if cfg.atr_period:
        previous = frame.close.shift(1)
        true_range = pd.concat([frame.high-frame.low, (frame.high-previous).abs(),
                                (frame.low-previous).abs()], axis=1).max(axis=1)
        atr_values = true_range.rolling(cfg.atr_period, min_periods=cfg.atr_period).mean().to_numpy()
    efficiency_values = None
    if cfg.efficiency_period is not None:
        n = cfg.efficiency_period
        distance = frame.close.diff(n).abs()
        path = frame.close.diff().abs().rolling(n, min_periods=n).sum()
        efficiency_values = (distance / path.replace(0, float('nan'))).mask(path == 0, 0.0).to_numpy()
    slip = cfg.slippage_ticks * tick
    trades, decisions, marks = [], [], []
    pos, realized, last_exit = None, 0.0, -10000
    for i, (opened, high, low, close, volume) in enumerate(values):
        # A signal becomes known at the next minute open, never its own open.
        signal = int(signal_values[i-1]) if i else 0
        if signal:
            atr = float(atr_values[i-1]) if atr_values is not None and i else None
            available = atr is None or (math.isfinite(atr) and atr > 0)
            requested = base_size * cfg.atr_reference_points / atr if atr_values is not None and available else base_size
            quantity = int(min(cfg.max_contracts, requested) // step) * step
            if cfg.execution_model == 'futures-ohlcv.1.0.0':
                quantity = legacy_size
            fair = float((values[offset,1]+values[offset,2])/2) if cfg.opening_bias and i > offset else None
            entry = opened + signal * slip
            wrong_direction = fair is not None and (signal*(values[i-1,3]-fair) >= 0 or signal*(entry-fair) >= 0)
            efficiency = float(efficiency_values[i-1]) if efficiency_values is not None and i else None
            regime_available = efficiency is None or math.isfinite(efficiency)
            trending = regime_available and efficiency is not None and efficiency > cfg.max_efficiency_ratio
            reason = ('position_open' if pos else 'warmup' if i < offset + cfg.warmup_minutes else
                      'entry_cutoff' if i >= len(frame)-cfg.last_entry_buffer else
                      'cooldown' if i <= last_exit + cfg.cooldown_minutes else
                      'volatility_unavailable' if not available else
                      'regime_unavailable' if not regime_available else
                      'trending_regime' if trending else
                      'opening_direction' if wrong_direction else
                      'risk_budget_below_one_contract' if quantity < step else 'accepted')
            extra = dict(fair_value=fair, atr_at_entry=atr if available else None, proposed_contracts=quantity) if cfg.execution_model!='futures-ohlcv.1.0.0' else {}
            if efficiency_values is not None:
                extra['efficiency_ratio_at_entry'] = efficiency if regime_available else None
            decisions.append(dict(signal_time=frame.index[i-1].isoformat(), eligible_at=frame.index[i].isoformat(),
                                  side='long' if signal == 1 else 'short', reason=reason, **extra))
            if reason == 'accepted':
                pos = dict(sign=signal, entry=entry, index=i, minimum=0.0, maximum=0.0, peak=0.0, dd=0.0,
                           size=quantity, extra=extra)
        lower = upper = mark = realized
        if pos:
            size = pos['size']
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
                    min_net_excursion=pos['minimum'], max_net_excursion=pos['maximum'], intratrade_drawdown_bound=pos['dd'], **pos['extra']))
                realized += pnl
                mark, pos, last_exit = realized, None, i
        marks.append(dict(timestamp=frame.index[i].isoformat(), net=mark, low=lower, high=upper))
    if signal_values[-1]:
        terminal = dict(signal_time=frame.index[-1].isoformat(),
            eligible_at=(frame.index[-1]+pd.Timedelta(minutes=1)).isoformat(),
            side='long' if signal_values[-1] == 1 else 'short', reason='session_ended')
        if efficiency_values is not None:
            last_efficiency = float(efficiency_values[-1])
            terminal['efficiency_ratio_at_entry'] = last_efficiency if math.isfinite(last_efficiency) else None
        decisions.append(terminal)
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
    cfg = FuturesRecipe.model_validate(recipe).model_dump(mode='json', exclude_none=True)
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
