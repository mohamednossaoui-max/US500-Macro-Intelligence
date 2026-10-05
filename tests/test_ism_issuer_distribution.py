import json
import pandas as pd
import pytest
import economic_official_sources_v1 as sources

PROFILE='https://www.prnewswire.com/news/institute-for-supply-management/'
URL='https://www.prnewswire.com/news-releases/manufacturing-pmi-at-fixture.html'


def fixture(monkeypatch,issuer='Institute for Supply Management',stamp_shift=0,body_value=53.1,include_published=True,sector='Manufacturing'):
    url='https://www.prnewswire.com/news-releases/'+sector.lower()+'-pmi-at-fixture.html'
    released=pd.Timestamp.now(tz='America/New_York').tz_localize(None).normalize()-pd.Timedelta(days=1)
    reference=(pd.Period(released,freq='M')-1).strftime('%B %Y')
    title=f'{sector} PMI® at 53.1%; {reference} ISM® {sector} PMI® Report'
    stamp=(released.tz_localize('America/New_York')+pd.Timedelta(hours=10,days=stamp_shift)).isoformat()
    schema={'@type':'NewsArticle','headline':title,'mainEntityOfPage':{'@id':url},'dateModified':stamp}
    if include_published:schema['datePublished']=stamp
    article=f'<h1>{title}</h1><h2>News provided by</h2><a href="{PROFILE}">{issuer}</a><script type="application/ld+json">{json.dumps(schema)}</script><p>The {sector} PMI® registered {body_value} percent.</p>'
    profile=f'<h1>News from Institute for Supply Management</h1><a href="{url}">{title}</a>'
    monkeypatch.setattr(sources,'ism_latest_release',lambda c,k:(released,'https://www.ismworld.org/calendar'))
    class Client:
        def get(self,requested):
            assert requested in (PROFILE,url)
            return type('Response',(),{'text':profile if requested==PROFILE else article})()
    return Client(),reference,released


def test_issuer_distributed_release_preserves_provenance(monkeypatch):
    client,reference,rd=fixture(monkeypatch)
    row=sources.collect_ism_distributed_release(client,'ISM_MANUFACTURING_PMI','licensed redirect')[0]
    assert row['actual']==53.1 and row['reference_period']==reference
    assert row['release_date']==rd.strftime('%Y-%m-%d') and row['verification_status']=='VERIFIED'
    assert row['agency']=='ISM' and row['source_url']==URL
    assert row['source_distribution']=='PR Newswire' and row['source_alternate_reason']=='licensed redirect'


@pytest.mark.parametrize('kwargs,reason',[
    ({'issuer':'Another Institute'},'issuer'),
    ({'stamp_shift':-1},'latest official'),
    ({'body_value':53.2},'value mismatch'),
    ({'include_published':False},'published timestamp')])
def test_distributed_release_rejects_unverified_evidence(monkeypatch,kwargs,reason):
    client,_,_=fixture(monkeypatch,**kwargs)
    with pytest.raises(sources.MetadataError,match=reason):sources.collect_ism_distributed_release(client,'ISM_MANUFACTURING_PMI','source failed')


def test_services_fallback_from_stale_direct_report(monkeypatch):
    client,reference,rd=fixture(monkeypatch,sector='Services')
    def broken(c,i):raise sources.MetadataError('ISM current-report period differs from latest dated calendar release')
    monkeypatch.setattr(sources,'collect_ism',broken)
    row=sources.collect(client,'ISM_SERVICES_PMI')[0]
    assert row['reference_period']==reference and row['release_date']==rd.strftime('%Y-%m-%d')
    assert row['verification_status']=='VERIFIED' and row['actual']==53.1
    assert row['source_url'].endswith('/services-pmi-at-fixture.html')
    assert 'current-report period differs' in row['source_alternate_reason']


@pytest.mark.parametrize('kwargs,reason',[
    ({'issuer':'Another Institute'},'issuer'),
    ({'stamp_shift':-1},'latest official'),
    ({'body_value':53.2},'value mismatch'),
    ({'include_published':False},'published timestamp')])
def test_services_fallback_still_fails_closed(monkeypatch,kwargs,reason):
    client,_,_=fixture(monkeypatch,sector='Services',**kwargs)
    with pytest.raises(sources.MetadataError,match=reason):
        sources.collect_ism_distributed_release(client,'ISM_SERVICES_PMI','stale direct report')


def test_services_never_uses_manufacturing_article(monkeypatch):
    client,_,_=fixture(monkeypatch)
    with pytest.raises(sources.MetadataError,match='no services release'):
        sources.collect_ism_distributed_release(client,'ISM_SERVICES_PMI','direct failure')


def test_stale_seo_title_cannot_override_current_visible_report(monkeypatch):
    released=pd.Timestamp.now(tz='America/New_York').tz_localize(None).normalize()-pd.Timedelta(days=1)
    ref=pd.Period(released,freq='M')-1
    old=ref-12
    url='https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/current/'
    index=f'<a href="{url}">View Report</a>'
    html=f'<html><head><title>{old.strftime("%B %Y")} ISM Services PMI Report</title></head><body><nav>{old.strftime("%B %Y")} ISM Services PMI Report</nav><h1>{ref.strftime("%B %Y")} ISM Services PMI Report</h1><p>The Services PMI registered 53.1 percent.</p></body></html>'
    monkeypatch.setattr(sources,'ism_latest_release',lambda c,k:(released,'https://www.ismworld.org/calendar'))
    class Client:
        def get(self,requested):return type('Response',(),{'text':html if requested==url else index})()
    r=sources.collect_ism(Client(),'ISM_SERVICES_PMI')[0]
    assert r['reference_period']==ref.strftime('%B %Y') and r['actual']==53.1
    assert r['verification_status']=='VERIFIED'


def test_old_visible_report_still_rejected_despite_fresh_seo_title(monkeypatch):
    released=pd.Timestamp.now(tz='America/New_York').tz_localize(None).normalize()-pd.Timedelta(days=1)
    ref=pd.Period(released,freq='M')-1;old=ref-1
    url='https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/current/'
    html=f'<html><head><title>{ref.strftime("%B %Y")} ISM Services PMI Report</title></head><body><h1>{old.strftime("%B %Y")} ISM Services PMI Report</h1><p>The Services PMI registered 53.1 percent.</p></body></html>'
    monkeypatch.setattr(sources,'ism_latest_release',lambda c,k:(released,'https://www.ismworld.org/calendar'))
    class Client:
        def get(self,requested):return type('Response',(),{'text':html if requested==url else f'<a href="{url}">View Report</a>'})()
    with pytest.raises(sources.MetadataError,match='period differs'):
        sources.collect_ism(Client(),'ISM_SERVICES_PMI')
