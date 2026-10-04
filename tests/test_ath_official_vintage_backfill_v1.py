import json
import pandas as pd
import pytest
import ath_official_vintage_backfill_v1 as m


def payload(rows,asof='2020-04-01'):
    return {'realtime_start':asof,'realtime_end':asof,
            'observations':[{'date':d,'value':v} for d,v in rows]}


def test_payroll_levels_are_differenced_and_scaled():
    r=m.observation('PAYEMS','2020-04-01',payload([('2020-02-01','151000'),('2020-01-01','150800')]))
    assert r['monthly_change_jobs']==200000 and r['release_date'] is None


def test_monthly_gap_fails_not_bridged():
    with pytest.raises(m.SourceError):m.observation('PAYEMS','2020-04-01',payload([('2020-03-01',150),('2020-01-01',149)]))


def test_current_vintage_cannot_substitute_for_past():
    with pytest.raises(m.SourceError):m.observation('DFF','2020-04-01',payload([('2020-03-31',.1)],'2026-10-04'))


def test_future_observation_and_stale_fail():
    for date in ('2020-04-02','2019-01-01'):
        with pytest.raises(m.SourceError):m.observation('DFF','2020-04-01',payload([(date,1)]))


def test_index_mom_and_exact_year_reference():
    r=m.observation('CPIAUCSL','2020-04-01',payload([('2020-02-01',110),('2020-01-01',100),('2019-02-01',100)]))
    assert r['mom_pct']==pytest.approx(10) and r['yoy_sa_index_pct']==pytest.approx(10)


def test_semantics_change_fails():
    with pytest.raises(m.SourceError):m.verify_metadata('PAYEMS',{'seriess':[{'id':'PAYEMS','frequency':'Monthly','units':'Percent','seasonal_adjustment':'Seasonally Adjusted'}]})


def test_secret_never_in_exception():
    class Broken:
        def get(self,*args,**kwargs):raise RuntimeError('secret-key URL')
    with pytest.raises(m.SourceError) as e:m.Client('secret-key',Broken(),0).get('series',{})
    assert 'secret-key' not in str(e.value)


def test_receipts_preserve_revisions_and_no_duplicates(tmp_path):
    a=m.immutable_receipt(tmp_path,'DFF','2020-04-01',{},payload([('2020-03-31',1)]))
    assert a==m.immutable_receipt(tmp_path,'DFF','2020-04-01',{},payload([('2020-03-31',1)]))
    b=m.immutable_receipt(tmp_path,'DFF','2020-04-01',{},payload([('2020-03-31',2)]))
    assert a!=b and len(list((tmp_path/'receipts').glob('*.json')))==2


def test_source_failure_is_explicit_no_neutral_fallback(tmp_path):
    class Broken:
        def get(self,*args,**kwargs):raise m.SourceError('Official provider HTTP 403')
    r=m.backfill(pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']}),Broken(),tmp_path)
    assert r['source_errors']==10 and r['verified']==0 and r['live_forecast'] is None
    assert not list((tmp_path/'receipts').glob('*'))
    assert all(x['as_of_date']=='2020-04-01' for x in r['results'])


def test_backfill_asof_requests_and_idempotency(tmp_path):
    class Good:
        def get(self,endpoint,params):
            sid=params['series_id']
            if endpoint=='series':
                freq,sa,units,_=m.SERIES[sid]
                return {'seriess':[{'id':sid,'frequency':freq,'seasonal_adjustment':sa,'units':units}]}
            assert params['realtime_start']==params['realtime_end']=='2020-04-01'
            assert params['observation_end']=='2020-04-01'
            if m.SERIES[sid][0]=='Monthly':return payload([('2020-03-01',110),('2020-02-01',100)])
            return payload([('2020-03-31',1)])
    events=pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']*2})
    a=m.backfill(events,Good(),tmp_path);b=m.backfill(events,Good(),tmp_path)
    assert a==b and a['verified']==10 and len(list((tmp_path/'receipts').glob('*')))==10
