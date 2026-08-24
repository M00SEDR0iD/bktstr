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
    "sentiment_momentum20",
    "sentiment_momentum60",
    "sentiment_momentum",
    "sentiment_component_spread",
    "sentiment_volatility_stress",
    "sentiment_fragility",
    *COMPONENT_WEIGHTS.keys(),
]


def _local_dates(index: pd.DatetimeIndex) -> pd.DatetimeIndex:
    if index.tz is None:
        local = index.tz_localize("UTC").tz_convert("America/New_York")
    else:
        local = index.tz_convert("America/New_York")
    return pd.DatetimeIndex([pd.Timestamp(value.date()) for value in local])


def _daily_ohlc_by_date(bars: pd.DataFrame) -> pd.DataFrame:
    required = {"high", "low", "close"}
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"daily bars missing columns: {sorted(missing)}")
    if bars.empty:
        return pd.DataFrame(columns=["high", "low", "close"], index=pd.DatetimeIndex([]), dtype=float)
    frame = bars.copy().sort_index()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("daily bars must use a DatetimeIndex")
    frame = frame[["high", "low", "close"]].astype(float)
    frame.index = _local_dates(frame.index)
    return frame[~frame.index.duplicated(keep="last")].sort_index()


def _daily_close_by_date(bars: pd.DataFrame) -> pd.Series:
    if "close" not in bars.columns:
        raise ValueError("daily bars missing close column")
    if bars.empty:
        return pd.Series(dtype=float, index=pd.DatetimeIndex([]))
    frame = bars.copy().sort_index()
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise ValueError("daily bars must use a DatetimeIndex")
    dates = _local_dates(frame.index)
    close = pd.Series(frame["close"].astype(float).values, index=dates, name="close")
    return close[~close.index.duplicated(keep="last")].sort_index()


def _return_pct(close: pd.Series, periods: int) -> pd.Series:
    return (close / close.shift(periods) - 1.0) * 100.0


def _tanh_scaled(series: pd.Series, scale: float) -> pd.Series:
    return pd.Series(np.tanh(series.astype(float) / float(scale)), index=series.index, dtype=float)


def _mean_available(frame: pd.DataFrame) -> pd.Series:
    return frame.mean(axis=1, skipna=True)


def _weighted_available(frame: pd.DataFrame, weights: dict[str, float]) -> pd.Series:
    weight_series = pd.Series(weights, dtype=float)
    available = frame.notna().astype(float)
    denom = available.mul(weight_series, axis=1).sum(axis=1).replace(0.0, np.nan)
    numer = frame.fillna(0.0).mul(weight_series, axis=1).sum(axis=1)
    return numer / denom


