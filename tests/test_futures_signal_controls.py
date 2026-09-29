import pandas as pd
import pytest
from test_futures_execution import bars
from test_futures_opening import config, micro_terms, frame


def cfg(**changes):
    return config(execution_model='futures-ohlcv.1.2.0', cash_start_offset=0,
                  opening_bias=False, warmup_minutes=0, atr_period=None,
                  atr_reference_points=None, max_contracts=15,
                  max_hold_minutes=1) | changes


def prices(closes):
    return bars([[v,v+1,v-1,v,10] for v in closes])


@pytest.mark.parametrize('version',['1.0.0','1.1.0'])
@pytest.mark.parametrize('field,value',[('signal_period',5),('signal_period',None),
    ('efficiency_period',3),('efficiency_period',None),
    ('max_efficiency_ratio',.5),('max_efficiency_ratio',None)])
def test_old_models_reject_new_controls(version,field,value):
    from bktstr.futures_execution import FuturesRecipe
    from test_futures_execution import recipe
    base=recipe() if version=='1.0.0' else config()
    with pytest.raises(ValueError):
        FuturesRecipe.model_validate(base | {field:value})


@pytest.mark.parametrize('changes',[dict(signal_period=1),dict(signal_period=391),
    dict(efficiency_period=4),dict(max_efficiency_ratio=.5),
    dict(efficiency_period=1,max_efficiency_ratio=.5),
    dict(efficiency_period=4,max_efficiency_ratio=-.1),
    dict(efficiency_period=4,max_efficiency_ratio=1.1)])
def test_v12_controls_validate_pairs_and_bounds(changes):
    from bktstr.futures_execution import FuturesRecipe
    with pytest.raises(ValueError):FuturesRecipe.model_validate(cfg(**changes))


@pytest.mark.parametrize('kind,period,recovery',[('bollinger',5,6),('vwap',5,7),('rsi',3,7)])
def test_explicit_period_detects_known_recovery_and_is_causal(kind,period,recovery):
    from bktstr.futures_execution import signals
    values=[100]*5+[96,97,99,100,102,99,97,103,100,99,102,101,99,103,100]
    f=prices(values);threshold=30 if kind=='rsi' else 1
    c=cfg(signal={'kind':kind,'threshold':threshold},signal_period=period)
    assert signals(f,c)[recovery]==1
    assert list(signals(f,c)[:10])==list(signals(f.iloc[:10],c))
    changed=prices(values[:10]+[200+i for i in range(10)])
    assert list(signals(f,c)[:10])==list(signals(changed,c)[:10])
    default=cfg(signal={'kind':kind,'threshold':threshold})
    assert signals(f,default)[recovery]==0


def test_default_v12_preserves_v11_fills_signals_and_old_normalization():
    from bktstr.futures_execution import execute_session,signals,FuturesRecipe
    f=frame();f.loc[f.index[34]:,['open','high','low','close']]=[99,100,98,99]
    old=config(max_hold_minutes=1);new=old | {'execution_model':'futures-ohlcv.1.2.0'}
    events=[0]*len(f);events[34]=1;events[35]=1
    assert execute_session(f,events,old,micro_terms(),'MNQU6')==execute_session(f,events,new,micro_terms(),'MNQU6')
    for kind,t in [('bollinger',2),('vwap',1.5),('rsi',30)]:
        assert list(signals(f,old | {'signal':dict(kind=kind,threshold=t)}))==list(signals(f,new | {'signal':dict(kind=kind,threshold=t)}))
    assert FuturesRecipe.model_validate(old).model_dump(exclude_none=True)==old


def test_flat_window_accepts_zero_and_missing_history_rejects():
    from bktstr.futures_execution import execute_session
    f=prices([100]*6);events=[1,0,1,0,0,0]
    r=execute_session(f,events,cfg(efficiency_period=2,max_efficiency_ratio=0),micro_terms(),'MNQU6')
    assert r['decisions'][0]['reason']=='regime_unavailable'
    assert r['decisions'][0]['efficiency_ratio_at_entry'] is None
    assert r['trades'][0]['entry_time']==f.index[3].isoformat()
    assert r['trades'][0]['efficiency_ratio_at_entry']==0


def test_monotonic_window_rejects_and_equality_accepts():
    from bktstr.futures_execution import execute_session
    events=[0,0,1,0,0]
    r=execute_session(prices([100,101,102,103,104]),events,cfg(efficiency_period=2,max_efficiency_ratio=.5),micro_terms(),'MNQU6')
    assert r['trades']==[] and r['decisions'][0]['reason']=='trending_regime'
    assert r['decisions'][0]['efficiency_ratio_at_entry']==1
    r=execute_session(prices([100,102,101,101,101]),events,cfg(efficiency_period=2,max_efficiency_ratio=1/3),micro_terms(),'MNQU6')
    assert len(r['trades'])==1 and r['trades'][0]['efficiency_ratio_at_entry']==pytest.approx(1/3)


def test_entry_uses_prior_ratio_and_protection_continues():
    from bktstr.futures_execution import execute_session
    f=prices([100,100,100,103,70,70]);f.loc[f.index[4],['open','high','low','close']]=[103,104,69,70]
    events=[0,0,1,1,0,0]
    r=execute_session(f,events,cfg(efficiency_period=2,max_efficiency_ratio=0,max_hold_minutes=10),micro_terms(),'MNQU6')
    assert len(r['trades'])==1
    trade=r['trades'][0]
    assert trade['entry_time']==f.index[3].isoformat()
    assert trade['efficiency_ratio_at_entry']==0
    assert trade['reason']=='stop' and trade['exit_time']==f.index[4].isoformat()
    assert r['decisions'][1]['reason']=='position_open'
    assert r['decisions'][1]['efficiency_ratio_at_entry']==1
