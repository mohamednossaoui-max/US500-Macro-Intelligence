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
            if endpoint=='series/vintagedates':return {'vintage_dates':['1990-01-01']}
            assert params['realtime_start']==params['realtime_end']=='2020-04-01'
            assert params['observation_end']=='2020-04-01'
            if m.SERIES[sid][0]=='Monthly':return payload([('2020-03-01',110),('2020-02-01',100)])
            if sid=='A191RL1Q225SBEA':return payload([('2020-01-01',1)])
            return payload([('2020-03-31',1)])
    events=pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']*2})
    a=m.backfill(events,Good(),tmp_path);b=m.backfill(events,Good(),tmp_path)
    assert a==b and a['verified']==10 and len(list((tmp_path/'receipts').glob('*')))==10


def test_dff_requires_official_seven_day_semantics():
    row={'id':'DFF','frequency':'Daily, 7-Day','seasonal_adjustment':'Not Seasonally Adjusted','units':'Percent'}
    assert m.verify_metadata('DFF',{'seriess':[row]})['frequency']=='Daily, 7-Day'
    assert m.observation('DFF','2020-04-01',payload([('2020-03-31',1)]))['level']==1
    with pytest.raises(m.SourceError):m.verify_metadata('DFF',{'seriess':[{**row,'frequency':'Daily'}]})


def test_before_archive_is_not_http_error_or_current(tmp_path):
    class NoEarly:
        def get(self,endpoint,params):
            sid=params['series_id']
            if endpoint=='series':
                freq,sa,units,_=m.SERIES[sid]
                return {'seriess':[{'id':sid,'frequency':freq,'seasonal_adjustment':sa,'units':units}]}
            if endpoint=='series/vintagedates':return {'vintage_dates':['2021-01-01']}
            raise AssertionError('Must not request unsupported vintage')
    r=m.backfill(pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']}),NoEarly(),tmp_path)
    assert r['unavailable_archive']==10 and r['source_errors']==0 and r['verified']==0
    assert all(x['status']=='UNAVAILABLE_ARCHIVE' for x in r['results'])


def test_receipt_tampering_and_conflict_fail_closed(tmp_path):
    m.immutable_receipt(tmp_path,'UNRATE','2020-04-01',{'id':'UNRATE','frequency':'Monthly','seasonal_adjustment':'Seasonally Adjusted','units':'Percent'},payload([('2020-03-01',4)]))
    assert len(m.load_receipts(tmp_path))==1
    path=next((tmp_path/'receipts').glob('*'));path.write_text(path.read_text()+' ')
    with pytest.raises(m.SourceError):m.load_receipts(tmp_path)


def test_stale_response_retained_but_not_accepted(tmp_path):
    class Stale:
        def get(self,endpoint,params):
            sid=params['series_id']
            if endpoint=='series':
                freq,sa,units,_=m.SERIES[sid]
                return {'seriess':[{'id':sid,'frequency':freq,'seasonal_adjustment':sa,'units':units}]}
            if endpoint=='series/vintagedates':return {'vintage_dates':['1990-01-01']}
            return payload([('1990-01-01',1)])
    r=m.backfill(pd.DataFrame({'decision_at':['2020-04-02T00:00:00+00:00']}),Stale(),tmp_path)
    assert r['stale']==10 and r['verified']==0
    assert len(list((tmp_path/'receipts').glob('*')))==10


@pytest.mark.parametrize('asof,start,end,value,age',[
    ('2022-01-18','2021-07-01','2021-09-30',2.3,110),
    ('2024-07-24','2024-01-01','2024-03-31',1.4,115),
    ('2025-11-17','2025-04-01','2025-06-30',3.8,140)])
def test_gdp_age_is_measured_from_quarter_end(asof,start,end,value,age):
    r=m.observation('A191RL1Q225SBEA',asof,payload([(start,value)],asof))
    assert r['reference_period']==start and r['reference_period_end']==end
    assert r['age_since_reference_period_end_days']==age
    assert r['level']==value and r['release_date'] is None


def test_genuinely_old_gdp_and_unfinished_quarter_still_fail():
    for date in ('2019-01-01','2020-04-01'):
        with pytest.raises(m.SourceError):m.observation('A191RL1Q225SBEA','2020-04-01',payload([(date,1)]))


def test_partial_archive_policy_does_not_allow_stale_or_source_failure():
    report={'rows':2,'first_provider_vintages':{'DFF':'2005-06-28'},'results':[
        {'series':'UNRATE','decision_at':'2000-04-13','status':'ASOF_VERIFIED'},
        {'series':'DFF','decision_at':'2000-04-13','as_of_date':'2000-04-12','status':'UNAVAILABLE_ARCHIVE'}]}
    assert m.research_coverage(report)=='VERIFIED_AVAILABLE_ARCHIVE_PARTIAL_TOTAL'
    for status in ('STALE','SOURCE_ERROR','METADATA_UNVERIFIED'):
        report['results'][1]['status']=status
        assert m.research_coverage(report)=='FAILED_SOURCE_VALIDATION'
    report['results'][1]['status']='UNAVAILABLE_ARCHIVE';report['results'][1]['as_of_date']='2006-01-01'
    assert m.research_coverage(report)=='FAILED_SOURCE_VALIDATION'


def test_missing_index_month_preserves_exact_year_but_never_bridges_mom():
    r=m.observation('CPIAUCSL','2026-01-06',payload([
        ('2025-11-01',325.031),('2025-10-01','.'),('2025-09-01',324.368),
        ('2024-11-01',315)],'2026-01-06'))
    assert r['mom_pct'] is None
    assert r['yoy_sa_index_pct']==pytest.approx(100*(325.031/315-1))
    assert r['derived_field_statuses']['mom_pct']=='UNAVAILABLE_CONSECUTIVE_MONTH'
    assert r['release_date'] is None


def test_missing_exact_year_does_not_use_nearest_month():
    r=m.observation('INDPRO','2020-04-01',payload([('2020-02-01',110),('2020-01-01',100),('2019-01-01',90)]))
    assert r['yoy_sa_index_pct'] is None
    assert r['derived_field_statuses']['yoy_sa_index_pct']=='UNAVAILABLE_YEAR_REFERENCE'


def test_monthly_reference_age_uses_completed_period_end():
    r=m.observation('PCEPILFE','2026-01-06',payload([('2025-09-01',126.955),('2025-08-01',126.707)],'2026-01-06'))
    assert r['reference_period_end']=='2025-09-30'
    assert r['age_since_reference_period_end_days']==98
    for date in ('2025-08-01','2026-01-01','2025-09-15'):
        with pytest.raises(m.SourceError):m.observation('UNRATE','2026-01-06',payload([(date,4)],'2026-01-06'))
