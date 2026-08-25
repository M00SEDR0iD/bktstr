from datetime import date

import pandas as pd

from bktstr.service import BacktestRequest


def intraday_fixture() -> pd.DataFrame:
    index = pd.DatetimeIndex(
        [
            "2026-08-17 09:30:00",
            "2026-08-17 09:31:00",
            "2026-08-17 09:32:00",
        ],
        tz="America/New_York",
    )
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 98.0],
            "high": [101.0, 101.0, 99.0],
            "low": [99.0, 98.0, 96.0],
            "close": [101.0, 99.0, 97.0],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=index,
    )


def daily_fixture(start: date, end: date, base: float, slope: float) -> pd.DataFrame:
    index = pd.date_range(start=start, end=end, freq="B", tz="America/New_York")
    close = [base + offset * slope for offset in range(len(index))]
    return pd.DataFrame(
        {
            "open": close,
            "high": [value + 1.0 for value in close],
            "low": [value - 1.0 for value in close],
            "close": close,
            "volume": [1000.0] * len(index),
        },
        index=index,
    )


def baseline_request() -> BacktestRequest:
    return BacktestRequest.from_values(
        symbol="NVDA",
        start="2026-08-17",
        end="2026-08-17",
        timeframe="1m",
        side="short",
        entry="close.lt:1000",
        regime="day_sma20_slope5.lt:999,relative_return20.lt:999",
        benchmark="SOXX",
        sentiment=True,
        sentiment_sector_benchmark="SOXX",
        sentiment_market_benchmark="QQQ",
        stop_pct=10,
        target_pct=10,
        max_hold_minutes=1,
        slippage_bps=0,
    )
