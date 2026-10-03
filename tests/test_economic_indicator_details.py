import importlib.util
import sys
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
import pytest
from economic_indicator_details_v1 import annual_bls,card_details,percent_change
from economic_official_ingestion_v1 import merge
from economic_official_sources_v1 import observation
from economic_pce_historical_backfill_v2 import parse_bea_release


def test_annual_uses_exact_twelve_month_baseline():
    rows=[dict(year='2025',period='M08',value='100'),dict(year='2026',period='M08',value='104.55'),dict(year='2026',period='M13',value='999')]
    assert annual_bls(rows,'August 2026')==4.6
    with pytest.raises(ValueError):annual_bls(rows,'September 2026')
    with pytest.raises(ValueError):annual_bls(rows[1:],'August 2026')
    with pytest.raises(ValueError):annual_bls(rows+[rows[0]],'August 2026')


def test_missing_annual_is_explicit_and_previous_formats_counts():
    prev,reading,annual=card_details(dict(indicator='NFP',actual=29000,previous=133000))
    assert '133,000' in prev and '29,000' in prev and 'lower' in reading and annual==''
    assert 'unavailable' in card_details(dict(indicator='CPI',actual=.4,previous=.2))[2]
    assert 'unchanged' in card_details(dict(indicator='CORE_PCE',actual=.2,previous=.2))[1]
    assert 'Prior published observation' in card_details(dict(indicator='CPI',actual=.4,delta_reference_value=.1))[0]


def test_gdp_never_labels_annualized_quarter_as_yoy():
    assert 'annualized quarterly' in card_details(dict(indicator='GDP',actual=2.2))[1]
    assert card_details(dict(indicator='GDP',actual=2.2))[2]==''
    assert 'Expansion' in card_details(dict(indicator='ISM_SERVICES_PMI',actual=55.4))[1]


def test_metadata_enrichment_preserves_pit_and_is_idempotent():
    old=observation('CPI','August 2026',.4,'2026-09-11','08:30 ET','https://www.bls.gov/',retrieved_at='2026-09-11T14:00:00+00:00')
    new=dict(old,yoy=3.5,mom=.4,previous=.2,yoy_verification_status='VERIFIED',latest_official_period='August 2026',retrieved_at='2026-10-03T20:00:00+00:00')
    events,q,n=merge(pd.DataFrame([old]),pd.DataFrame(),[new]);assert n==1 and len(events)==2
    assert pd.isna(events.iloc[0].yoy) and events.iloc[1].yoy==3.5
    assert events.iloc[1].ingestion_event_type=='METADATA_ENRICHMENT' and events.iloc[1].available_as_of=='2026-10-03'
    again,q2,n=merge(events,q,[new]);assert n==0 and len(again)==2
    from point_in_time import filter_available_as_of
    assert len(filter_available_as_of(events,'2026-10-02'))==1


def test_unverified_yoy_does_not_create_enrichment():
    old=observation('CPI','August 2026',.4,'2026-09-11','08:30 ET','https://www.bls.gov/',retrieved_at='2026-09-11T14:00:00+00:00')
    new=dict(old,yoy=999,yoy_verification_status='METADATA_UNVERIFIED',latest_official_period='August 2026')
    assert merge(pd.DataFrame([old]),pd.DataFrame(),[new])[2]==0


def test_bea_annual_separated_from_monthly():
    html='Personal Income and Outlays, August 2026 EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026 From the preceding month, the PCE price index for August increased 0.3 percent. Excluding food and energy, the PCE price index increased 0.2 percent. From the same month one year ago, the PCE price index for August increased 3.4 percent. Excluding food and energy, the PCE price index increased 3.0 percent from one year ago.'
    rows=parse_bea_release(html,'https://www.bea.gov/news/test')
    assert [(r['mom'],r['yoy'])for r in rows]==[(.3,3.4),(.2,3.0)]
    assert all(r['yoy_verification_status']=='VERIFIED'for r in rows)
    missing=parse_bea_release(html.split(' From the same month one year ago')[0],'https://www.bea.gov/news/test')
    assert all(r['yoy'] is None and r['yoy_verification_status']=='METADATA_UNVERIFIED'for r in missing)


def test_metadata_enrichment_not_extra_zscore_sample():
    path=Path(__file__).resolve().parents[1]/'economic_surprise_engine_v1.1.py'
    spec=importlib.util.spec_from_file_location('surprise_detail_test',path);mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    d=pd.DataFrame(dict(indicator=['CPI']*4,release_date=['2026-01-01','2026-02-01','2026-02-02','2026-03-01'],directional_release_shock=[1,2,2,3],metadata_only=[False,False,True,False]))
    z,count=mod.calculate_prior_zscore(d)
    assert count.iloc[-1]==2
    assert not mod.finalize_gdp_release_types(d).iloc[2].regime_eligible


def test_bls_annual_batch_is_separate_cached_and_key_not_saved(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from economic_official_sources_v1 import Client,BLS
    from economic_indicator_details_v1 import ANNUAL_BLS
    token='fixture-only-not-real';monkeypatch.setenv('BLS_API_KEY',token);calls=[]
    client=Client(tmp_path)
    def post(url,**kwargs):
        request=kwargs['json'];calls.append(request)
        return SimpleNamespace(raise_for_status=lambda:None,json=lambda:{'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':series,'data':[]} for series in request['seriesid']]}})
    monkeypatch.setattr(client.session,'post',post)
    for series in list(BLS.values()):client.bls_payload(series[0])
    for series in ANNUAL_BLS.values():client.bls_payload(series);client.bls_payload(series)
    assert len(calls)==2 and len(calls[0]['seriesid'])==7 and set(calls[1]['seriesid'])==set(ANNUAL_BLS.values())
    assert int(calls[1]['endyear'])-int(calls[1]['startyear'])==1
    assert all(token not in p.read_text() for p in tmp_path.iterdir())


def test_bls_monthly_and_nsa_annual_collector(monkeypatch):
    from types import SimpleNamespace
    import economic_official_sources_v1 as module
    def payload(series):
        rows=[dict(year='2025',period='M08',value='100'),dict(year='2026',period='M07',value='102'),dict(year='2026',period='M08',value='102.408')]
        if series=='CUUR0000SA0':rows=[dict(year='2025',period='M08',value='100'),dict(year='2026',period='M08',value='103.5')]
        return {'status':'REQUEST_SUCCEEDED','Results':{'series':[dict(seriesID=series,data=rows)]}}
    client=SimpleNamespace(bls_payload=payload)
    monkeypatch.setattr(module,'bls_release_context',lambda c,g:('August 2026','2026-09-11','08:30 ET','https://www.bls.gov/news.release/cpi.htm',{}))
    row=module.collect_bls(client,'CPI')[-1]
    assert row['actual']==row['mom']==.4 and row['yoy']==3.5 and row['yoy_source_series']=='CUUR0000SA0'
    assert row['yoy_verification_status']=='VERIFIED'
    client.bls_payload=lambda series:payload('CUSR0000SA0')
    row=module.collect_bls(client,'CPI')[-1]
    assert row['actual']==.4 and row['yoy'] is None and row['yoy_verification_status']=='METADATA_UNVERIFIED'


def test_latest_reference_wins_when_revisions_share_release_date():
    from economic_observation_order_v1 import latest
    rows=pd.DataFrame([dict(indicator='CPI',reference_period='August 2026',release_date='2026-09-11',actual=.4),dict(indicator='CPI',reference_period='July 2026',release_date='2026-09-11',actual=.1)])
    assert latest(rows,'CPI').reference_period=='August 2026'
