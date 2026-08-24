import pandas as pd
from bktstr.engine import BacktestConfig, run_backtest_on_bars


def bars(rows):
    idx=pd.to_datetime([r[0] for r in rows],utc=True).tz_convert("America/New_York")
    return pd.DataFrame({"open":[r[1] for r in rows],"high":[r[2] for r in rows],"low":[r[3] for r in rows],"close":[r[4] for r in rows],"volume":[r[5] for r in rows]},index=idx)


def test_short_enters_next_bar_and_hits_target():
    d=bars([("2026-08-03 13:30+00:00",100,101,99,101,1000),("2026-08-03 13:31+00:00",101,101,98,99,1000),("2026-08-03 13:32+00:00",98,99,96,97,1000),("2026-08-03 13:33+00:00",97,98,94,95,1000)])
    r=run_backtest_on_bars(d,BacktestConfig(side="short",entry_rules="close.cross_below:vwap",stop_pct=2,target_pct=3,max_hold_minutes=30,slippage_bps=0))
    t=r["trades"][0]; assert t["entry_price"]==98 and t["exit_reason"]=="target" and t["exit_price"]==95.06


def test_same_bar_stop_target_is_stop_first():
    d=bars([("2026-08-03 13:30+00:00",100,101,99,101,1000),("2026-08-03 13:31+00:00",101,101,98,99,1000),("2026-08-03 13:32+00:00",100,104,96,100,1000)])
    r=run_backtest_on_bars(d,BacktestConfig(side="short",entry_rules="close.cross_below:vwap",stop_pct=2,target_pct=2,max_hold_minutes=30,slippage_bps=0))
    assert r["trades"][0]["exit_reason"]=="stop"


def test_cross_does_not_bridge_sessions():
    d=bars([("2026-08-03 19:59+00:00",100,100,100,100,1000),("2026-08-04 13:30+00:00",100,110,90,95,1000),("2026-08-04 13:31+00:00",95,100,90,94,1000)])
    r=run_backtest_on_bars(d,BacktestConfig(side="short",entry_rules="close.cross_below:vwap",stop_pct=10,target_pct=10,max_hold_minutes=1,slippage_bps=0))
    assert r["summary"]["trades"]==0


def test_sentiment_metadata_does_not_resize_position():
    idx=pd.DatetimeIndex(["2026-08-18 13:00","2026-08-18 13:01","2026-08-18 13:02"],tz="America/New_York")
    d=pd.DataFrame({"open":[100.,99.,98.],"high":[100.,99.,98.],"low":[99.,98.,97.],"close":[99.5,98.5,97.5],"volume":[1000.]*3,"sentiment_direction":[-.6]*3,"sentiment_confidence":[.8]*3,"sentiment_completeness":[1.]*3,"sentiment_multiplier_long":[.76]*3,"sentiment_multiplier_short":[1.24]*3,"sentiment_fragility":[.65]*3,"sentiment_momentum":[-.43]*3},index=idx)
    r=run_backtest_on_bars(d,BacktestConfig(side="short",entry_rules="close.lt:1000",stop_pct=10,target_pct=10,max_hold_minutes=1,position_size=1000,slippage_bps=0))
    t=r["trades"][0]; assert t["position_size"]==1000 and t["sentiment_multiplier"]==1.24 and t["sentiment_fragility"]==.65
