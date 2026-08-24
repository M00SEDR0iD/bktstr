import math

import pandas as pd

from bktstr.sentiment import attach_sentiment_to_intraday, build_daily_sentiment


def _daily_frame(closes, start="2025-01-02"):
    idx = pd.date_range(start=start, periods=len(closes), freq="B", tz="America/New_York")
    closes = [float(v) for v in closes]
    return pd.DataFrame(
        {
            "open": closes,
            "high": [v + 1.0 for v in closes],
            "low": [v - 1.0 for v in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=idx,
    )


def test_build_daily_sentiment_exposes_raw_components_and_scores():
    n = 320
    subject = _daily_frame([100 + i * 0.5 for i in range(n)])
    sector = _daily_frame([100 + i * 0.2 for i in range(n)])
    market = _daily_frame([100 + i * 0.1 for i in range(n)])

    result = build_daily_sentiment(subject, sector, market)

    expected = {
        "relative_return63_sector",
        "relative_return126_sector",
        "relative_return63_market",
        "relative_return126_market",
        "distance_from_52w_high",
        "sma50_slope20",
        "sma100_slope20",
        "sma200_slope20",
        "days_below_sma50",
        "sentiment_leadership_score",
        "sentiment_trend_score",
        "sentiment_peak_score",
        "sentiment_persistence_score",
        "sentiment_direction",
        "sentiment_confidence",
        "sentiment_completeness",
        "sentiment_multiplier_long",
        "sentiment_multiplier_short",
    }
    assert expected.issubset(result.columns)
    last = result.iloc[-1]
    assert 0 < last["sentiment_direction"] <= 1
    assert 0 <= last["sentiment_confidence"] <= 1
    assert last["sentiment_completeness"] == 1.0
    assert 0.5 <= last["sentiment_multiplier_short"] < 1.0
    assert 1.0 < last["sentiment_multiplier_long"] <= 1.5


def test_bearish_history_scores_below_bullish_history():
    n = 320
    sector = _daily_frame([100 + i * 0.15 for i in range(n)])
    market = _daily_frame([100 + i * 0.1 for i in range(n)])
    bullish = _daily_frame([100 + i * 0.45 for i in range(n)])
    bearish = _daily_frame([220 - i * 0.4 for i in range(n)])

    bull_score = build_daily_sentiment(bullish, sector, market).iloc[-1]
    bear_score = build_daily_sentiment(bearish, sector, market).iloc[-1]

    assert bear_score["sentiment_direction"] < 0 < bull_score["sentiment_direction"]
    assert bear_score["sentiment_multiplier_short"] > 1.0
    assert bull_score["sentiment_multiplier_short"] < 1.0
    assert math.isclose(
        bear_score["sentiment_multiplier_long"] + bear_score["sentiment_multiplier_short"],
        2.0,
        rel_tol=0,
        abs_tol=1e-9,
    )


def test_missing_long_history_lowers_completeness_instead_of_invalidating_score():
    n = 90
    subject = _daily_frame([100 + i * 0.2 for i in range(n)])
    sector = _daily_frame([100 + i * 0.1 for i in range(n)])
    market = _daily_frame([100 + i * 0.05 for i in range(n)])

    last = build_daily_sentiment(subject, sector, market).iloc[-1]

    assert pd.notna(last["sentiment_direction"])
    assert 0 < last["sentiment_completeness"] < 1
    assert 0 <= last["sentiment_confidence"] <= last["sentiment_completeness"]


def test_attach_sentiment_uses_strictly_prior_completed_day():
    daily_idx = pd.DatetimeIndex(["2026-08-17", "2026-08-18"], tz="America/New_York")
    sentiment = pd.DataFrame(
        {
            "sentiment_direction": [-0.2, -0.9],
            "sentiment_confidence": [0.4, 0.8],
            "sentiment_multiplier_short": [1.04, 1.36],
        },
        index=daily_idx,
    )
    intraday_idx = pd.DatetimeIndex(
        ["2026-08-18 13:00", "2026-08-18 14:00"], tz="America/New_York"
    )
    intraday = pd.DataFrame(
        {"open": [100, 99], "high": [101, 100], "low": [98, 97], "close": [99, 98], "volume": [1000, 1000]},
        index=intraday_idx,
    )

    attached = attach_sentiment_to_intraday(intraday, sentiment)

    assert list(attached["sentiment_direction"]) == [-0.2, -0.2]
    assert list(attached["sentiment_confidence"]) == [0.4, 0.4]
