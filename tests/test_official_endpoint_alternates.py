"""Alternate official documents must prove metadata and reject stale releases."""
from types import SimpleNamespace
import pandas as pd
import pytest
import requests
import economic_official_sources_v1 as sources


def forbidden(url):
    response=requests.Response();response.status_code=403;response.url=url
    response.request=requests.Request('GET',url).prepare()
    return requests.HTTPError(response=response)


class Response:
    def __init__(self,text='',payload=None):self.content=text.encode();self.payload=payload
    def json(self):return self.payload


@pytest.mark.parametrize('group,title,label',[
    ('empsit','THE EMPLOYMENT SITUATION','Employment Situation'),
    ('cpi','CONSUMER PRICE INDEX','Consumer Price Index'),
    ('ppi','PRODUCER PRICE INDEXES','Producer Price Index')])
def test_bls_blocked_feed_joins_published_text_and_calendar(group,title,label):
    released=pd.Timestamp.now(tz='America/New_York').normalize()-pd.Timedelta(days=1)
    reference=(pd.Period(released.tz_localize(None),freq='M')-1).strftime('%B %Y')
    text=f'<pre>Transmission of material is embargoed until USDL-00-0000 8:30 a.m. (ET) {released.strftime("%A, %B %d, %Y")} {title} - {reference}</pre>'
    calendar=''.join(f'BEGIN:VEVENT\nSUMMARY:{label}\nDTSTART;TZID=US-Eastern:{d.strftime("%Y%m%d")}T083000\nEND:VEVENT\n' for d in [released,released+pd.Timedelta(days=40)])
    class Client:
        def get(self,url):
            if '/feed/' in url:raise forbidden(url)
            return Response(calendar if url.endswith('.ics') else text)
    result=sources.bls_release_context(Client(),group)
    assert result[0]==reference and result[1]==released.strftime('%Y-%m-%d')
    assert result[2]=='8:30 AM ET' and result[4]['metadata_alternate_reason'].startswith('HTTPError status=403')


def test_bls_no_metadata_returns_unverified_values_not_current():
    class Client:
        def bls_payload(self,series):
            return {'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':series,'data':[{'year':'2026','period':'M09','value':'4.2'}]}]}}
        def get(self,url):raise forbidden(url)
    row=sources.collect_bls(Client(),'UNEMPLOYMENT_RATE')[0]
    assert row['actual']==4.2 and row['verification_status']=='METADATA_UNVERIFIED'
    assert row['release_date'] is None and 'status=403' in row['reason']


def test_bls_calendar_schedule_does_not_prove_publication():
    class Client:
        def get(self,url):
            if '/feed/' in url:raise forbidden(url)
            return Response('<pre>Publication delayed. No data have been released.</pre>')
    with pytest.raises(sources.MetadataError,match='date/reference'):sources.bls_release_context(Client(),'empsit')


def test_dol_blocked_current_discovers_archive_and_keeps_revision(monkeypatch):
    now=pd.Timestamp.now(tz='America/New_York');rd=now.normalize()-pd.Timedelta(days=(now.weekday()-3)%7)
    if rd+pd.Timedelta(hours=8,minutes=30)>now:rd-=pd.Timedelta(days=7)
    week=rd-pd.Timedelta(days=5)
    pdf_text=f'EMBARGOED UNTIL 8:30 A.M. (Eastern) {rd.strftime("%A, %B %d, %Y")} In the week ending {week.strftime("%B %d, %Y")}, the advance figure for seasonally adjusted initial claims was 200,000. The previous week\'s level was revised up by 1,000 from 199,000 to 200,000.'
    monkeypatch.setattr(sources,'PdfReader',lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:pdf_text)]))
    class Client:
        def get(self,url):
            if url=='https://www.dol.gov/ui/data.pdf':raise forbidden(url)
            return Response('published each week on Thursday' if url.endswith('claims_arch.asp') else 'PDF')
        def post_public_form(self,url,data):
            assert data['report']=='press'
            return Response(f'<a href="/press/{rd.year}/{rd.strftime("%m%d%y")}.pdf">Report</a>')
    rows=sources.collect_claims(Client())
    assert rows[-1]['actual']==200000 and rows[-1]['release_date']==rd.strftime('%Y-%m-%d')
    assert rows[0]['publication_status']=='REVISED'
    assert rows[-1]['source_url'].startswith('https://oui.doleta.gov/press/')
    assert rows[-1]['source_alternate_reason'].startswith('HTTPError status=403')


def test_census_time_is_predicate_only(monkeypatch):
    monkeypatch.setenv('CENSUS_API_KEY','TEST_ONLY_KEY')
    text='FOR RELEASE AT 8:30 AM EDT, WEDNESDAY, SEPTEMBER 16, 2026 ADVANCE MONTHLY SALES FOR RETAIL AND FOOD SERVICES, AUGUST 2026'
    monkeypatch.setattr(sources,'PdfReader',lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)]))
    class Client:
        def get(self,url,**kwargs):
            if url.endswith('.pdf'):return Response('PDF')
            params=kwargs['params']
            assert 'time' not in params['get'].split(',')
            assert 'time_slot_date' in params['get'].split(',') and ' to ' in params['time']
            assert params['category_code']=='44X72' and params['data_type_code']=='SM' and params['seasonally_adj']=='yes'
            return Response(payload=[['cell_value','time_slot_date','category_code','data_type_code','seasonally_adj'],['100','2026-07-01','44X72','SM','yes'],['102','2026-08-01','44X72','SM','yes']])
    row=sources.collect_retail(Client())[0]
    assert row['actual']==2 and row['reference_period']=='August 2026'


def test_bls_stale_published_page_fails_calendar_parity():
    released=pd.Timestamp.now(tz='America/New_York').normalize()-pd.Timedelta(days=1)
    stale=released-pd.Timedelta(days=30)
    text=f'<pre>Transmission is embargoed until 8:30 a.m. (ET) {stale.strftime("%A, %B %d, %Y")} THE EMPLOYMENT SITUATION - {stale.strftime("%B %Y")}</pre>'
    calendar=''.join(f'BEGIN:VEVENT\nSUMMARY:Employment Situation\nDTSTART;TZID=US-Eastern:{d.strftime("%Y%m%d")}T083000\nEND:VEVENT\n' for d in [released,released+pd.Timedelta(days=40)])
    class Client:
        def get(self,url):
            if '/feed/' in url:raise forbidden(url)
            return Response(calendar if url.endswith('.ics') else text)
    with pytest.raises(sources.MetadataError,match='differs from latest due'):sources.bls_release_context(Client(),'empsit')


def test_dol_stale_archive_fails_before_pdf_read():
    now=pd.Timestamp.now(tz='America/New_York');stale=now.normalize()-pd.Timedelta(days=30)
    class Client:
        def get(self,url):
            if url=='https://www.dol.gov/ui/data.pdf':raise forbidden(url)
            assert url.endswith('claims_arch.asp')
            return Response('published each week on Thursday')
        def post_public_form(self,url,data):
            return Response(f'<a href="/press/{stale.year}/{stale.strftime("%m%d%y")}.pdf">Report</a>')
    with pytest.raises(sources.MetadataError,match='older than latest'):sources.collect_claims(Client())
