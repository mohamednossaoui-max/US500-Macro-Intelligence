import numpy as np
import pandas as pd
import ath_record_high_research_v6 as m


def history(values):
    dates=pd.date_range('2020-01-01',periods=len(values),tz='UTC')
    return m.old.history(pd.DataFrame({'observation_date':dates,'availability_date':dates+pd.Timedelta(days=1),
        'SP500':values,'VIX':20.,'NASDAQ':values,'DXY':100.,'US10Y':2.}))


def test_record_selection_is_past_only_and_calendar_spaced():
    data=history(100+np.arange(600)/10)
    anchors=m.cohort(data)
    prefix=m.cohort(data.iloc[:400])
    pd.testing.assert_frame_equal(prefix,anchors[anchors.anchor_index<400].reset_index(drop=True))
    assert anchors.anchor_index.iloc[0]==252
    for a,b in zip(anchors.decision_at,anchors.decision_at.iloc[1:]):
        assert pd.Timestamp(b)>pd.Timestamp(a)+pd.DateOffset(months=3)+pd.Timedelta(days=1)


def test_continuing_record_highs_are_not_excluded_by_future_outcome():
    data=history(100+np.arange(400)/10)
    anchors=m.cohort(data);events=m.labels(data,anchors)
    recovery=events[events.horizon.eq('UNTIL_RECOVERY')]
    assert recovery.class_label.eq('NO_MEANINGFUL_PULLBACK').all()
    assert recovery.depth_pct.eq(0).all()


def test_recovery_depth_and_label_availability():
    data=history(list(100+np.arange(252)/10)+[200,150,200])
    row=m.labels(data,m.cohort(data)).query("horizon=='UNTIL_RECOVERY'").iloc[0]
    assert row.depth_pct==25 and row.class_label=='CRASH' and row.complete
    assert row.label_available_at==data.iloc[-1].available.isoformat()


def test_incomplete_month_is_censored_and_not_training():
    data=history(100+np.arange(260)/10)
    events=m.labels(data,m.cohort(data));monthly=events[events.horizon.eq('1M')]
    assert not monthly.complete.any() and monthly.label_available_at.isna().all()
    assert m.evaluate(monthly)==[]


def test_monthly_metric_includes_drawdown_after_a_new_higher_peak():
    data=history(list(100+np.arange(252)/10)+[200,220,198]+[220]*100)
    row=m.labels(data,m.cohort(data)).query("horizon=='1M'").iloc[0]
    assert row.depth_pct==10 and row.class_label=='MEDIUM'


def test_walk_forward_respects_label_maturity_and_future_features():
    rows=[]
    for i in range(16):
        d=pd.Timestamp('2019-01-01',tz='UTC')+pd.Timedelta(days=100*i)
        r={k:float(i+1) for k in m.FULL}
        r.update(episode_id=str(i),decision_at=d.isoformat(),complete=True,
                 label_available_at=(d+pd.Timedelta(days=30)).isoformat(),class_label=m.CLASSES[i%4])
        rows.append(r)
    frame=pd.DataFrame(rows);original=m.evaluate(frame,True)
    assert all(r['latest_training_label_available_at']<r['decision_at'] for r in original)
    changed=frame.copy();changed.loc[15,'gdp_saar_pct']=1e9
    assert m.evaluate(changed,True)[:-1]==original[:-1]
    assert m.evaluate(frame,True)==original
    assert all(abs(sum(r['full_context_probabilities'])-1)<1e-10 for r in original)


def test_missing_context_is_not_neutral_and_blocks_full_model():
    frame=pd.DataFrame({'episode_id':['a'],'decision_at':['2020-04-02T00:00:00+00:00']})
    out,coverage=m.context(frame,{})
    assert out['effective_fed_rate_pct'].isna().all() and out['gdp_saar_pct'].isna().all()
    assert all(r['status']=='UNAVAILABLE_RECEIPT' for r in coverage)


def test_four_classes_do_not_force_a_pullback():
    assert [m.label(x) for x in (0,2.9,3,4.9,5,19.9,20)]==[
        'NO_MEANINGFUL_PULLBACK','NO_MEANINGFUL_PULLBACK','LIMITED','LIMITED','MEDIUM','MEDIUM','CRASH']
