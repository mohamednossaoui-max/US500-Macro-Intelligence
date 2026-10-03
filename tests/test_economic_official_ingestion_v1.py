from datetime import datetime,timezone
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pandas as pd
import pytest
from economic_official_ingestion_v1 import compare,merge,run,assert_current,validate_batch,EVENTS,QUALITY
from economic_official_sources_v1 import transform_bls,observation,MAPPINGS,bls_context,release_timestamp,MetadataError
from point_in_time import filter_available_as_of
ROOT=Path(__file__).resolve().parents[1]
NOW=datetime(2026,10,2,20,tzinfo=timezone.utc)


def row(indicator='NFP',value=100,period='September 2026',release='2026-10-02'):
    return observation(indicator,period,value,release,'08:30 ET',MAPPINGS[indicator]['url'],retrieved_at=NOW.isoformat())


def base():
    return pd.DataFrame([row(value=10,period='August 2026',release='2026-09-04')])


def quality():return pd.DataFrame(columns=['record_id','indicator','agency','release_date','reference_period','point_in_time_safe','quality_issues','historical_consensus_available'])


def test_new_release_and_same_release():
    b=base();r=row();assert compare(r,b)['status']=='NEW_RELEASE'
    events,q,n=merge(b,quality(),[r]);assert n==1
    assert compare(r,events)['status']=='CURRENT'
    assert_current(events,[compare(r,events)])


def test_revision_preserves_prior_vintage_and_pit():
    b=base();r=row(value=12,period='August 2026')
    assert compare(r,b)['status']=='REVISION'
    events,q,n=merge(b,quality(),[r]);assert events.actual.tolist()==[10,12]
    assert events.iloc[-1].revision==2
    assert events.iloc[-1].available_as_of=='2026-10-02'
    assert filter_available_as_of(events,'2026-09-30').actual.tolist()==[10]
    assert filter_available_as_of(events,'2026-10-02').actual.tolist()==[10,12]


def test_duplicate_run_deterministic():
    e,q,n=merge(base(),quality(),[row()]);bytes1=e.to_csv(index=False)
    e2,q2,n=merge(e,q,[row()]);assert n==0
    assert e2.to_csv(index=False)==bytes1 and q2.to_csv(index=False)==q.to_csv(index=False)


def test_metadata_missing_never_invents_release_date():
    r=row();r.update(release_date=None,vintage_date=None,verification_status='METADATA_UNVERIFIED')
    assert compare(r,base())['status']=='METADATA_UNVERIFIED'
    assert r['release_date'] is None


def test_stale_source_refuses_rollback():
    r=row(period='July 2026',release='2026-08-07')
    assert compare(r,base())['status']=='STALE'


def test_gate_rejects_old_canonical():
    r=row();report=compare(r,base())
    with pytest.raises(RuntimeError,match='canonical gate'):assert_current(base(),[report])


def test_nfp_is_difference_of_sa_thousands_and_not_level():
    d=[dict(year='2026',period='M07',value='150000'),dict(year='2026',period='M08',value='150100'),dict(year='2026',period='M09',value='150129'),dict(year='2026',period='M13',value='150110')]
    out=transform_bls(d,'difference_thousands')
    assert [v for _,v,_ in out]==[100000,29000]


def test_monthly_percent_and_gap_no_silent_nonadjacent_change():
    d=[dict(year='2026',period='M07',value='100'),dict(year='2026',period='M09',value='110')]
    with pytest.raises(ValueError):transform_bls(d,'percent')
    d.insert(1,dict(year='2026',period='M08',value='100.35'))
    assert transform_bls(d,'percent')[0][1]==0.4


def test_bls_feed_uses_archive_release_not_api_month_or_updated():
    xml='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Payroll employment rises in September</title><link href="https://www.bls.gov/news.release/archives/empsit_10022026.htm"/><published>2026-10-02T07:51:00-04:00</published><updated>2026-10-03T10:00:00Z</updated></entry></feed>'''
    ref,release,time,url=bls_context(xml,'empsit')
    assert ref=='September 2026' and release=='2026-10-02' and time is None
    with pytest.raises(MetadataError):bls_context(xml.replace('<published>','<other>').replace('</published>','</other>'),'empsit')


def test_embargo_date_distinct_from_reference_month():
    date,time=release_timestamp('FOR RELEASE AT 8:30 AM EDT, WEDNESDAY, SEPTEMBER 16, 2026 ADVANCE MONTHLY SALES AUGUST 2026')
    assert date=='2026-09-16'
    with pytest.raises(MetadataError):release_timestamp('September 2026 retrieved October 2, 2026')