def _atr20(ohlc: pd.DataFrame) -> pd.Series:
    previous_close = ohlc["close"].shift(1)
    true_range = pd.concat(
        [
            ohlc["high"] - ohlc["low"],
            (ohlc["high"] - previous_close).abs(),
            (ohlc["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return true_range.rolling(20, min_periods=20).mean()


def build_daily_sentiment(
    subject_daily: pd.DataFrame,
    sector_daily: pd.DataFrame,
    market_daily: pd.DataFrame,
) -> pd.DataFrame:
    subject_ohlc = _daily_ohlc_by_date(subject_daily)
    subject_close = subject_ohlc["close"]
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

    # Preserve the v0.3.1 slow-trend definition so v0.3.2 changes only persistence.
    sma50 = subject_close.rolling(50, min_periods=50).mean()
    sma100 = subject_close.rolling(100, min_periods=100).mean()
    sma200 = subject_close.rolling(200, min_periods=200).mean()
    result["sma50_slope20"] = (sma50 / sma50.shift(20) - 1.0) * 100.0
    result["sma100_slope20"] = (sma100 / sma100.shift(20) - 1.0) * 100.0
    result["sma200_slope20"] = (sma200 / sma200.shift(20) - 1.0) * 100.0

    high52 = subject_close.rolling(252, min_periods=252).max()
    result["distance_from_52w_high"] = (subject_close / high52 - 1.0) * 100.0

    # Legacy diagnostic remains exposed; the persistence score below no longer uses it.
    below50 = (subject_close < sma50).astype(float).where(sma50.notna())
    result["days_below_sma50"] = below50.rolling(20, min_periods=20).sum()

    # v0.3.2 clean transition features.
    ema50 = subject_close.ewm(span=50, adjust=False, min_periods=50).mean()
    ema100 = subject_close.ewm(span=100, adjust=False, min_periods=100).mean()
    ema200 = subject_close.ewm(span=200, adjust=False, min_periods=200).mean()
    result["ema50"] = ema50
    result["ema100"] = ema100
    result["ema200"] = ema200

    atr20 = _atr20(subject_ohlc)
    result["atr20_pct"] = (atr20 / subject_close) * 100.0
    daily_returns = subject_close.pct_change()
    result["realized_vol20"] = daily_returns.rolling(20, min_periods=20).std() * np.sqrt(252.0) * 100.0
    result["realized_vol60"] = daily_returns.rolling(60, min_periods=60).std() * np.sqrt(252.0) * 100.0
    result["volatility_ratio"] = result["realized_vol20"] / result["realized_vol60"].replace(0.0, np.nan)

    below_ema50 = (subject_close < ema50).astype(float).where(ema50.notna())
    result["persistence_occupancy"] = below_ema50.ewm(span=40, adjust=False, min_periods=20).mean()
    result["normalized_ema50_distance"] = (subject_close - ema50) / atr20.replace(0.0, np.nan)
    result["persistence_pressure_raw"] = result["normalized_ema50_distance"].ewm(
        span=40, adjust=False, min_periods=20
    ).mean()

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

    persistence_inputs = pd.DataFrame(
        {
            "occupancy": (1.0 - 2.0 * result["persistence_occupancy"]).clip(-1.0, 1.0),
            "pressure": np.tanh(result["persistence_pressure_raw"]),
        },
        index=result.index,
    )
    result["sentiment_persistence_score"] = _mean_available(persistence_inputs).clip(-1.0, 1.0)

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

    # Directional rate of change. These remain independent of confidence so a rapid
    # transition is visible even while the level components disagree.
    result["sentiment_momentum20"] = (result["sentiment_direction"] - result["sentiment_direction"].shift(20)).clip(-1.0, 1.0)
    result["sentiment_momentum60"] = (result["sentiment_direction"] - result["sentiment_direction"].shift(60)).clip(-1.0, 1.0)
    result["sentiment_momentum"] = _weighted_available(
        result[["sentiment_momentum20", "sentiment_momentum60"]],
        {"sentiment_momentum20": 0.65, "sentiment_momentum60": 0.35},
    ).clip(-1.0, 1.0)

    # Weighted component disagreement around the weighted sentiment level.
    centered_sq = components.sub(result["sentiment_direction"], axis=0).pow(2)
    variance = centered_sq.fillna(0.0).mul(weights, axis=1).sum(axis=1) / available_weight.replace(0.0, np.nan)
    result["sentiment_component_spread"] = np.sqrt(variance).clip(0.0, 1.0)

    volatility_expansion = ((result["volatility_ratio"] - 1.0) / 0.75).clip(0.0, 1.0)
    atr_baseline = result["atr20_pct"].rolling(60, min_periods=30).median()
    atr_expansion = ((result["atr20_pct"] / atr_baseline.replace(0.0, np.nan) - 1.0) / 0.75).clip(0.0, 1.0)
    result["sentiment_volatility_stress"] = _mean_available(
        pd.DataFrame({"vol_ratio": volatility_expansion, "atr_ratio": atr_expansion}, index=result.index)
    ).clip(0.0, 1.0)

    fragility_inputs = pd.DataFrame(
        {
            "spread": result["sentiment_component_spread"],
            "volatility": result["sentiment_volatility_stress"],
            "momentum": result["sentiment_momentum20"].abs(),
        },
        index=result.index,
    )
    result["sentiment_fragility"] = _weighted_available(
        fragility_inputs,
        {"spread": 0.50, "volatility": 0.30, "momentum": 0.20},
    ).clip(0.0, 1.0)
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
