import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from ath_depth_model_research_v1 import PRICE,PARTIAL,FULL,probabilities,walk_forward,attach,experiment,score


def sample(n=14):
    d=pd.DataFrame({'peak_date':pd.date_range('2000-01-01',periods=n,freq='YS').strftime('%Y-%m-%d'),
                    'label_end':(pd.date_range('2000-01-01',periods=n,freq='YS')+pd.DateOffset(months=3)).strftime('%Y-%m-%d'),
                    'complete':True,'intraday_ambiguous':False,
                    'class_lower':['LIMITED','MEDIUM','CRASH','NO_MEANINGFUL_PULLBACK']*(n//4)+['LIMITED']*(n%4)})
    for index,f in enumerate(FULL): d[f]=np.arange(n,dtype=float)+index
    return d


def test_labels_must_mature_before_each_prediction():
    d=sample();d.loc[0,'label_end']='2010-01-01'
    rows=walk_forward(d,min_train=2)
    assert all(r['training_latest_label_end'] < r['peak_date'] for r in rows)
    first=next(r for r in rows if r['peak_date']=='2003-01-01')
    assert first['training_rows']==2


def test_same_date_label_end_is_not_matured():
    d=sample(6);d.loc[0,'label_end']='2002-01-01'
    rows=walk_forward(d,min_train=1)
    at2002=next(r for r in rows if r['peak_date']=='2002-01-01')
    assert at2002['training_rows']==1


def test_future_outcomes_and_scaling_do_not_change_prior_predictions():
    d=sample();a=walk_forward(d)
    d.loc[12:,'class_lower']='CRASH';d.loc[12:,FULL]=1e12
    b=walk_forward(d)
    assert [r for r in a if r['peak_date']<'2012-01-01']==[r for r in b if r['peak_date']<'2012-01-01']


def test_models_use_same_training_rows_and_probabilities_are_normalized():
    d=sample();d.loc[0,'sentiment']=np.nan
    rows=walk_forward(d)
    for r in rows:
        assert r['training_rows']<=int(r['peak_date'][:4])-2001
        for key in ['price_probabilities','context_probabilities','climatology_probabilities']:
            assert sum(r[key])==pytest.approx(1)
            assert min(r[key])>0


def test_censored_and_intraday_ambiguous_outcomes_excluded():
    d=sample();d.loc[0,'complete']=False;d.loc[1,'intraday_ambiguous']=True
    rows=walk_forward(d,min_train=2)
    assert rows[0]['peak_date']=='2004-01-01'
    assert rows[0]['training_rows']==2


def test_strict_context_dates_false_flags_and_stale_values():
    anchors=pd.DataFrame({'peak_date':['2020-01-02','2020-01-03','2020-02-01']})
    source=pd.DataFrame({'available':['2020-01-01','2020-01-02'], 'value':[1,999],
                         'point_in_time_safe':['True','False']})
    result=attach(anchors,source,'available','value','feature',7)
    assert result.feature.iloc[0]==1
    assert result.feature.iloc[1:].isna().all()


def test_current_snapshot_cannot_backcast():
    anchors=pd.DataFrame({'peak_date':['2000-01-01']})
    source=pd.DataFrame({'available':['2026-10-03'],'value':[100],'point_in_time_safe':[True]})
    assert attach(anchors,source,'available','value','feature',7).feature.isna().all()


def test_missing_and_duplicate_metadata_fail_closed():
    anchors=pd.DataFrame({'peak_date':['2000-01-01']})
    assert attach(anchors,pd.DataFrame(),'available','value','feature',7).feature.isna().all()
    bad=pd.DataFrame({'available':['1999-01-01']*2,'value':[1,2],'point_in_time_safe':[True]*2})
    with pytest.raises(ValueError):attach(anchors,bad,'available','value','feature',7)


def test_unknown_features_are_not_neutralized():
    d=sample();d['sentiment']=np.nan
    assert walk_forward(d)==[]
    with pytest.raises(ValueError):probabilities(d,d.iloc[-1],PARTIAL)


def test_determinism_and_identical_features_zero_increment():
    d=sample()
    assert walk_forward(d)==walk_forward(d)
    r=walk_forward(d,PRICE)
    assert all(x['price_brier']==x['context_brier'] for x in r)
    assert score([0,1,0,0],'LIMITED')==0


def test_real_experiment_never_claims_high_confidence_or_live_forecast():
    root=Path(__file__).resolve().parents[1]
    a,events,predictions=experiment(root/'public_data',root/'research_history/ath_context_v1')
    assert a['forecast_status']=='NOT_VALIDATED'
    assert a['live_forecast'] is None
    assert a['incremental_edge_status']=='NOT_ESTABLISHED'
    assert events[['inflation','labor','growth','fed']].isna().all().all()
    assert all(r['training_latest_label_end'] < r['peak_date'] for r in predictions)
    json.dumps(a,allow_nan=False)


def test_ui_model_audit_is_explicitly_archival(tmp_path):
    from streamlit.testing.v1 import AppTest
    page=tmp_path/'page.py'
    root=Path(__file__).resolve().parents[1]
    page.write_text('from ath_pullback_context_ui_v1 import render_model_research\nrender_model_research('+repr(str(root/'public_data'))+')\n')
    app=AppTest.from_file(str(page)).run()
    assert not app.exception
