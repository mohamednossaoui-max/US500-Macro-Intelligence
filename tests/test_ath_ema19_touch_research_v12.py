import json
import numpy as np
import pandas as pd
import pytest
import ath_ema19_touch_research_v12 as m


def base():
    c=100+np.arange(260)*.1;dates=pd.bdate_range('2000-01-03',periods=260,tz='UTC')
    return pd.DataFrame({'observation_date':dates.strftime('%Y-%m-%d'),
                         'availability_date':(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                         'Open':c,'High':c+.1,'Low':c-.1,'Close':c})


def append(raw,high,low,close):
    date=pd.Timestamp(raw.observation_date.iloc[-1])+pd.offsets.BDay(1)
    return pd.concat([raw,pd.DataFrame([dict(observation_date=date.date().isoformat(),
                    availability_date=(date+pd.Timedelta(days=1)).date().isoformat(),
                    Open=close,High=high,Low=low,Close=close)])],ignore_index=True)


def touch():
    raw=base();d=m.history(raw);ema=float(d.ema19.iloc[-1]);peak=float(d.High.max())
    return append(raw,peak-.01,ema-.1,ema+.1),peak,ema


def test_prior_day_ema_and_first_touch_only():
    raw,peak,ema=touch();raw=append(raw,peak-.02,ema-.2,ema+.2)
    selected,_=m.select(m.history(raw))
    assert len(selected)==1 and selected.touch_ema.iloc[0]==ema
    assert selected.touch_low.iloc[0]<ema


def test_selection_is_prefix_invariant():
    raw,peak,ema=touch();prefix=m.select(m.history(raw))[0]
    extended=append(raw,peak*1.1,peak*.9,peak*1.05)
    selected,_=m.select(m.history(extended))
    pd.testing.assert_frame_equal(prefix,selected[selected['index']<len(raw)].reset_index(drop=True))


def test_new_high_and_touch_same_day_is_unresolved():
    raw=base();d=m.history(raw);ema=d.ema19.iloc[-1];peak=d.High.max()
    selected,excluded=m.select(m.history(append(raw,peak+1,ema-.1,peak+.1)))
    assert selected.empty and excluded[-1]['status']=='TOUCH_AND_PEAK_RECOVERY_ORDER_UNRESOLVED'


def test_gap_below_is_not_range_touch():
    raw=base();ema=m.history(raw).ema19.iloc[-1]
    selected,excluded=m.select(m.history(append(raw,ema-.1,ema-1,ema-.5)))
    assert selected.empty and excluded[-1]['status']=='GAP_BELOW_EMA_NO_RANGE_TOUCH'


def test_future_recovery_and_target_order_excluded():
    raw,peak,ema=touch()
    raw=append(raw,peak+1,peak*.7,peak+.5)
    d=m.history(raw);selected,_=m.select(d);events=m.labels(d,selected)
    assert events.status.eq('INTRADAY_ORDER_UNRESOLVED').all()
    assert events.hit.isna().all()


def test_prior_target_hit_not_erased_by_later_ambiguous_recovery():
    raw,peak,ema=touch();raw=append(raw,peak-.5,peak*.89,peak*.95)
    raw=append(raw,peak+1,peak*.7,peak+.5)
    d=m.history(raw);selected,_=m.select(d);events=m.labels(d,selected)
    ten=events[events.target_pct.eq(10)].iloc[0]
    assert ten.eligible and ten.hit==1
    assert events[events.target_pct.eq(20)].status.iloc[0]=='INTRADAY_ORDER_UNRESOLVED'


def test_known_target_on_touch_day_not_future_forecast():
    raw=base();d=m.history(raw);ema=d.ema19.iloc[-1];peak=d.High.max()
    raw=append(raw,peak-.1,peak*.89,ema+.1)
    raw=append(raw,peak+1,peak-.1,peak+.5)
    d=m.history(raw);selected,_=m.select(d);events=m.labels(d,selected)
    assert events[events.target_pct.eq(10)].status.iloc[0]=='TARGET_ALREADY_REACHED'


def test_bad_ohlc_and_availability_fail_closed():
    raw=base();raw.loc[10,'Low']=raw.loc[10,'High']+1
    with pytest.raises(ValueError,match='OHLC'):m.history(raw)
    raw=base();raw.loc[10,'availability_date']=raw.loc[10,'observation_date']
    with pytest.raises(ValueError,match='availability'):m.history(raw)


def test_training_only_mature_earlier_labels():
    rows=[]
    for i in range(35):
        date=pd.Timestamp('2020-01-01',tz='UTC')+pd.Timedelta(days=3*i)
        rows.append(dict(event_id=str(i),cycle_id=str(i),target_pct=10,
                         decision_at=date.isoformat(),label_available_at=(date+pd.Timedelta(days=1)).isoformat(),
                         eligible=True,complete=True,hit=i%2,**{f:float(i%7) for f in m.FEATURES}))
    frame=pd.DataFrame(rows);frame.loc[0,'label_available_at']='2030-01-01T00:00:00+00:00'
    p=m.evaluate(frame)
    assert len(p)==4 and all(r['latest_training_label_at']<r['decision_at'] for r in p)
    assert all(r['training_count']>=30 for r in p)


def test_unmatured_event_has_no_negative_label():
    raw,peak,ema=touch();d=m.history(raw);selected,_=m.select(d);events=m.labels(d,selected)
    assert not events.complete.any() and events.hit.isna().all()


def test_acquisition_failure_cannot_claim_validated_ohlc(tmp_path):
    def fail(s,e):raise RuntimeError('HTTP 429')
    with pytest.raises(RuntimeError):m.acquire(tmp_path,fail)
    a=json.loads((tmp_path/'ohlc_acquisition_audit.json').read_text())
    assert a['status']=='SOURCE_ERROR' and a['fallback_used'] is False
    assert not (tmp_path/'ohlc.csv').exists()


def test_future_observations_cannot_enter_study(tmp_path):
    raw=base();raw.loc[0,'observation_date']='2100-01-01';raw.loc[0,'availability_date']='2100-01-02'
    with pytest.raises(ValueError,match='outside'):m.acquire(tmp_path,lambda s,e:raw)
    assert json.loads((tmp_path/'ohlc_acquisition_audit.json').read_text())['status']=='SOURCE_ERROR'


def test_fixture_full_path_and_repeat_outputs(tmp_path):
    def fixture(start,end):
        dates=m.gate.expected_sessions(start,end).index
        t=np.arange(len(dates));c=100+t*.03+3*np.sin(t/17)
        return pd.DataFrame({'observation_date':dates.strftime('%Y-%m-%d'),
                             'availability_date':(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                             'Open':c,'High':c+.3,'Low':c-.3,'Close':c})
    cache=tmp_path/'cache';output=tmp_path/'study';m.acquire(cache,fixture)
    a=m.study(cache,output)
    assert a['touch_events']>0 and a['live_forecast'] is None
    before={p.name:p.read_bytes() for p in output.iterdir()}
    m.study(cache,output)
    assert before=={p.name:p.read_bytes() for p in output.iterdir()}
    path=cache/'ohlc.csv';path.write_bytes(path.read_bytes()+b'\n')
    with pytest.raises(ValueError,match='changed'):m.study(cache,output)
