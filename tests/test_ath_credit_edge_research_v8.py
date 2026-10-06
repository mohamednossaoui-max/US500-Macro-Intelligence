import json
import numpy as np
import pandas as pd
import pytest
import ath_credit_edge_research_v8 as m


def payload(asof='2020-04-01',rows=None):
    return {'realtime_start':asof,'realtime_end':asof,'observations':[
        {'date':d,'value':v} for d,v in (rows or [('2020-03-31',2.5),('2020-02-28',2.)])]}


def meta():
    return {'id':m.SID,'frequency':'Daily','units':'Percent','seasonal_adjustment':'Not Seasonally Adjusted'}


def test_spread_difference_is_percentage_points_not_percent_return():
    r=m.features('2020-04-01',payload())
    assert r['baa_change_30_calendar_days_pp']==.5
    assert r['baseline_date']=='2020-02-28' and r['release_date'] is None


@pytest.mark.parametrize('rows',[
 [('2020-04-02',2),('2020-02-28',1)],
 [('2020-03-01',2),('2020-01-31',1)],
 [('2020-03-31',2),('2020-03-02',1)],
 [('2020-03-31',2),('2020-01-01',1)],
 [('2020-03-31',2),('2020-03-31',1)]])
def test_future_stale_missing_baseline_duplicate_rejected(rows):
    with pytest.raises(m.SourceError):m.features('2020-04-01',payload(rows=rows))


def test_current_data_cannot_replace_historical_vintage():
    with pytest.raises(m.SourceError):m.features('2020-04-01',payload(asof='2026-10-05'))
    with pytest.raises(m.SourceError):m.metadata({'seriess':[{**meta(),'units':'Basis Points'}]})


class Client:
    def get(self,endpoint,params):
        if endpoint=='series':return {'seriess':[meta()]}
        if endpoint=='series/vintagedates':return {'vintage_dates':['1990-01-01']}
        assert params['realtime_start']==params['realtime_end']=='2020-04-01'
        return payload()


def test_acquisition_idempotent_and_cached_values_revalidated(tmp_path):
    events=pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']*2})
    a=m.acquire(events,Client(),tmp_path);b=m.acquire(events,Client(),tmp_path)
    assert a==b and a['verified']==1
    assert len(list((tmp_path/'receipts').glob('*')))==1
    assert len(m.load_credit(tmp_path))==1
    p=next((tmp_path/'receipts').glob('*'));p.write_text(p.read_text()+' ')
    with pytest.raises(m.SourceError):m.load_credit(tmp_path)


