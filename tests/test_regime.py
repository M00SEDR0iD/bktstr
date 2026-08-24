from datetime import date, timedelta
import pandas as pd
import pytest
from bktstr.regime import attach_regime_to_intraday, build_daily_regime, validate_regime_rules


def daily_bars(start, closes):
    cursor=date.fromisoformat(start); days=[]
    while len(days)<len(closes):
        if cursor.weekday()<5: days.append(cursor)
        cursor += timedelta(days=1)
    idx=pd.DatetimeIndex([pd.Timestamp(d.isoformat(),tz="America/New_York") for d in days])
    return pd.DataFrame({"open":closes,"high":[x+1 for x in closes],"low":[x-1 for x in closes],"close":closes,"volume":[1000.]*len(closes)},index=idx)


def test_daily_regime_features_and_relative_return():
    s=daily_bars("2026-01-02",[100+i for i in range(60)]); b=daily_bars("2026-01-02",[100+i*.5 for i in range(60)])
    r=build_daily_regime(s,b); last=r.iloc[-1]
    assert last.day_close==s.iloc[-1].close and last.day_sma20_slope5>0
    assert round(last.relative_return20,6)==round(last.day_return20-last.benchmark_return20,6)


def test_intraday_attachment_strictly_prior_day():
    d=daily_bars("2026-08-17",[100.,50.]); r=build_daily_regime(d)
    idx=pd.DatetimeIndex(["2026-08-18 13:00","2026-08-18 14:00"],tz="America/New_York")
    bars=pd.DataFrame({"open":[90.,89.],"high":[91.,90.],"low":[88.,87.],"close":[89.,88.],"volume":[1000.,1000.]},index=idx)
    out=attach_regime_to_intraday(bars,r)
    assert list(out.day_close)==[100.,100.]


def test_regime_validation_dependencies():
    validate_regime_rules("day_close.lt:day_sma20",benchmark=None)
    with pytest.raises(ValueError,match="benchmark is required"):
        validate_regime_rules("relative_return20.lt:0",benchmark=None)
    validate_regime_rules("relative_return20.lt:0",benchmark="SOXX")
    with pytest.raises(ValueError,match="sentiment=true"):
        validate_regime_rules("sentiment_fragility.gte:0.35",benchmark=None,sentiment_enabled=False)
    validate_regime_rules("sentiment_fragility.gte:0.35",benchmark=None,sentiment_enabled=True)
