import numpy as np
import pandas as pd
import pytest
import ath_cause_depth_research_v1 as m
from ath_ema19_touch_research_v12 import history


def prices(tail):
    bars=[(100,100,99,100)]*21+tail
    d=pd.DataFrame(bars,columns=['Open','High','Low','Close'])
    dates=pd.bdate_range('2020-01-01',periods=len(d))
    d['observation_date']=dates.strftime('%Y-%m-%d');d['availability_date']=(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    return history(d)


def test_target_future_hit_and_wait_for_label_maturity():
    d=prices([(97,98,96,97),(95,96,94,95),(100,100,99,100)])
    e=m.events(d,warmup=20,horizon=3);r=e[e.target_pct==5].iloc[0]
    assert r.hit==1 and r.complete and r.label_available_at==d.available.iloc[-1].isoformat()


def test_same_bar_recovery_and_target_are_unknown():
    d=prices([(97,98,96,97),(99,101,94,99)])
    e=m.events(d,warmup=20,horizon=3);r=e[e.target_pct==5].iloc[0]
    assert not r.eligible and r.exclusion=='TARGET_RECOVERY_ORDER_UNKNOWN' and pd.isna(r.hit)


def test_previously_hit_target_remains_known_on_recovery_bar():
    d=prices([(97,98,96,97),(95,96,94,95),(99,101,94,99)])
    r=m.events(d,warmup=20,horizon=3).query('target_pct==5').iloc[0]
    assert r.eligible and r.hit==1


def test_already_reached_target_excluded():
    d=prices([(96,98,94,96),(100,100,99,100)])
    r=m.events(d,warmup=20,horizon=3).query('target_pct==5').iloc[0]
    assert not r.eligible and r.exclusion=='TARGET_ALREADY_REACHED'


def test_incomplete_negative_is_not_zero():
    d=prices([(97,98,96,97),(97,98,96,97)])
    r=m.events(d,warmup=20,horizon=63).iloc[0]
    assert not r.complete and r.hit is None


def test_first_landmark_once_per_cycle():
    d=prices([(97,98,96,97)]*4)
    e=m.events(d,warmup=20)
    assert e.event_id.nunique()==1 and len(e)==4


def test_future_receipts_do_not_fill_historical_causes():
    e=m.events(prices([(97,98,96,97)]*2),warmup=20)
    record={'available_at':'2026-01-01','snapshot_id':'fixture','payload':{'context_features':{},'feature_evidence':[]}}
    r=m.attach(e,[record])
    assert r[list(m.context.FEATURES)].isna().all().all()


def test_exact_capture_at_decision_not_available_before():
    e=m.events(prices([(97,98,96,97)]*2),warmup=20)
    record={'available_at':e.decision_at.iloc[0],'snapshot_id':'fixture','payload':{'context_features':{x:1 for x in m.context.FEATURES},'feature_evidence':[]}}
    assert m.attach(e,[record])[list(m.context.FEATURES)].isna().all().all()


def training():
    rows=[]
    for i in range(6):
        t=pd.Timestamp('2020-01-01',tz='UTC')+pd.Timedelta(days=90*i)
        rows.append({'event_id':str(i),'cycle_id':str(i),'decision_at':t.isoformat(),'label_available_at':(t+pd.Timedelta(days=10)).isoformat(),
                     'target_pct':5,'eligible':True,'complete':True,'hit':i%2,
                     **{x:float(i) for x in m.ALL_FEATURES}})
    return pd.DataFrame(rows)


def test_walkforward_strict_maturity_and_no_current_cycle():
    r=m.evaluate(training(),m.ALL_FEATURES,min_train=2)
    assert r and all(x['latest_training_label_at']<x['decision_at'] for x in r)
    assert all(x['training_count']<int(x['event_id'])+1 for x in r)


def test_context_and_baseline_use_common_sample():
    f=training();f.loc[2,'economic_inflation']=np.nan
    a=m.evaluate(f[f[list(m.context.FEATURES)].notna().all(axis=1)],m.PRICE_FEATURES,min_train=2)
    b=m.evaluate(f,m.ALL_FEATURES,min_train=2)
    assert [x['event_id'] for x in a]==[x['event_id'] for x in b]
    assert [x['training_count'] for x in a]==[x['training_count'] for x in b]


def test_missing_features_not_neutral_imputed():
    f=training();f['economic_inflation']=np.nan
    assert m.evaluate(f,m.ALL_FEATURES,min_train=2)==[]


def test_historical_research_never_certifies_live_probability():
    r=m.summarize(m.evaluate(training(),m.ALL_FEATURES,min_train=2))
    assert all(x['live_probability'] is None for x in r)
    assert m.PROTOCOL['live_forecast'] is None and m.PROTOCOL['research_only']
