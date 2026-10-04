import numpy as np
import pandas as pd
import pytest
import ath_macro_edge_research_v4 as m
from ath_official_vintage_backfill_v1 import immutable_receipt,load_receipts


def test_exact_asof_only_no_future_macro(tmp_path):
    meta={'id':'UNRATE','frequency':'Monthly','seasonal_adjustment':'Seasonally Adjusted','units':'Percent'}
    payload={'realtime_start':'2020-04-01','realtime_end':'2020-04-01','observations':[{'date':'2020-03-01','value':'4'}]}
    immutable_receipt(tmp_path,'UNRATE','2020-04-01',meta,payload)
    frame=pd.DataFrame({'episode_id':['a','b'],'decision_at':['2020-04-02T00:00:00+00:00','2020-04-01T00:00:00+00:00']})
    out,coverage=m.attach(frame,load_receipts(tmp_path))
    assert out.loc[0,'unemployment_pct']==4 and np.isnan(out.loc[1,'unemployment_pct'])
    assert out.nfp_change_jobs.isna().all()
    assert len(coverage)==10


def test_walk_forward_labels_mature_and_future_change_does_not_retrain_past():
    rows=[]
    for i in range(16):
        d=pd.Timestamp('2019-01-01',tz='UTC')+pd.Timedelta(days=i*40)
        row={k:float(i+1) for k in set(m.COLUMNS+m.base.MARKET)}
        row.update(episode_id=str(i),decision_at=d.isoformat(),complete=True,
                   label_available_at=(d+pd.Timedelta(days=5)).isoformat(),class_label=m.base.CLASSES[i%3])
        rows.append(row)
    frame=pd.DataFrame(rows);a=m.evaluate(frame)
    assert all(x['latest_training_label_available_at']<x['decision_at'] for x in a)
    changed=frame.copy();changed.loc[15,'cpi_yoy_sa_pct']=1e9
    assert m.evaluate(changed)[:-1]==a[:-1]
    assert m.evaluate(frame)==a
    for x in a:assert sum(x['macro_probabilities'])==pytest.approx(1)
    frame.loc[:,'nfp_change_jobs']=np.nan
    assert m.evaluate(frame)==[]


def test_unverified_inputs_cannot_be_imputed_neutral():
    frame=pd.DataFrame({'episode_id':['a'],'decision_at':['2020-04-02T00:00:00+00:00']})
    out,checks=m.attach(frame,{})
    assert out[list(m.MACRO_FEATURES)].isna().all().all()
    assert all(x['status']=='UNAVAILABLE_RECEIPT' for x in checks)
