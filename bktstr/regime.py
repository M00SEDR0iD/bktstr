from __future__ import annotations

import pandas as pd

from .rules import parse_rules


SUBJECT_REGIME_FIELDS = {
    "day_close",
    "day_sma20",
    "day_sma50",
    "day_sma20_slope5",
    "day_return20",
}
BENCHMARK_FIELDS = {"benchmark_return20", "relative_return20"}
REGIME_FIELDS = SUBJECT_REGIME_FIELDS | BENCHMARK_FIELDS
_ALLOWED_REGIME_OPS = {"lt", "lte", "gt", "gte", "eq"}


def _daily_close_by_date(bars: pd.DataFrame) -> pd.Series:
    if "close" not in bars.columns:
        raise ValueError("daily bars missing close column")
    if bars.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    frame = bars.copy().sort_index()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("daily bars must use a DatetimeIndex")
    if frame.index.tz is None:
        local = frame.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = frame.index.tz_convert("America/New_York")
    dates = pd.DatetimeIndex([pd.Timestamp(value.date()) for value in local])
    close = pd.Series(frame["close"].astype(float).values, index=dates, name="close")
    return close[~close.index.duplicated(keep="last")].sort_index()


def build_daily_regime(
    subject_daily: pd.DataFrame,
    benchmark_daily: pd.DataFrame | None = None,
) -> pd.DataFrame:
    subject_close = _daily_close_by_date(subject_daily)
    regime = pd.DataFrame(index=subject_close.index)
    regime["day_close"] = subject_close
    regime["day_sma20"] = subject_close.rolling(20, min_periods=20).mean()
    regime["day_sma50"] = subject_close.rolling(50, min_periods=50).mean()
    regime["day_sma20_slope5"] = (regime["day_sma20"] / regime["day_sma20"].shift(5) - 1.0) * 100.0
    regime["day_return20"] = (subject_close / subject_close.shift(20) - 1.0) * 100.0

    if benchmark_daily is not None:
        benchmark_close = _daily_close_by_date(benchmark_daily)
        benchmark_return = (benchmark_close / benchmark_close.shift(20) - 1.0) * 100.0
        aligned_benchmark = benchmark_return.reindex(regime.index, method="ffill")
        regime["benchmark_return20"] = aligned_benchmark
        regime["relative_return20"] = regime["day_return20"] - aligned_benchmark

    return regime


def attach_regime_to_intraday(intraday: pd.DataFrame, daily_regime: pd.DataFrame) -> pd.DataFrame:
    frame = intraday.copy().sort_index()
    if frame.empty:
        for column in daily_regime.columns:
            frame[column] = pd.Series(dtype=float, index=frame.index)
        return frame
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("intraday bars must use a DatetimeIndex")
    if frame.index.tz is None:
        local = frame.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = frame.index.tz_convert("America/New_York")

    regime = daily_regime.sort_index()
    regime_dates = regime.index
    sessions = pd.DatetimeIndex([pd.Timestamp(value.date()) for value in local])
    unique_sessions = sessions.unique()

    session_rows: dict[pd.Timestamp, pd.Series | None] = {}
    for session_date in unique_sessions:
        position = int(regime_dates.searchsorted(session_date, side="left")) - 1
        session_rows[session_date] = regime.iloc[position] if position >= 0 else None

    for column in regime.columns:
        values = []
        for session_date in sessions:
            row = session_rows[session_date]
            values.append(float(row[column]) if row is not None and pd.notna(row[column]) else float("nan"))
        frame[column] = values
    return frame


def validate_regime_rules(spec: str, benchmark: str | None) -> None:
    rules = parse_rules(spec)
    for rule in rules:
        if rule.op not in _ALLOWED_REGIME_OPS:
            raise ValueError("cross operators are not supported in regime rules")
        if rule.left not in REGIME_FIELDS:
            raise ValueError(f"unsupported regime field '{rule.left}'")
        if isinstance(rule.right, str) and rule.right not in REGIME_FIELDS:
            raise ValueError(f"unsupported regime field '{rule.right}'")
        referenced = {rule.left}
        if isinstance(rule.right, str):
            referenced.add(rule.right)
        if referenced & BENCHMARK_FIELDS and not benchmark:
            raise ValueError("benchmark is required for benchmark regime fields")
