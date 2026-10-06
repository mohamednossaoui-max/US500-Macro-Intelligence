import numpy as np
import pandas as pd
import pytest
import ath_breadth_comparison_research_v11 as m


def inputs():
    dates=pd.bdate_range('2020-01-01',periods=50,tz='UTC')
    prices=pd.DataFrame({'observation_date':dates.strftime('%Y-%m-%d')})
    raw=pd.DataFrame({'asof_date':prices.observation_date,'universe_count':100,
                      'price_eligible_count':100,'coverage_pct':100.,'advances':60,
                      'declines':40,'unchanged':0,'point_in_time_reconstructed':True,'cross_validated':True})
    return raw,prices


def test_quality_windows_cannot_impute_missing_or_low_coverage():
    raw,prices=inputs();raw.loc[25,'coverage_pct']=80;raw.loc[25,'price_eligible_count']=80
    raw.loc[25,'advances']=40;raw.loc[25,'declines']=40
    f,a=m.breadth_features(raw,prices)
    assert f.iloc[24].notna().all()
    assert f.iloc[25:45].isna().all().all()
    assert f.iloc[45].notna().all()
    raw,prices=inputs();raw=raw.drop(index=25)
    f,_=m.breadth_features(raw,prices)
    assert f.iloc[25:45].isna().all().all()


def test_feature_prefix_unchanged_by_future():
    raw,prices=inputs();full,_=m.breadth_features(raw,prices)
    past,_=m.breadth_features(raw.iloc[:30],prices.iloc[:30])
    pd.testing.assert_frame_equal(full.iloc[:30],past)


def test_bad_membership_flag_never_promoted():
    raw,prices=inputs();raw['point_in_time_reconstructed']='UNKNOWN'
    f,a=m.breadth_features(raw,prices)
    assert f.isna().all().all() and a['rows_meeting_quality_gate']==0
    assert a['membership_vintages_certified'] is False


def test_counts_coverage_and_duplicate_dates_validated():
    raw,prices=inputs();raw.loc[3,'advances']=61
    with pytest.raises(ValueError,match='counts'):m.breadth_features(raw,prices)
    raw,prices=inputs();raw.loc[3,'coverage_pct']=99
    with pytest.raises(ValueError,match='coverage'):m.breadth_features(raw,prices)
    raw,prices=inputs()
    with pytest.raises(ValueError,match='duplicate'):m.breadth_features(pd.concat([raw,raw.iloc[:1]]),prices)


def test_no_later_breadth_row_attached():
    raw,prices=inputs();f,_=m.breadth_features(raw,prices)
    f.iloc[-1]=999
    day=f.index[29]
    events=pd.DataFrame([dict(event_id='e',stage_pct=3,target_pct=5,decision_at=(day+pd.Timedelta(days=1)).isoformat())])
    attached,coverage=m.attach(events,f)
    assert attached[m.BREADTH].iloc[0].tolist()==[60.,20.]
    assert coverage[0]['availability_proxy']==events.decision_at.iloc[0]


def events():
    rows=[]
    for i in range(35):
        date=pd.Timestamp('2020-01-01',tz='UTC')+pd.Timedelta(days=i*3)
        rows.append(dict(event_id=str(i),cycle_id=str(i),decision_at=date.isoformat(),
                         label_available_at=(date+pd.Timedelta(days=1)).isoformat(),
                         stage_pct=3,target_pct=10,hit=i%2,eligible=True,complete=True,
                         **{f:float(i%7) for f in m.v9.FEATURES+m.BREADTH}))
    return pd.DataFrame(rows)


def test_common_sample_and_maturity_gate():
    e=events();e.loc[0,m.BREADTH[0]]=np.nan
    e.loc[1,'label_available_at']='2030-01-01T00:00:00+00:00'
    results=m.evaluate(e)
    assert len(results)==3
    assert all(r['training_count']>=30 and r['latest_training_label_at']<r['decision_at'] for r in results)
    assert all(k in results[0] for k in ['baseline_brier','price_brier','price_breadth_brier'])


def test_small_common_sample_explicitly_blocks_edge():
    e=events().iloc[:20];p=m.evaluate(e)
    assert p==[]
    summary=m.summarize(e,p)
    assert all(r['status']=='INSUFFICIENT_COMMON_SAMPLE' for r in summary)
    assert all(r['high_confidence_probability'] is None for r in summary)