def test_audit_source_failure_no_public_or_workspace_mutation(tmp_path):
    shutil.copytree(ROOT/'public_data',tmp_path/'public_data')
    before={p.name:p.read_bytes() for p in (tmp_path/'public_data').iterdir() if p.is_file()}
    def failing(c,i):raise OSError('endpoint unavailable')
    out=run(tmp_path,tmp_path/'stage',collector=failing,now=NOW)
    assert {r['status'] for r in out['reports']}=={'SOURCE_ERROR'}
    assert not out['passed'] and not (tmp_path/EVENTS).exists()
    with pytest.raises(RuntimeError):run(tmp_path,tmp_path/'stage',mode='merge',collector=failing,now=NOW)
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'public_data').iterdir() if p.is_file()}


def verified_fixture(c,i):
    # Synthetic test observations only: this collector is never selectable by CLI.
    return [row(i,123 if i=='NFP' else 1.2,period='Q3 2026' if i=='GDP' else 'Week ending September 26, 2026' if i=='INITIAL_JOBLESS_CLAIMS' else 'September 2026')]


def test_all_14_staging_merge_and_downstream_e2e(tmp_path):
    shutil.copytree(ROOT/'public_data',tmp_path/'public_data')
    # Fixture reference/release times must not depend on today's production vintages.
    baseline=[]
    for index,period in enumerate(pd.period_range('2025-01','2026-08',freq='M')):
        release=((period+1).to_timestamp()+pd.Timedelta(days=3)).strftime('%Y-%m-%d')
        for indicator in MAPPINGS:
            if indicator=='GDP':continue
            ref='Week ending '+period.end_time.strftime('%B %d, %Y') if indicator=='INITIAL_JOBLESS_CLAIMS' else period.strftime('%B %Y')
            baseline.append(row(indicator,10+index*index if indicator=='NFP' else 1.0+(index%5)*.1,period=ref,release=release))
    for period in pd.period_range('2024Q4','2026Q2',freq='Q'):
        baseline.append(row('GDP',1.0,period=f'Q{period.quarter} {period.year}',release=(period.end_time+pd.Timedelta(days=25)).strftime('%Y-%m-%d')))
    pd.DataFrame(baseline).to_csv(tmp_path/'public_data'/EVENTS,index=False)
    quality().to_csv(tmp_path/'public_data'/QUALITY,index=False)
    out=run(tmp_path,tmp_path/'stage',mode='merge',collector=verified_fixture,now=NOW)
    assert out['passed'] and len(out['reports'])==14
    original=pd.read_csv(tmp_path/'public_data'/EVENTS)
    assert len(pd.read_csv(tmp_path/EVENTS))>len(original)
    for script in ['economic_surprise_engine_v1.1.py','economic_regime_classifier_v1.5.py']:
        subprocess.run([sys.executable,str(ROOT/script)],cwd=tmp_path,check=True,capture_output=True)
    surprise=pd.read_csv(tmp_path/'economic_surprise_engine_v1.csv')
    for report in out['reports']:
        sub=surprise[(surprise.indicator==report['indicator'])&(surprise.release_date=='2026-10-02')]
        assert (sub.actual==report['official_value']).any()
    regime=pd.read_csv(tmp_path/'economic_regime_events_v1.csv')
    assert regime.release_date.max()=='2026-10-02'
    for name in [EVENTS,QUALITY,'economic_ingestion_status_v1.json','economic_surprise_engine_v1.csv','economic_surprise_summary_v1.csv','economic_regime_events_v1.csv','economic_regime_summary_v1.csv']:
        shutil.copy2(tmp_path/name,tmp_path/'public_data'/name)
    # Exercise the actual Context and Decision scripts in an isolated project.
    import os
    for src in ROOT.glob('*.py'):shutil.copy2(src,tmp_path/src.name)
    for folder in ['evidence_adapters','scripts']:
        shutil.copytree(ROOT/folder,tmp_path/folder,dirs_exist_ok=True)
    for src in (tmp_path/'public_data').iterdir():
        if src.suffix in {'.csv','.json'}:shutil.copy2(src,tmp_path/src.name)
    env=dict(os.environ,MACRO_CONTEXT_AS_OF_DATE=NOW.date().isoformat(),MACRO_CONTEXT_FILE=str(tmp_path/'macro_context_v1.csv'),SENTIMENT_ENGINE_FILE=str(tmp_path/'sentiment_engine_research_v1.csv'),TECHNICAL_INTELLIGENCE_FILE=str(tmp_path/'technical_intelligence_research_v1.csv'))
    for script in ['macro_context_v1.py','research-context-v1.py']:
        subprocess.run([sys.executable,str(tmp_path/script)],cwd=tmp_path,env=env,check=True,capture_output=True)
    macro=pd.read_csv(tmp_path/'macro_context_v1.csv')
    assert str(macro.iloc[-1]['economic_source_date'])[:10]=='2026-10-02'
    for name in ['macro_context_v1.csv','macro_context_v1.json','research_context_v1.csv','research_context_summary_v1.csv','research_context_extremes_v1.csv']:
        shutil.copy2(tmp_path/name,tmp_path/'public_data'/name)
    for script in ['research_evidence_contract_v1.py','research_context_quality_integration_v1.py']:
        subprocess.run([sys.executable,str(tmp_path/script)],cwd=tmp_path,env=env,check=True,capture_output=True)
    subprocess.run([sys.executable,str(ROOT/'tests/decision_engine/decision_engine_v1.py'),'--input',str(tmp_path/'public_data/research_context_summary_v1.csv'),'--output-dir',str(tmp_path/'decision_engine_output')],cwd=tmp_path,check=True,capture_output=True)
    for src in (tmp_path/'decision_engine_output').iterdir():shutil.copy2(src,tmp_path/'public_data'/src.name)
    # Decision Intelligence prerequisites are the project's existing quality,
    # state-vector and analog rebuild sequence.
    for script in ['remaining_layers_quality_v1.py','final_remaining_layers_hardening_v1.py','unified_state_vector_v1.py','historical_analog_engine_v1.py','historical_market_reaction_v1.py','decision_intelligence_v2.py']:
        subprocess.run([sys.executable,str(tmp_path/script)],cwd=tmp_path,env=env,check=True,capture_output=True)
    from scripts.rebuild_publication_manifest import rebuild
    rebuild(tmp_path/'public_data','mock-economic-e2e')
    subprocess.run([sys.executable,str(ROOT/'scripts/verify_publication_integrity.py'),'--public-data',str(tmp_path/'public_data')],check=True,capture_output=True)


