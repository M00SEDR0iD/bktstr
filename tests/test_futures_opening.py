import pandas as pd
import pytest
from test_futures_execution import recipe, terms, bars


def config(**changes):
    return recipe() | dict(execution_model='futures-ohlcv.1.1.0', stop_points=25,
        reward_risk=1.52, risk_budget=500, max_contracts=30, commission_per_side=.5,
        warmup_minutes=5, opening_bias=True, cash_start_offset=30,
        quantity_step=5, atr_period=14, atr_reference_points=12.5) | changes


def micro_terms():
    return terms() | dict(multiplier=2, contracts={'2026-09-01':'MNQU6'})


def frame():
    f=bars([[100,105,95,100,10]]*45)
    f.index=pd.date_range('2026-09-01T13:00Z',periods=len(f),freq='min')
    return f


def test_opening_reference_direction_exact_start_and_no_cooldown():
    from bktstr.futures_execution import execute_session
    f=frame(); f.loc[f.index[30],['high','low']]=[110,90]
    # Opening midpoint 100; long below it. One-minute time exit then re-enter.
    f.loc[f.index[34]:,['open','high','low','close']]=[99,100,98,99]
    sig=[0]*len(f)
    for i in [30,33,34,35,36]:sig[i]=1
    r=execute_session(f,sig,config(max_hold_minutes=1),micro_terms(),'MNQU6')
    assert [t['entry_time'] for t in r['trades']]==[f.index[i].isoformat() for i in [35,36,37]]
    assert all(t['entry_time']!=f.index[34].isoformat() for t in r['trades'])
    assert all(t['fair_value']==100 for t in r['trades'])
    assert all(t['target_price']-t['entry_price']==38 for t in r['trades'])
    sig[34]=-1
    r=execute_session(f,sig,config(max_hold_minutes=1),micro_terms(),'MNQU6')
    assert next(d for d in r['decisions'] if d['eligible_at']==f.index[35].isoformat())['reason']=='opening_direction'


def test_volatility_sizing_is_causal_integer_and_frozen_during_trade():
    from bktstr.futures_execution import execute_session
    f=frame();f.loc[f.index[35]:,['open','high','low','close']]=[99,100,98,99]
    f.loc[f.index[34],'close']=99
    sig=[0]*len(f);sig[34]=1
    r=execute_session(f,sig,config(),micro_terms(),'MNQU6')
    t=r['trades'][0]
    assert t['atr_at_entry']==10
    assert t['contracts']==10  # floor(500/(25*2) *12.5/10) to a multiple of five
    assert t['initial_risk_dollars']==500
    altered=f.copy();altered.loc[altered.index[36]:,'high']=150
    u=execute_session(altered,sig,config(),micro_terms(),'MNQU6')['trades'][0]
    assert (u['contracts'],u['atr_at_entry'])==(t['contracts'],t['atr_at_entry'])
    wide=f.copy();wide.loc[wide.index[:35],['high','low']]=[110,90]
    assert execute_session(wide,sig,config(),micro_terms(),'MNQU6')['trades'][0]['contracts']==5


def test_entry_gap_cannot_reverse_opening_bias_and_v1_fields_rejected():
    from bktstr.futures_execution import execute_session, FuturesRecipe
    f=frame();f.loc[f.index[34],['open','high','low','close']]=[99,100,98,99]
    f.loc[f.index[35],['open','high','low','close']]=[102,103,101,102]
    sig=[0]*len(f);sig[34]=1
    r=execute_session(f,sig,config(),micro_terms(),'MNQU6')
    assert r['trades']==[] and r['decisions'][-1]['reason']=='opening_direction'
    with pytest.raises(ValueError):FuturesRecipe.model_validate(config(execution_model='futures-ohlcv.1.0.0'))


def test_premarket_warms_indicators_but_session_vwap_starts_at_cash_open():
    from bktstr.futures_execution import signals
    f=frame();cfg=config(signal={'kind':'vwap','threshold':1.5})
    assert list(signals(f,cfg)[:36])==list(signals(f.iloc[:36],cfg))
    g=f.copy();g.loc[g.index[:30],'volume']=1000000
    assert list(signals(f,cfg)[30:])==list(signals(g,cfg)[30:])


def test_v1_preserves_decimal_floor_division_quantity():
    from bktstr.futures_execution import execute_session
    f=bars([[100,100.5,99.5,100,10]]*3)
    cfg=recipe() | dict(risk_budget=1,stop_points=1,max_contracts=20)
    result=execute_session(f,[1,0,0],cfg,terms() | dict(multiplier=.1),'NQU6')
    assert result['trades'][0]['contracts']==9
