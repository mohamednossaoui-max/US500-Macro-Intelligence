import json
import pandas as pd
import pytest
import economic_official_sources_v1 as sources

PROFILE='https://www.prnewswire.com/news/institute-for-supply-management/'
URL='https://www.prnewswire.com/news-releases/manufacturing-pmi-at-fixture.html'


def fixture(monkeypatch,issuer='Institute for Supply Management',stamp_shift=0,body_value=53.1,include_published=True):
    released=pd.Timestamp.now(tz='America/New_York').tz_localize(None).normalize()-pd.Timedelta(days=1)
    reference=(pd.Period(released,freq='M')-1).strftime('%B %Y')
    title=f'Manufacturing PMI® at 53.1%; {reference} ISM® Manufacturing PMI® Report'
    stamp=(released.tz_localize('America/New_York')+pd.Timedelta(hours=10,days=stamp_shift)).isoformat()
    schema={'@type':'NewsArticle','headline':title,'mainEntityOfPage':{'@id':URL},'dateModified':stamp}
    if include_published:schema['datePublished']=stamp
    article=f'<h1>{title}</h1><h2>News provided by</h2><a href="{PROFILE}">{issuer}</a><script type="application/ld+json">{json.dumps(schema)}</script><p>The Manufacturing PMI® registered {body_value} percent.</p>'
    profile=f'<h1>News from Institute for Supply Management</h1><a href="{URL}">{title}</a>'
    monkeypatch.setattr(sources,'ism_latest_release',lambda c,k:(released,'https://www.ismworld.org/calendar'))
    class Client:
        def get(self,url):
            assert url in (PROFILE,URL)
            return type('Response',(),{'text':profile if url==PROFILE else article})()
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
