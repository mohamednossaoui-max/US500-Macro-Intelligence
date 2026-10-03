"""Release-aware FRED corroboration rejects lag, ambiguous dates and wrong series."""
import copy
import json
from types import SimpleNamespace
import pandas as pd
import pytest
import requests
import economic_official_sources_v1 as s
from economic_bls_fred_metadata_v1 import corroborate, SERIES, BASE
from economic_official_ingestion_v1 import compare
NOW=pd.Timestamp('2024-03-09',tz='America/New_York')


def fixture(indicator):
 sid,title,units=SERIES[indicator];code,group,_,_=s.BLS[indicator]
 records=[dict(year='2024',period='M02',value='110',footnotes=[]),dict(year='2024',period='M01',value='100',footnotes=[])]
 p={
 'series':{'seriess':[dict(id=sid,title=title,units=units,frequency='Monthly',seasonal_adjustment='Seasonally Adjusted',notes='Source code '+code,observation_end='2024-02-01',last_updated='2024-03-08 09:00:00-05:00')]},
 'series/release':{'releases':[dict(id=99,name={'empsit':'Employment Situation','cpi':'Consumer Price Index','ppi':'Producer Price Index'}[group],link='https://www.bls.gov/')]},
 'release/sources':{'sources':[dict(name='U.S. Bureau of Labor Statistics',link='https://www.bls.gov/')]},
 'release/dates':{'release_dates':[dict(release_id=99,date='2024-04-08'),dict(release_id=99,date='2024-03-08')]},
 'series/vintagedates':{'vintage_dates':['2024-03-08']},
 'series/observations':{'count':2,'observations':[dict(date='2024-02-01',value='110'),dict(date='2024-01-01',value='100')]}}
 class Client:
  def get(self,url,**kw):
   assert kw['params']['api_key']=='TEST_ONLY_KEY'
   if url==BASE+'series/observations':
    assert kw['params']['realtime_start']==kw['params']['realtime_end']=='2024-03-08'
    assert kw['params']['units']=='lin'
   return SimpleNamespace(json=lambda:copy.deepcopy(p[url[len(BASE):]]))
 return Client(),records,p


@pytest.mark.parametrize('indicator',list(SERIES))
def test_seven_mappings_and_distinct_dates(indicator,monkeypatch):
 monkeypatch.setenv('FRED_API_KEY','TEST_ONLY_KEY');c,r,_=fixture(indicator)
 period,rd,rt,url,extra=corroborate(c,indicator,r,'BLS HTTP403',now=NOW)
 assert period=='February 2024' and rd=='2024-03-08' and rt is None
 assert extra['metadata_provider']=='FRED_ALFRED' and extra['source_alternate_reason']=='BLS HTTP403'


@pytest.mark.parametrize('case,match',[
 ('nsa','semantics'),('source','not BLS'),('release','provenance'),('lag','latest vintage'),
 ('new_due','latest vintage'),('value','raw values'),('baseline','raw values'),('period','reference periods'),
 ('coverage','coverage'),('duplicate','duplicate'),('truncated','truncated'),('code','source-series'),('updated','published release')])
def test_false_current_rejected(case,match,monkeypatch):
 monkeypatch.setenv('FRED_API_KEY','TEST_ONLY_KEY');c,r,p=fixture('NFP')
 if case=='nsa':p['series']['seriess'][0]['seasonal_adjustment']='Not Seasonally Adjusted'
 if case=='source':p['release/sources']['sources'][0]['name']='Other'
 if case=='release':p['series/release']['releases'][0]['name']='Other'
 if case=='lag':p['series/vintagedates']['vintage_dates']=['2024-02-08']
 if case=='new_due':p['release/dates']['release_dates'].append(dict(release_id=99,date='2024-03-09'))
 if case=='value':p['series/observations']['observations'][0]['value']='111'
 if case=='baseline':p['series/observations']['observations'][1]['value']='101'
 if case=='period':p['series']['seriess'][0]['observation_end']='2024-01-01'
 if case=='coverage':p['release/dates']['release_dates']=p['release/dates']['release_dates'][1:]
 if case=='duplicate':p['series/observations']['observations'][1]['date']='2024-02-01'
 if case=='truncated':p['series/observations']['count']=3
 if case=='code':p['series']['seriess'][0]['notes']='Other'
 if case=='updated':p['series']['seriess'][0]['last_updated']='2024-03-10 09:00:00-05:00'
 with pytest.raises(s.MetadataError,match=match):corroborate(c,'NFP',r,'403',now=NOW)


def test_missing_key_no_requests(monkeypatch):
 monkeypatch.delenv('FRED_API_KEY',raising=False)
 with pytest.raises(s.MetadataError,match='requires FRED_API_KEY'):corroborate(None,'NFP',[],'403')


def collector_fixture(monkeypatch):
 monkeypatch.setenv('FRED_API_KEY','TEST_ONLY_KEY');c,r,p=fixture('NFP')
 c.bls_payload=lambda code:{'status':'REQUEST_SUCCEEDED','Results':{'series':[dict(seriesID=code,data=r)]}}
 def blocked(*a):raise s.MetadataError('BLS metadata unavailable')
 monkeypatch.setattr(s,'bls_release_context',blocked)
 import economic_bls_fred_metadata_v1 as alternate
 orig=alternate.corroborate
 monkeypatch.setattr(alternate,'corroborate',lambda *a:orig(*a,now=NOW))
 return c,p


def test_collector_value_stays_bls_and_metadata_exposed(monkeypatch):
 c,_=collector_fixture(monkeypatch);row=s.collect_bls(c,'NFP')[-1]
 assert row['actual']==10000 and row['release_date']=='2024-03-08'
 assert row['source_series']=='CES0000000001' and row['metadata_series']=='PAYEMS'
 assert row['release_time'] is None and row['release_time_verification']=='METADATA_UNVERIFIED'
 row['retrieved_at']='2024-03-09T12:00:00+00:00'
 report=compare(row,pd.DataFrame(columns=['indicator','reference_period','release_date','actual']))
 assert report['status']=='NEW_RELEASE' and report['metadata_provider']=='FRED_ALFRED'


def test_http_failure_preserves_value_no_date_no_key(monkeypatch):
 c,_=collector_fixture(monkeypatch)
 response=requests.Response();response.status_code=403;response.url=BASE+'series?api_key=TEST_ONLY_KEY'
 response.request=requests.Request('GET',response.url).prepare()
 def failed(*a,**kw):raise requests.HTTPError(response=response)
 c.get=failed;row=s.collect_bls(c,'NFP')[0]
 assert row['actual']==10000 and row['release_date'] is None and row['verification_status']=='METADATA_UNVERIFIED'
 assert 'TEST_ONLY_KEY' not in row['reason']


def test_evidence_cache_excludes_fred_secret(tmp_path):
 c=s.Client(tmp_path);response=SimpleNamespace(url=BASE+'series',content=b'{}',raise_for_status=lambda:None)
 c.session.get=lambda *a,**kw:response
 c.get(BASE+'series',params={'api_key':'KEY_A','series_id':'PAYEMS'});files=list(tmp_path.iterdir())
 c.get(BASE+'series',params={'api_key':'KEY_B','series_id':'PAYEMS'})
 assert list(tmp_path.iterdir())==files and len(c.cache)==1
