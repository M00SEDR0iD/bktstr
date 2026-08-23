from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from .rules import evaluate_rules, parse_rules


@dataclass(frozen=True)
class BacktestConfig:
    side: str = "long"
    entry_rules: str = "close.cross_above:vwap"
    stop_pct: float = 1.0
    target_pct: float = 3.0
    max_hold_minutes: int = 240
    position_size: float = 1000.0
    starting_capital: float = 10000.0
    slippage_bps: float = 2.0
    regular_hours_only: bool = True
    same_day_only: bool = True
    entry_start_time: str | None = None
    entry_end_time: str | None = None

    def __post_init__(self) -> None:
        if self.side not in {"long", "short"}:
            raise ValueError("side must be 'long' or 'short'")
        if self.stop_pct <= 0 or self.target_pct <= 0:
            raise ValueError("stop_pct and target_pct must be positive")
        if self.max_hold_minutes < 1:
            raise ValueError("max_hold_minutes must be positive")
        if self.position_size <= 0 or self.starting_capital <= 0:
            raise ValueError("capital values must be positive")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")
        start = _parse_market_time(self.entry_start_time)
        end = _parse_market_time(self.entry_end_time)
        if start is not None and end is not None and start >= end:
            raise ValueError("entry_start_time must be before entry_end_time")


def _parse_market_time(value: str | None):
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError as exc:
        raise ValueError("entry times must use 24-hour HH:MM format") from exc


def add_indicators(bars: pd.DataFrame) -> pd.DataFrame:
    frame = bars.copy().sort_index()
    if frame.index.tz is None:
        frame.index = frame.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        frame.index = frame.index.tz_convert("America/New_York")

    session = pd.Series(frame.index.date, index=frame.index)
    typical = (frame["high"] + frame["low"] + frame["close"]) / 3.0
    pv = typical * frame["volume"]
    cum_pv = pv.groupby(session).cumsum()
    cum_vol = frame["volume"].groupby(session).cumsum().replace(0, pd.NA)
    frame["vwap"] = cum_pv / cum_vol

    delta = frame["close"].diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    avg_loss = loss.ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    frame["rsi14"] = (100 - (100 / (1 + rs))).astype(float)

    rolling_volume = frame["volume"].rolling(20, min_periods=20).mean()
    frame["volume_ratio20"] = frame["volume"] / rolling_volume
    return frame


def _regular_hours(frame: pd.DataFrame) -> pd.DataFrame:
    times = frame.index.time
    start = pd.Timestamp("09:30").time()
    end = pd.Timestamp("16:00").time()
    mask = [(t >= start and t < end) for t in times]
    return frame.loc[mask]


def _apply_slippage(price: float, side: str, is_entry: bool, bps: float) -> float:
    slip = bps / 10000.0
    if side == "long":
        factor = 1 + slip if is_entry else 1 - slip
    else:
        factor = 1 - slip if is_entry else 1 + slip
    return float(price * factor)


def _round_money(value: float) -> float:
    return round(float(value), 6)