def test_failed_indicator_blocks_all_14_merge(tmp_path):
    shutil.copytree(ROOT/'public_data',tmp_path/'public_data')
    def collector(c,i):
        if i=='CORE_CPI':return [dict(row(i),verification_status='METADATA_UNVERIFIED',release_date=None)]
        return verified_fixture(c,i)
    with pytest.raises(RuntimeError,match='CORE_CPI:METADATA_UNVERIFIED'):run(tmp_path,tmp_path/'stage','merge',collector,NOW)
    assert not (tmp_path/EVENTS).exists()


def test_workflow_order_and_audit_readonly():
    text=(ROOT/'.github/workflows/economic_intelligence_full_pipeline_v2.3_refresh.yml').read_text()
    assert text.index('--mode merge')<text.index('python economic_surprise_engine_v1.1.py')<text.index('python economic_regime_classifier_v1.5.py')<text.index('--mode gate')
    assert '2026-09-04' not in text
    audit=(ROOT/'.github/workflows/official-economic-ingestion-audit.yml').read_text()
    assert '--mode audit' in audit and '--mode merge' not in audit and 'contents: read' in audit


def test_source_snapshot_revision_does_not_replace_latest_period():
    from economic_official_ingestion_v1 import latest
    e,q,n=merge(base(),quality(),[dict(row(value=12,period='August 2026'),latest_official_period='September 2026'),dict(row(),latest_official_period='September 2026')])
    assert latest(e,'NFP').reference_period=='September 2026'
    revised=e[e.reference_period=='August 2026'].iloc[-1]
    assert revised.source_snapshot_history


def test_economic_due_even_after_file_rebuild(monkeypatch):
    import autonomy_due_detector_v1 as dd
    monkeypatch.setattr(dd,'_git_last_change',lambda *a,**k: NOW)
    registry=dd.load_registry()
    # A stale registry cadence must not turn freshly rebuilt files into source proof.
    next(node for node in registry['nodes'] if node['id']=='economic')['frequency']='daily'
    out=dd.detect_due(registry,NOW,ROOT)
    assert 'economic' in out['due_roots']


