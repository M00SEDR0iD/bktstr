from __future__ import annotations

import numpy as np
import pandas as pd


COMPONENT_WEIGHTS = {
    "sentiment_leadership_score": 0.35,
    "sentiment_trend_score": 0.30,
    "sentiment_peak_score": 0.20,
    "sentiment_persistence_score": 0.15,
}
SENTIMENT_OUTPUT_COLUMNS = [
    "sentiment_direction",
    "sentiment_confidence",
    "sentiment_completeness",
    "sentiment_multiplier_long",
    "sentiment_multiplier_short",
    *COMPONENT_WEIGHTS.keys(),
]


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


def _return_pct(close: pd.Series, periods: int) -> pd.Series:
    return (close / close.shift(periods) - 1.0) * 100.0


def _tanh_scaled(series: pd.Series, scale: float) -> pd.Series:
    return pd.Series(np.tanh(series.astype(float) / float(scale)), index=series.index, dtype=float)


def _mean_available(frame: pd.DataFrame) -> pd.Series:
    return frame.mean(axis=1, skipna=True)


def build_daily_sentiment(
    subject_daily: pd.DataFrame,
    sector_daily: pd.DataFrame,
    market_daily: pd.DataFrame,
) -> pd.DataFrame:
    subject_close = _daily_close_by_date(subject_daily)
    sector_close = _daily_close_by_date(sector_daily)
    market_close = _daily_close_by_date(market_daily)

    result = pd.DataFrame(index=subject_close.index)

    subject_return63 = _return_pct(subject_close, 63)
    subject_return126 = _return_pct(subject_close, 126)
    sector_return63 = _return_pct(sector_close, 63).reindex(result.index, method="ffill")
    sector_return126 = _return_pct(sector_close, 126).reindex(result.index, method="ffill")
    market_return63 = _return_pct(market_close, 63).reindex(result.index, method="ffill")
    market_return126 = _return_pct(market_close, 126).reindex(result.index, method="ffill")

    result["relative_return63_sector"] = subject_return63 - sector_return63
    result["relative_return126_sector"] = subject_return126 - sector_return126
    result["relative_return63_market"] = subject_return63 - market_return63
    result["relative_return126_market"] = subject_return126 - market_return126

    sma50 = subject_close.rolling(50, min_periods=50).mean()
    sma100 = subject_close.rolling(100, min_periods=100).mean()
    sma200 = subject_close.rolling(200, min_periods=200).mean()
    result["sma50_slope20"] = (sma50 / sma50.shift(20) - 1.0) * 100.0
    result["sma100_slope20"] = (sma100 / sma100.shift(20) - 1.0) * 100.0
    result["sma200_slope20"] = (sma200 / sma200.shift(20) - 1.0) * 100.0

    high52 = subject_close.rolling(252, min_periods=252).max()
    result["distance_from_52w_high"] = (subject_close / high52 - 1.0) * 100.0

    below50 = (subject_close < sma50).astype(float).where(sma50.notna())
    result["days_below_sma50"] = below50.rolling(20, min_periods=20).sum()

    leadership_inputs = pd.DataFrame(
        {
            "r63_sector": _tanh_scaled(result["relative_return63_sector"], 10.0),
            "r126_sector": _tanh_scaled(result["relative_return126_sector"], 20.0),
            "r63_market": _tanh_scaled(result["relative_return63_market"], 10.0),
            "r126_market": _tanh_scaled(result["relative_return126_market"], 20.0),
        },
        index=result.index,
    )
    result["sentiment_leadership_score"] = _mean_available(leadership_inputs)

    trend_inputs = pd.DataFrame(
        {
            "sma50": _tanh_scaled(result["sma50_slope20"], 5.0),
            "sma100": _tanh_scaled(result["sma100_slope20"], 4.0),
            "sma200": _tanh_scaled(result["sma200_slope20"], 3.0),
        },
        index=result.index,
    )
    result["sentiment_trend_score"] = _mean_available(trend_inputs)
    result["sentiment_peak_score"] = (1.0 + result["distance_from_52w_high"] / 20.0).clip(-1.0, 1.0)
    result["sentiment_persistence_score"] = (1.0 - result["days_below_sma50"] / 10.0).clip(-1.0, 1.0)

    components = result[list(COMPONENT_WEIGHTS)].copy()
    weights = pd.Series(COMPONENT_WEIGHTS, dtype=float)
    available = components.notna().astype(float)
    available_weight = available.mul(weights, axis=1).sum(axis=1)
    weighted_sum = components.fillna(0.0).mul(weights, axis=1).sum(axis=1)
    weighted_abs = components.abs().fillna(0.0).mul(weights, axis=1).sum(axis=1)

    direction = (weighted_sum / available_weight.replace(0.0, np.nan)).clip(-1.0, 1.0)
    mean_abs = weighted_abs / available_weight.replace(0.0, np.nan)
    completeness = available_weight.clip(0.0, 1.0).round(12)
    confidence = completeness * np.sqrt(direction.abs() * mean_abs.clip(lower=0.0))

    result["sentiment_direction"] = direction
    result["sentiment_completeness"] = completeness
    result["sentiment_confidence"] = confidence.clip(0.0, 1.0)
    adjustment = 0.5 * result["sentiment_direction"] * result["sentiment_confidence"]
    result["sentiment_multiplier_long"] = (1.0 + adjustment).clip(0.5, 1.5)
    result["sentiment_multiplier_short"] = (1.0 - adjustment).clip(0.5, 1.5)
    return result


def attach_sentiment_to_intraday(intraday: pd.DataFrame, daily_sentiment: pd.DataFrame) -> pd.DataFrame:
    frame = intraday.copy().sort_index()
    if frame.empty:
        for column in daily_sentiment.columns:
            frame[column] = pd.Series(dtype=float, index=frame.index)
        return frame
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("intraday bars must use a DatetimeIndex")
    if frame.index.tz is None:
        local = frame.index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = frame.index.tz_convert("America/New_York")

    sentiment = daily_sentiment.copy().sort_index()
    sentiment_dates = pd.DatetimeIndex([pd.Timestamp(value.date()) for value in sentiment.index])
    sentiment = sentiment.set_axis(sentiment_dates)
    sentiment = sentiment[~sentiment.index.duplicated(keep="last")].sort_index()
    sentiment_dates = sentiment.index

    sessions = pd.DatetimeIndex([pd.Timestamp(value.date()) for value in local])
    unique_sessions = sessions.unique()
    session_rows: dict[pd.Timestamp, pd.Series | None] = {}
    for session_date in unique_sessions:
        position = int(sentiment_dates.searchsorted(session_date, side="left")) - 1
        session_rows[session_date] = sentiment.iloc[position] if position >= 0 else None

    for column in sentiment.columns:
        values = []
        for session_date in sessions:
            row = session_rows[session_date]
            values.append(float(row[column]) if row is not None and pd.notna(row[column]) else float("nan"))
        frame[column] = values
    return frame