def run_backtest_on_bars(bars: pd.DataFrame, config: BacktestConfig) -> dict:
    if bars.empty:
        return {"summary": _empty_summary(config.starting_capital), "trades": []}
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"bars missing columns: {sorted(missing)}")

    frame = bars.copy().sort_index()
    if config.regular_hours_only:
        frame = _regular_hours(frame)
    frame = add_indicators(frame)
    if len(frame) < 2:
        return {"summary": _empty_summary(config.starting_capital), "trades": []}

    signal = evaluate_rules(frame, parse_rules(config.entry_rules))
    start_clock = _parse_market_time(config.entry_start_time)
    end_clock = _parse_market_time(config.entry_end_time)
    trades: list[dict] = []
    i = 0
    while i < len(frame) - 1:
        if not bool(signal.iloc[i]):
            i += 1
            continue

        entry_i = i + 1
        signal_ts = frame.index[i]
        entry_ts = frame.index[entry_i]
        if config.same_day_only and entry_ts.date() != signal_ts.date():
            i += 1
            continue
        entry_clock = entry_ts.time().replace(tzinfo=None)
        if start_clock is not None and entry_clock < start_clock:
            i += 1
            continue
        if end_clock is not None and entry_clock >= end_clock:
            i += 1
            continue

        raw_entry = float(frame.iloc[entry_i]["open"])
        entry = _apply_slippage(raw_entry, config.side, True, config.slippage_bps)
        shares = config.position_size / entry

        if config.side == "long":
            stop = entry * (1 - config.stop_pct / 100.0)
            target = entry * (1 + config.target_pct / 100.0)
        else:
            stop = entry * (1 + config.stop_pct / 100.0)
            target = entry * (1 - config.target_pct / 100.0)

        exit_i = entry_i
        raw_exit = float(frame.iloc[entry_i]["close"])
        exit_reason = "end_of_data"
        best_return = 0.0
        worst_return = 0.0

        j = entry_i
        while j < len(frame):
            row = frame.iloc[j]
            ts = frame.index[j]
            if config.same_day_only and ts.date() != entry_ts.date():
                prev = max(entry_i, j - 1)
                raw_exit = float(frame.iloc[prev]["close"])
                exit_i = prev
                exit_reason = "end_of_day"
                break

            high = float(row["high"])
            low = float(row["low"])
            if config.side == "long":
                favorable = (high - entry) / entry * 100.0
                adverse = (low - entry) / entry * 100.0
                stop_hit = low <= stop
                target_hit = high >= target
            else:
                favorable = (entry - low) / entry * 100.0
                adverse = (entry - high) / entry * 100.0
                stop_hit = high >= stop
                target_hit = low <= target
            best_return = max(best_return, favorable)
            worst_return = min(worst_return, adverse)

            # Conservative fill when both thresholds were touched inside one OHLC bar.
            if stop_hit:
                raw_exit = stop
                exit_i = j
                exit_reason = "stop"
                break
            if target_hit:
                raw_exit = target
                exit_i = j
                exit_reason = "target"
                break

            elapsed = (ts - entry_ts).total_seconds() / 60.0
            if elapsed >= config.max_hold_minutes:
                raw_exit = float(row["close"])
                exit_i = j
                exit_reason = "time"
                break
            if j == len(frame) - 1:
                raw_exit = float(row["close"])
                exit_i = j
                exit_reason = "end_of_data"
                break
            j += 1

        exit_price = _apply_slippage(raw_exit, config.side, False, config.slippage_bps)
        if config.side == "long":
            pnl = (exit_price - entry) * shares
        else:
            pnl = (entry - exit_price) * shares
        return_pct = pnl / config.position_size * 100.0
        exit_ts = frame.index[exit_i]
        trades.append(
            {
                "signal_time": signal_ts.isoformat(),
                "entry_time": entry_ts.isoformat(),
                "entry_price": _round_money(entry),
                "exit_time": exit_ts.isoformat(),
                "exit_price": _round_money(exit_price),
                "exit_reason": exit_reason,
                "side": config.side,
                "position_size": _round_money(config.position_size),
                "pnl_dollars": _round_money(pnl),
                "return_pct": _round_money(return_pct),
                "mfe_pct": _round_money(best_return),
                "mae_pct": _round_money(worst_return),
                "hold_minutes": int(round((exit_ts - entry_ts).total_seconds() / 60.0)),
            }
        )
        i = max(i + 1, exit_i + 1)

    return {"summary": _summarize(trades, config.starting_capital), "trades": trades}


def _empty_summary(starting_capital: float) -> dict:
    return {
        "trades": 0,
        "wins": 0,
        "losses": 0,
        "win_rate_pct": 0.0,
        "total_pnl_dollars": 0.0,
        "expected_pnl_per_trade": 0.0,
        "average_return_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "ending_equity": float(starting_capital),
    }


def _summarize(trades: list[dict], starting_capital: float) -> dict:
    if not trades:
        return _empty_summary(starting_capital)
    pnls = pd.Series([t["pnl_dollars"] for t in trades], dtype=float)
    returns = pd.Series([t["return_pct"] for t in trades], dtype=float)
    wins = int((pnls > 0).sum())
    losses = int((pnls <= 0).sum())
    equity = starting_capital + pnls.cumsum()
    peaks = pd.concat([pd.Series([starting_capital]), equity], ignore_index=True).cummax().iloc[1:].reset_index(drop=True)
    dd = (equity.reset_index(drop=True) - peaks) / peaks * 100.0
    return {
        "trades": int(len(trades)),
        "wins": wins,
        "losses": losses,
        "win_rate_pct": _round_money(wins / len(trades) * 100.0),
        "total_pnl_dollars": _round_money(pnls.sum()),
        "expected_pnl_per_trade": _round_money(pnls.mean()),
        "average_return_pct": _round_money(returns.mean()),
        "max_drawdown_pct": _round_money(dd.min()),
        "ending_equity": _round_money(starting_capital + pnls.sum()),
    }