class Response:
    def __init__(self,text='',payload=None):self.text=text;self.content=(json.dumps(payload).encode() if payload is not None else text.encode());self.payload=payload
    def json(self):return self.payload

class FakeClient:
    def __init__(self,fn):self.fn=fn
    def get(self,url,**kwargs):return self.fn(url,kwargs)


def test_bls_unavailable_historical_value_and_latest_metadata(monkeypatch):
    from economic_official_sources_v1 import collect_bls
    data=[dict(year='2026',period='M09',value='4.2'),dict(year='2026',period='M08',value='4.1'),dict(year='2025',period='M10',value='-')]
    xml='''<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Unemployment changes little in September</title><link href="https://www.bls.gov/news.release/archives/empsit_10022026.htm"/><published>2026-10-02T08:30:00-04:00</published></entry></feed>'''
    c=FakeClient(lambda u,k:Response(text=xml) if 'feed/' in u else Response(payload={'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':'LNS14000000','data':data}]}}))
    rows=collect_bls(c,'UNEMPLOYMENT_RATE');assert rows[-1]['actual']==4.2 and rows[-1]['release_date']=='2026-10-02'
    data[0]['value']='-'
    with pytest.raises(MetadataError,match='Latest BLS'):collect_bls(c,'UNEMPLOYMENT_RATE')


def test_bls_api_value_without_metadata_is_unverified():
    from economic_official_sources_v1 import collect_bls
    c=FakeClient(lambda u,k:Response(text='<feed/>') if 'feed/' in u else Response(payload={'status':'REQUEST_SUCCEEDED','Results':{'series':[{'seriesID':'CES0000000001','data':[dict(year='2026',period='M08',value='100'),dict(year='2026',period='M09',value='101')]}]}}))
    r=collect_bls(c,'NFP')[-1]
    assert r['actual']==1000 and r['verification_status']=='METADATA_UNVERIFIED' and r['release_date'] is None


@pytest.mark.parametrize('indicator,expected',[('PCE_PRICE_INDEX',0.3),('CORE_PCE',0.2),('GDP',2.5)])
def test_bea_discovery_and_release_parsing(indicator,expected):
    from economic_official_sources_v1 import collect_bea
    index='<a href="/news/2026/pce">Personal Income and Outlays, August 2026</a><a href="/news/2026/gdp">GDP (Third Estimate), 2nd Quarter 2026</a>'
    embargo='EMBARGOED UNTIL RELEASE AT 8:30 a.m. EDT, Wednesday, September 30, 2026 '
    pce=embargo+'Personal Income and Outlays, August 2026 From the preceding month, the PCE price index for August increased 0.3 percent. Excluding food and energy, the PCE price index increased 0.2 percent.'
    gdp=embargo+'Real gross domestic product (GDP) increased at an annual rate of 2.5 percent in the second quarter of 2026.'
    c=FakeClient(lambda u,k:Response(text=index if u.endswith('current-releases') else gdp if u.endswith('gdp') else pce))
    r=collect_bea(c,indicator)[0];assert r['actual']==expected and r['release_date']=='2026-09-30'


def test_claims_seasonally_adjusted_and_revision(monkeypatch):
    import economic_official_sources_v1 as sources
    from types import SimpleNamespace
    text="EMBARGOED UNTIL 8:30 A.M. (Eastern) Thursday, October 1, 2026 In the week ending September 26, the advance figure for seasonally adjusted initial claims was 197,000. The previous week's level was revised up by 1,000 from 197,000 to 198,000."
    monkeypatch.setattr(sources,'PdfReader',lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)]))
    r=sources.collect_claims(FakeClient(lambda u,k:Response()))
    assert r[-1]['actual']==197000 and r[-1]['previous']==198000
    assert r[0]['reference_period']=='Week ending September 19, 2026' and r[0]['actual']==198000


