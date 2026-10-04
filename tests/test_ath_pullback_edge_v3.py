import numpy as np
import pandas as pd
import pytest
import ath_pullback_edge_v3 as m


def prices(values):
    dates=pd.date_range('2020-01-01',periods=len(values),tz='UTC')
    return pd.DataFrame({'observation_date':dates,'availability_date':dates+pd.Timedelta(days=1),
                         'SP500':values,'VIX':20.,'NASDAQ':values,'DXY':100.,'US10Y':2.})


def test_availability_cannot_hide_future_price():
    f=prices([100,97]);f.loc[0,'availability_date']+=pd.Timedelta(days=5)
    with pytest.raises(ValueError):m.history(f)


def test_gap_and_early_episode_cannot_be_reentered():
    f=m.history(prices([100]*63+[94,97,99,101,97.5,98,101]))
    e=m.episodes(f)
    assert len(e)==2 and not e[0]['eligible'] and e[1]['eligible']
    assert e[1]['trigger_index']==67


def test_pending_recovery_not_trainable():
    f=m.history(prices([100]*63+[97,90,80]))
    row=m.event_table(f,'UNTIL_RECOVERY').iloc[0]
    assert not row.complete and row.class_label=='CRASH' and row.label_available_at is None


def test_months_are_calendar_and_include_activation_depth():
    f=m.history(prices([100]*63+[97]+[110]*100))
    row=m.event_table(f,'1M').iloc[0]
    assert row.depth_pct==3 and row.class_label=='LIMITED'
    assert pd.Timestamp(row.label_available_at)==pd.Timestamp(row.decision_at)+pd.DateOffset(months=1)+pd.Timedelta(days=1)


def test_official_vix_complete_or_fail_closed(tmp_path):
    f=m.history(prices([100,97]));p=tmp_path/'vix.csv'
    pd.DataFrame({'DATE':['01/01/2020','01/02/2020'],'CLOSE':[21,22]}).to_csv(p,index=False)
    corrected,receipt=m.official_vix(f,p)
    assert corrected.VIX.tolist()==[21,22] and f.VIX.tolist()==[20,20]
    assert receipt['vendor_differences_above_0_02']==2
    p.write_text('DATE,CLOSE\n01/01/2020,21\n')
    with pytest.raises(ValueError):m.official_vix(f,p)


def test_strict_label_maturity_and_determinism():
    rows=[]
    for i in range(16):
        d=pd.Timestamp('2019-01-01',tz='UTC')+pd.Timedelta(days=i*40)
        row={k:float(i+1) for k in m.MARKET}
        row.update(episode_id=str(i),decision_at=d.isoformat(),complete=True,
                   label_available_at=(d+pd.Timedelta(days=5)).isoformat(),class_label=m.CLASSES[i%3])
        rows.append(row)
    frame=pd.DataFrame(rows);a=m.evaluate(frame)
    assert a==m.evaluate(frame)
    assert all(x['training_latest_label_available_at']<x['decision_at'] for x in a)
    changed=frame.copy();changed.loc[15,'return20']=1e9
    assert m.evaluate(changed)[:-1]==a[:-1]
    assert all(abs(sum(x['market_probabilities'])-1)<1e-9 for x in a)


def test_insufficient_crashes_cannot_claim_edge():
    r=m.summary([])
    assert r['candidate_status']=='NO_CONFIRMED_EDGE' and r['live_probabilities'] is None