def test_source_failure_never_becomes_verified(tmp_path):
    class Broken:
        def get(self,*a,**k):raise m.SourceError('HTTP 403')
    r=m.acquire(pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']}),Broken(),tmp_path)
    assert r['verified']==0 and r['status']=='FAILED_SOURCE_VALIDATION'
    assert r['live_forecast'] is None


def frame():
    rows=[]
    for i in range(16):
        d=pd.Timestamp('2019-01-01',tz='UTC')+pd.Timedelta(days=100*i)
        r={c:float(i+1) for c in m.base.MARKET+m.CREDIT}
        r.update(episode_id=str(i),decision_at=d.isoformat(),complete=True,
                 label_available_at=(d+pd.Timedelta(days=30)).isoformat(),class_label=m.base.CLASSES[i%4],horizon='3M')
        rows.append(r)
    return pd.DataFrame(rows)


def test_identical_cases_label_maturity_and_no_future_retraining():
    f=frame();a=m.evaluate(f)
    assert all(r['latest_training_label_available_at']<r['decision_at'] for r in a)
    changed=f.copy();changed.loc[15,m.CREDIT[0]]=1e9
    assert m.evaluate(changed)[:-1]==a[:-1]
    assert a==m.evaluate(f)
    for r in a:
        for name in ['price','market','credit_only','price_plus_credit','market_plus_credit','climatology']:
            assert sum(r[name+'_probabilities'])==pytest.approx(1.)
    f.loc[15,m.CREDIT]=np.nan
    assert m.evaluate(f)==a[:-1]


def test_missing_credit_blocks_not_neutral(tmp_path):
    f=frame();out,coverage=m.attach(f,{})
    assert out[m.CREDIT].isna().all().all()
    assert m.evaluate(out)==[]
    r=m.study(f,None,tmp_path)
    assert r['status']=='BLOCKED_INSUFFICIENT_VERIFIED_CREDIT'
    assert all(a['evaluations']==0 for a in r['analyses'])


def test_fixture_end_to_end_acquire_validate_study_repeat(tmp_path):
    class Historical(Client):
        def get(self,endpoint,params):
            if endpoint!='series/observations':return super().get(endpoint,params)
            asof=params['realtime_start'];assert asof==params['realtime_end']
            d=pd.Timestamp(asof);value=2+(d.year-2019)*.1
            return payload(asof,[(asof,value),((d-pd.Timedelta(days=30)).date().isoformat(),value-.1)])
    events=frame();cache=tmp_path/'vintages';out=tmp_path/'study'
    audit=m.acquire(events,Historical(),cache)
    assert audit['verified']==16 and audit['status']=='VERIFIED_AVAILABLE_ARCHIVE'
    result=m.study(events,cache,out)
    score=next(x for x in result['analyses'] if x['horizon']=='3M')
    assert score['evaluations']==4 and result['live_forecast'] is None
    before={p.name:p.read_bytes() for p in out.iterdir()}
    assert m.study(events,cache,out)==result
    assert before=={p.name:p.read_bytes() for p in out.iterdir()}
    assert m.acquire(events,Historical(),cache)==audit
    assert len(list((cache/'receipts').glob('*')))==16


def test_archive_gap_is_proven_and_not_source_success(tmp_path):
    class Late(Client):
        def get(self,endpoint,params):
            if endpoint=='series/vintagedates':return {'vintage_dates':['2021-01-01']}
            if endpoint=='series/observations':raise AssertionError('No unsupported vintage query')
            return super().get(endpoint,params)
    r=m.acquire(pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']}),Late(),tmp_path)
    assert r['results'][0]['status']=='UNAVAILABLE_ARCHIVE' and r['verified']==0
    assert r['status']=='FAILED_SOURCE_VALIDATION'


def historical_meta(asof, title='Baa Spread (DISCONTINUED)'):
    return {'realtime_start':asof,'realtime_end':asof,'seriess':[
        {**meta(),'title':title,'realtime_start':asof,'realtime_end':asof}]}


def test_provider_discontinuation_is_verified_and_excluded(tmp_path):
    class Stopped(Client):
        def get(self, endpoint, params):
            if endpoint=='series' and 'realtime_start' in params:
                return historical_meta(params['realtime_start'])
            if endpoint=='series/observations':
                return {'realtime_start':'2020-04-01','realtime_end':'2020-04-01','observations':[]}
            return super().get(endpoint,params)
    events=pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']})
    r=m.acquire(events,Stopped(),tmp_path)
    assert r['verified']==0 and r['status']=='FAILED_SOURCE_VALIDATION'
    assert r['results'][0]['status']=='UNAVAILABLE_PROVIDER_DISCONTINUED'
    assert len(m.load_lifecycle(tmp_path))==1
    out,coverage=m.attach(frame(),m.load_credit(tmp_path))
    assert out[m.CREDIT].isna().all().all()


def test_discontinued_gap_with_verified_cases_permits_available_archive_study(tmp_path):
    class Mixed(Client):
        def get(self,endpoint,params):
            if endpoint=='series' and 'realtime_start' in params:
                return historical_meta(params['realtime_start'])
            if endpoint=='series/observations' and params['realtime_start']=='2020-04-02':
                return {'realtime_start':'2020-04-02','realtime_end':'2020-04-02','observations':[]}
            return super().get(endpoint,params)
    events=pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00','2020-04-03T00:00:00+00:00']})
    r=m.acquire(events,Mixed(),tmp_path)
    assert r['status']=='VERIFIED_AVAILABLE_ARCHIVE' and r['verified']==1
    assert r['results'][1]['status']=='UNAVAILABLE_PROVIDER_DISCONTINUED'


@pytest.mark.parametrize('change',['current_date','active_title','wrong_series'])
def test_unproven_lifecycle_cannot_bypass_failure(change):
    p=historical_meta('2020-04-01')
    if change=='current_date':p['realtime_start']='2026-10-06'
    if change=='active_title':p['seriess'][0]['title']='Baa Spread'
    if change=='wrong_series':p['seriess'][0]['id']='OTHER'
    with pytest.raises(m.SourceError):m.discontinued('2020-04-01',p)


def test_lifecycle_tamper_rejected(tmp_path):
    m.lifecycle_receipt(tmp_path,'2020-04-01',historical_meta('2020-04-01'))
    p=next((tmp_path/'lifecycle_receipts').glob('*'));p.write_text(p.read_text()+' ')
    with pytest.raises(m.SourceError):m.load_lifecycle(tmp_path)