def test_census_revision_uses_new_vintage_and_api_sa_selector(monkeypatch):
    import economic_official_sources_v1 as sources
    from types import SimpleNamespace
    monkeypatch.setenv('CENSUS_API_KEY','TEST_ONLY_NOT_A_SECRET')
    text='FOR RELEASE AT 8:30 AM EDT, WEDNESDAY, SEPTEMBER 16, 2026 ADVANCE MONTHLY SALES FOR RETAIL AND FOOD SERVICES, AUGUST 2026 Revised not adjusted estimates and corresponding adjusted estimates were released on September 28, 2026 at 10:00 a.m. EDT.'
    monkeypatch.setattr(sources,'PdfReader',lambda _:SimpleNamespace(pages=[SimpleNamespace(extract_text=lambda:text)]))
    def response(u,k):
        if u.endswith('.pdf'):return Response()
        if u.endswith('/marts.json'):return Response(payload={'dataset':[{'c_dataset':['timeseries','eits','marts'],'title':'Advance Monthly Sales for Retail and Food Services'}]})
        assert k['params']['category_code']=='44X72' and k['params']['seasonally_adj']=='yes'
        return Response(payload=[['cell_value','time','category_code','data_type_code','seasonally_adj'],['100','2026-07','44X72','SM','yes'],['102','2026-08','44X72','SM','yes']])
    r=sources.collect_retail(FakeClient(response))[0]
    assert r['actual']==2 and r['release_date']=='2026-09-28' and r['publication_status']=='REVISED'


def test_ism_dynamic_link_and_explicit_calendar(monkeypatch):
    import economic_official_sources_v1 as sources
    today=pd.Timestamp.now(tz='America/New_York');released=(today.tz_localize(None).normalize()-pd.Timedelta(days=1))
    reference=(pd.Period(released,freq='M')-1).strftime('%B %Y')
    index='<a href="/supply-management-news-and-reports/reports/ism-pmi-reports/services/current/">View Report</a>'
    report=reference+' ISM® Services PMI® Report The Services PMI® registered 55.4 percent'
    cal=f'<table><tr><td>{released.strftime("%B %Y")}</td><td>{released.day}</td><td>{released.day}</td></tr></table>'
    c=FakeClient(lambda u,k:Response(text=cal if 'rob-report-calendar' in u else report if '/services/current/' in u else index))
    r=sources.collect_ism(c,'ISM_SERVICES_PMI')[0]
    assert r['actual']==55.4 and r['release_date']==released.strftime('%Y-%m-%d')


def test_secret_not_in_error_audit(tmp_path):
    import requests
    shutil.copytree(ROOT/'public_data',tmp_path/'public_data')
    def bad(c,i):raise requests.HTTPError('bad URL ?key=PRIVATE_TEST_VALUE')
    run(tmp_path,tmp_path/'stage',collector=bad,now=NOW)
    assert 'PRIVATE_TEST_VALUE' not in (tmp_path/'stage/audit.json').read_text()


def test_revision_reversion_is_recorded_and_duplicate_safe():
    b=base();first=row(value=12,period='August 2026')
    e,q,n=merge(b,quality(),[first])
    restored=row(value=10,period='August 2026')
    e,q,n=merge(e,q,[restored]);assert n==1 and e.actual.tolist()==[10,12,10]
    e2,q2,n=merge(e,q,[restored]);assert n==0 and e2.to_csv(index=False)==e.to_csv(index=False)


def test_prior_period_revisions_are_not_independent_zscore_samples():
    import importlib.util
    spec=importlib.util.spec_from_file_location('official_surprise_test',ROOT/'economic_surprise_engine_v1.1.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    base=pd.DataFrame({'indicator':['CPI']*5,'release_date':pd.date_range('2026-01-01',periods=5,freq='MS'),'directional_release_shock':[1,2,3,4,5]})
    z,_=mod.calculate_prior_zscore(base)
    revision=pd.DataFrame({'indicator':['CPI'],'release_date':[pd.Timestamp('2026-04-20')],'directional_release_shock':[9999],'source_snapshot_history':[True]})
    combined=pd.concat([base,revision],ignore_index=True).sort_values('release_date')
    z2,_=mod.calculate_prior_zscore(combined)
    assert z2.loc[4]==z.loc[4] and pd.isna(z2.loc[5])


def test_delayed_revision_cannot_enter_earlier_zscore_baseline():
    spec=importlib.util.spec_from_file_location('official_surprise_availability_test',ROOT/'economic_surprise_engine_v1.1.py')
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    base=pd.DataFrame({'indicator':['CPI']*5,'release_date':pd.date_range('2026-01-01',periods=5,freq='MS'),'directional_release_shock':[1,2,3,4,5]})
    z,_=mod.calculate_prior_zscore(base)
    delayed=pd.DataFrame({'indicator':['CPI'],'release_date':['2026-02-15'],'available_as_of':['2026-06-01'],'directional_release_shock':[9999]})
    combined=pd.concat([base,delayed],ignore_index=True)
    z2,_=mod.calculate_prior_zscore(combined)
    assert z2.loc[4]==z.loc[4]
