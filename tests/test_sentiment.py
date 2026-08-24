import math
import pandas as pd
from bktstr.sentiment import attach_sentiment_to_intraday, build_daily_sentiment


def frame(closes,start="2025-01-02"):
    idx=pd.date_range(start=start,periods=len(closes),freq="B",tz="America/New_York"); closes=[float(x) for x in closes]
    return pd.DataFrame({"open":closes,"high":[x+1 for x in closes],"low":[x-1 for x in closes],"close":closes,"volume":[1000.]*len(closes)},index=idx)


def test_sentiment_exposes_components_transition_and_volatility():
    n=420; s=frame([100+i*.2+(2 if i%7==0 else 0) for i in range(n)]); sec=frame([100+i*.1 for i in range(n)]); m=frame([100+i*.08 for i in range(n)])
    out=build_daily_sentiment(s,sec,m); last=out.iloc[-1]
    for col in ["sentiment_direction","sentiment_confidence","sentiment_momentum","sentiment_component_spread","sentiment_volatility_stress","sentiment_fragility","ema50","atr20_pct","volatility_ratio","persistence_occupancy"]:
        assert col in out.columns and pd.notna(last[col])
    assert -1<=last.sentiment_direction<=1 and 0<=last.sentiment_fragility<=1


def test_bearish_history_scores_below_bullish():
    n=320; sec=frame([100+i*.15 for i in range(n)]); m=frame([100+i*.1 for i in range(n)])
    bull=build_daily_sentiment(frame([100+i*.45 for i in range(n)]),sec,m).iloc[-1]
    bear=build_daily_sentiment(frame([220-i*.4 for i in range(n)]),sec,m).iloc[-1]
    assert bear.sentiment_direction<0<bull.sentiment_direction
    assert bear.sentiment_multiplier_short>1>bull.sentiment_multiplier_short
    assert math.isclose(bear.sentiment_multiplier_long+bear.sentiment_multiplier_short,2,abs_tol=1e-9)


def test_short_history_degrades_completeness_not_score():
    n=90; out=build_daily_sentiment(frame([100+i*.2 for i in range(n)]),frame([100+i*.1 for i in range(n)]),frame([100+i*.05 for i in range(n)])).iloc[-1]
    assert pd.notna(out.sentiment_direction) and 0<out.sentiment_completeness<1


def test_attach_sentiment_uses_prior_day_only():
    idx=pd.DatetimeIndex(["2026-08-17","2026-08-18"],tz="America/New_York")
    s=pd.DataFrame({"sentiment_direction":[-.2,-.9],"sentiment_confidence":[.4,.8],"sentiment_fragility":[.8,.3]},index=idx)
    ii=pd.DatetimeIndex(["2026-08-18 13:00","2026-08-18 14:00"],tz="America/New_York")
    bars=pd.DataFrame({"open":[100,99],"high":[101,100],"low":[98,97],"close":[99,98],"volume":[1000,1000]},index=ii)
    out=attach_sentiment_to_intraday(bars,s)
    assert list(out.sentiment_direction)==[-.2,-.2] and list(out.sentiment_fragility)==[.8,.8]
