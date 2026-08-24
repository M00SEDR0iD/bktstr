from datetime import date, timedelta

import pandas as pd
import pytest

from bktstr.regime import (
    attach_regime_to_intraday,
    build_daily_regime,
    validate_regime_rules,
)


def daily_bars(start: str, closes: list[float]) -> pd.DataFrame:
    start_date = date.fromisoformat(start)
    days = []
    cursor = start_date
    while len(days) < len(closes):
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    index = pd.DatetimeIndex(
        [pd.Timestamp(day.isoformat(), tz="America/New_York") for day in days]
    )
    return pd.DataFrame(
        {
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
        },
        index=index,
    )


def test_daily_regime_builds_subject_and_benchmark_features():
    subject = daily_bars("2026-01-02", [100 + i for i in range(60)])
    benchmark = daily_bars("2026-01-02", [100 + i * 0.5 for i in range(60)])

    regime = build_daily_regime(subject, benchmark)
    last = regime.iloc[-1]

    assert last["day_close"] == subject.iloc[-1]["close"]
    assert round(last["day_sma20"], 6) == round(subject["close"].tail(20).mean(), 6)
    assert round(last["day_sma50"], 6) == round(subject["close"].tail(50).mean(), 6)
    expected_return = (subject.iloc[-1]["close"] / subject.iloc[-21]["close"] - 1) * 100
    benchmark_return = (benchmark.iloc[-1]["close"] / benchmark.iloc[-21]["close"] - 1) * 100
    assert round(last["day_return20"], 6) == round(expected_return, 6)
    assert round(last["benchmark_return20"], 6) == round(benchmark_return, 6)
    assert round(last["relative_return20"], 6) == round(expected_return - benchmark_return, 6)
    assert last["day_sma20_slope5"] > 0


def test_intraday_attachment_uses_strictly_prior_daily_session():
    daily = daily_bars("2026-08-17", [100.0, 50.0])  # Monday, Tuesday
    regime = build_daily_regime(daily)
    intraday_index = pd.DatetimeIndex(
        ["2026-08-18 13:00:00", "2026-08-18 14:00:00"],
        tz="America/New_York",
    )
    intraday = pd.DataFrame(
        {
            "open": [90.0, 89.0],
            "high": [91.0, 90.0],
            "low": [88.0, 87.0],
            "close": [89.0, 88.0],
            "volume": [1000.0, 1000.0],
        },
        index=intraday_index,
    )

    attached = attach_regime_to_intraday(intraday, regime)

    assert list(attached["day_close"]) == [100.0, 100.0]


def test_regime_rule_validation_requires_benchmark_for_benchmark_fields():
    validate_regime_rules("day_close.lt:day_sma20", benchmark=None)

    with pytest.raises(ValueError, match="benchmark is required"):
        validate_regime_rules("relative_return20.lt:0", benchmark=None)

    validate_regime_rules("relative_return20.lt:0", benchmark="SOXX")


def test_regime_rule_validation_rejects_intraday_fields_and_cross_ops():
    with pytest.raises(ValueError, match="unsupported regime field"):
        validate_regime_rules("close.lt:day_sma20", benchmark=None)

    with pytest.raises(ValueError, match="cross operators"):
        validate_regime_rules("day_close.cross_below:day_sma20", benchmark=None)
