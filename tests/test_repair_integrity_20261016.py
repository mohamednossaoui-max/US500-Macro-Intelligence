"""Regression coverage for audit failures, using frozen synthetic evidence only."""
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import importlib.util
import numpy as np
import pandas as pd
import pytest
from research_evidence_quality_v1 import apply_quality
from evidence_adapters.fed import build as fed_rows
from evidence_adapters.liquidity import build as liquidity_rows
from published_snapshot_v1 import PublishedSnapshot
from release_clock_v1 import official_release_at
from point_in_time import filter_available_as_of
from workspace_transaction_v1 import install_bundle
import system_health_monitor_v1 as health
import historical_analog_engine_v1 as analog
from economic_official_ingestion_v1 import compare
from economic_official_sources_v1 import observation,MAPPINGS

ROOT=Path(__file__).resolve().parents[1]

def manifest(p,files):
 obj={'files':{}}
 for n,b in files.items():
  (p/n).write_bytes(b);obj['files'][n]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
 (p/'manifest.json').write_text(json.dumps(obj))
 return obj

def test_minutes_publication_is_not_meeting_date(tmp_path):
 obj={'as_of_date':'2026-10-15','latest_fomc':'2026-09-16','minutes_publication_date':'2026-10-07','minutes':{'available':True},'quality':{'pit_status':'OBSERVATION_CHECKED'}}
 (tmp_path/'fed_intelligence_output_v1.json').write_text(json.dumps(obj))
 r=next(r for r in fed_rows(tmp_path) if r['indicator']=='FOMC Minutes')
 assert r['available_at']=='2026-10-07' and r['release_date']=='2026-10-07'
 obj['as_of_date']='2026-10-06';(tmp_path/'fed_intelligence_output_v1.json').write_text(json.dumps(obj))
 r=next(r for r in apply_quality(fed_rows(tmp_path)) if r['indicator']=='FOMC Minutes')
 assert r['pit_status']=='NOT_PIT_SAFE' and not r['decision_engine_eligible']

def test_press_unknown_publication_is_bounded_by_retrieval(tmp_path):
 obj={'as_of_date':'2026-10-15','latest_fomc':'2026-09-16','chair_press':{'available':True},'evidence_dates':{'chair_press':{'retrieved_at':'2026-10-15T20:00:00Z'}},'quality':{'pit_status':'OBSERVATION_CHECKED'}}
 (tmp_path/'fed_intelligence_output_v1.json').write_text(json.dumps(obj))
 r=next(r for r in apply_quality(fed_rows(tmp_path)) if r['indicator']=='Press Conference')
 assert r['available_at']=='2026-10-15T20:00:00Z' and not r['release_date']
 assert r['pit_status']=='OBSERVATION_CHECKED' and not r['decision_engine_eligible']

@pytest.mark.parametrize('status',['UNKNOWN','OBSERVATION_CHECKED','PIT_LIMITED','NOT_PIT_SAFE'])
def test_unproved_pit_never_becomes_eligible(status):
 r=apply_quality([dict(pit_status=status,available_at='2026-10-14',as_of_date='2026-10-15',expected_frequency='DAILY')])[0]
 assert r['pit_status']==status and not r['decision_engine_eligible']

@pytest.mark.parametrize('changes',[{'available_at':''},{'as_of_date':''},{'expected_frequency':'UNKNOWN'}])
def test_unknown_freshness_is_not_eligible(changes):
 row=dict(pit_status='PIT_SAFE',available_at='2026-10-14',as_of_date='2026-10-15',expected_frequency='DAILY');row.update(changes)
 r=apply_quality([row])[0];assert not r['decision_engine_eligible']

def test_valid_quality_contract_keeps_eligible():
 r=apply_quality([dict(pit_status='PIT_SAFE',available_at='2026-10-14',as_of_date='2026-10-15',expected_frequency='DAILY')])[0]
 assert r['decision_engine_eligible'] and r['freshness_status']=='CURRENT'

@pytest.mark.parametrize('day,expected',[('2026-10-14','2026-10-14T12:30:00Z'),('2026-11-12','2026-11-12T13:30:00Z')])
def test_release_clock_dst(day,expected):
 assert official_release_at({'release_date':day,'release_time':'08:30 ET'})==pd.Timestamp(expected)

@pytest.mark.parametrize('time',['unknown','08:30','08:30 XYZ','99:99 ET'])
def test_release_clock_does_not_invent_hour(time):
 assert official_release_at({'release_date':'2026-10-14','release_time':time}) is None

@pytest.mark.parametrize('indicator',['CPI','CORE_CPI','PPI_FINAL_DEMAND','CORE_PPI'])
def test_before_official_release_blocked_even_same_day(indicator):
 row=observation(indicator,'September 2026',.1,'2026-10-14','08:30 ET',MAPPINGS[indicator]['url'],retrieved_at='2026-10-14T12:29:59Z')
 base=pd.DataFrame([dict(row,release_date='2026-09-11',reference_period='August 2026')])
 assert compare(row,base)['status']=='METADATA_UNVERIFIED'
 row['retrieved_at']='2026-10-14T12:30:00Z'
 assert compare(row,base)['status']=='NEW_RELEASE'

def test_precise_availability_blocks_early_and_late_revision():
 d=pd.DataFrame({'release_date':['2026-10-14','2026-10-14'],'available_as_of':['2026-10-14','2026-10-15'],'available_at_utc':['2026-10-14T12:31:00Z','2026-10-15T09:00:00Z'],'actual':[1,2]})
 assert filter_available_as_of(d,'2026-10-14T12:30:59Z').empty
 assert filter_available_as_of(d,'2026-10-14T12:31:00Z').actual.tolist()==[1]
 assert filter_available_as_of(d,'2026-10-14').actual.tolist()==[1]
 assert filter_available_as_of(d,'2026-10-15T08:59:59Z').actual.tolist()==[1]
 assert filter_available_as_of(d,'2026-10-15T09:00:00Z').actual.tolist()==[1,2]

def test_invalid_precise_timestamp_fails_closed():
 d=pd.DataFrame({'release_date':['2026-10-14'],'available_at_utc':['BROKEN']})
 assert filter_available_as_of(d,'2026-10-15').empty

def test_old_liquidity_uses_consumer_clock(tmp_path):
 d=pd.read_csv(ROOT/'public_data/liquidity_intelligence_research_v1.csv').tail(1).copy()
 d['asof_date']='2026-09-21'
 for c in d:
  if c.endswith('_available_at'):d[c]='2026-09-21'
 d.to_csv(tmp_path/'liquidity_intelligence_research_v1.csv',index=False)
 pd.DataFrame([{'context_date':'2026-10-15'}]).to_csv(tmp_path/'research_context_summary_v1.csv',index=False)
 rows=apply_quality(liquidity_rows(tmp_path))
 assert all(r['as_of_date']=='2026-10-15' and r['freshness_status']=='STALE' and not r['decision_engine_eligible'] for r in rows)

def test_touching_old_file_never_makes_healthy(tmp_path):
 manifest(tmp_path,{'x.csv':b'asof_date,value\n2000-01-01,1\n'})
 now=datetime(2026,10,16,tzinfo=timezone.utc);os.utime(tmp_path/'x.csv',(now.timestamp(),now.timestamp()))
 reg={'nodes':[{'id':'x','kind':'source_layer','criticality':'critical','outputs':['x.csv'],'freshness_sla_days':2}]}
 r=health.derive_health(reg,[],tmp_path,now)['layers'][0]
 assert r['state']=='STALE' and r['age_days']>9000
 (tmp_path/'x.csv').write_text('asof_date,value\n2026-10-16,1\n')
 r=health.derive_health(reg,[],tmp_path,now)['layers'][0]
 assert not r['last_known_good'] and r['state']!='HEALTHY'

def test_mtime_without_content_date_is_unknown(tmp_path):
 manifest(tmp_path,{'x.csv':b'value\n1\n'})
 reg={'nodes':[{'id':'x','kind':'source_layer','outputs':['x.csv']}]}
 assert health.derive_health(reg,[],tmp_path)['layers'][0]['state']=='UNKNOWN'

def test_snapshot_never_combines_local_and_remote(tmp_path):
 manifest(tmp_path,{'x':b'old'})
 calls=[];snap=PublishedSnapshot(tmp_path,lambda n:calls.append(n) or b'new')
 assert snap.read('x')[0]==b'old'
 (tmp_path/'x').unlink();new=PublishedSnapshot(tmp_path,lambda n:calls.append(n) or b'new')
 assert new.read('x')[0] is None and not calls

def test_snapshot_rejects_mismatch_and_unlisted(tmp_path):
 manifest(tmp_path,{'x':b'old'});(tmp_path/'x').write_bytes(b'new')
 s=PublishedSnapshot(tmp_path,None)
 assert s.read('x')[0] is None and s.read('unknown')[0] is None
 assert s.read('../secrets')[0] is None

def test_snapshot_is_frozen_for_one_frontend_run(tmp_path):
 manifest(tmp_path,{'x':b'old'});s=PublishedSnapshot(tmp_path,None);assert s.read('x')[0]==b'old'
 manifest(tmp_path,{'x':b'new'});assert s.read('x')[0]==b'old'
 assert PublishedSnapshot(tmp_path,None).read('x')[0]==b'new'

def test_remote_manifest_verifies_bytes(tmp_path):
 obj={'files':{'x':{'bytes':3,'sha256':hashlib.sha256(b'old').hexdigest()}}}
 data={'manifest.json':json.dumps(obj).encode(),'x':b'new'}
 s=PublishedSnapshot(tmp_path,data.get);assert s.read('x')[0] is None
 data['x']=b'old';assert s.read('x')[0]==b'old'

def test_economic_install_rolls_back_entire_bundle(tmp_path,monkeypatch):
 (tmp_path/'a').write_bytes(b'old-a');(tmp_path/'b').write_bytes(b'old-b')
 import workspace_transaction_v1 as m
 replace=m.os.replace;calls=[]
 def fail_second(a,b):
  calls.append(str(b))
  if len(calls)==2:raise OSError('synthetic disk failure')
  return replace(a,b)
 monkeypatch.setattr(m.os,'replace',fail_second)
 with pytest.raises(OSError):install_bundle(tmp_path,{'a':b'new-a','b':b'new-b','c':b'new-c'})
 assert (tmp_path/'a').read_bytes()==b'old-a' and (tmp_path/'b').read_bytes()==b'old-b' and not (tmp_path/'c').exists()
 assert not (tmp_path/'.economic-install-journal.json').exists()

def test_correlated_run_rejects_latest_unrelated():
 spec=importlib.util.spec_from_file_location('dispatch',ROOT/'scripts/dispatch_correlated_run.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
 runs=[dict(databaseId=2,displayTitle='workflow [other]',headSha='sha',event='workflow_dispatch'),dict(databaseId=1,displayTitle='workflow [token]',headSha='sha',event='workflow_dispatch')]
 assert m.select_run(runs,'token','sha')=='1'
 assert m.select_run(runs,'token','different') is None
 with pytest.raises(RuntimeError):m.select_run(runs+[runs[1]],'token','sha')

def test_historical_pit_masks_use_explicit_feature_mapping(tmp_path,monkeypatch):
 frames={
 'economic_regime_events_v1.csv':[dict(release_date='2020-01-10',dimensions_available=3,pit_safe=True,inflation_score=1,labor_score=1,growth_score=1,economic_regime='X')],
 'financial_stress_research_v1.csv':[dict(asof_date='2020-01-09',composite_stress_score=99,point_in_time_safe=False)],
 'liquidity_intelligence_research_v1.csv':[dict(asof_date='2020-01-09',SOFR_fresh=True,point_in_time_safe=False)],
 'research_context_v1.csv':[dict(context_date='2020-01-09',sentiment_unified_sentiment_score=5,sentiment_point_in_time_safe=True)],
 'technical_intelligence_research_v1.csv':[dict(availability_date='2020-01-09',technical_regime='UP',point_in_time_safe=True)]}
 for n,rows in frames.items():pd.DataFrame(rows).to_csv(tmp_path/n,index=False)
 monkeypatch.setattr(analog,'P',tmp_path);h=analog.build_history().iloc[0]
 assert pd.isna(h.financial_stress) and pd.isna(h.liquidity_coverage) and h.sentiment==5 and h.technical=='UP'

def test_backward_join_has_age_bound():
 l=pd.DataFrame({'event':pd.to_datetime(['2026-10-15'])});r=pd.DataFrame({'known':pd.to_datetime(['2026-08-01']),'v':[1]})
 assert pd.isna(analog._asof(l,r,'event','known',['v']).v.iloc[0])

def test_target_excludes_ineligible_values(tmp_path,monkeypatch):
 rows=[dict(feature=f,state_vector_version=analog.VECTOR_VERSION,context_date='2026-10-15',value=99,state='UP',eligible=False) for f in analog.CORE_FEATURES]
 pd.DataFrame(rows).to_csv(tmp_path/'unified_state_vector_v1.csv',index=False);monkeypatch.setattr(analog,'P',tmp_path)
 t,_=analog.target();assert all(pd.isna(v) for v in t.values())


def test_health_display_expires_stale_green_snapshot():
 from system_health_monitor_v1 import display_summary
 r=display_summary({'overall_health':'HEALTHY','as_of':'2026-10-14T12:00:00Z'},datetime(2026,10,16,tzinfo=timezone.utc))
 assert r['overall_health']=='DEGRADED' and r['snapshot_freshness']=='STALE'


def test_empty_analogs_reaction_has_schema_and_no_invented_outcome(monkeypatch):
 import historical_market_reaction_v1 as m
 empty=pd.read_csv(ROOT/'public_data/historical_analog_top_v1.csv').head(0)
 monkeypatch.setattr(m,'load_locked_analogs',lambda:empty)
 r=m.build_reactions();s=m.build_summary(r)
 assert r.empty and s['analog_count']==0
 assert all(h['median_return_pct'] is None and h['available_analogs']==0 for h in s['horizons'].values())


def test_empty_analogs_decision_summary_is_explicit(tmp_path,monkeypatch):
 import shutil
 import decision_intelligence_v2 as m
 for name in ['decision_engine_research_summary_v1.csv','unified_state_vector_v1.csv','historical_analog_summary_v1.json','historical_market_reaction_summary_v1.json']:
  shutil.copy2(ROOT/'public_data'/name,tmp_path/name)
 pd.read_csv(ROOT/'public_data/historical_analog_top_v1.csv').head(0).to_csv(tmp_path/'historical_analog_top_v1.csv',index=False)
 obj=json.loads((tmp_path/'historical_market_reaction_summary_v1.json').read_text())
 for h in obj['horizons'].values():
  for k in h:
   h[k]=0 if k in {'available_analogs','total_analogs'} else None
 (tmp_path/'historical_market_reaction_summary_v1.json').write_text(json.dumps(obj))
 monkeypatch.setattr(m,'PD',tmp_path);r=m.build()
 assert r['historical_analogs']['count']==0 and r['historical_analogs']['closest_date'] is None
 assert 'insufficient' in r['historical_analogs']['summary'].lower()
 assert 'positive median outcomes' not in r['final_research_synthesis']
 assert 'NaN' not in (tmp_path/'decision_intelligence_v2.json').read_text()


def test_fed_eligibility_is_not_forced_in_state_vector():
 text=(ROOT/'unified_state_vector_v1.py').read_text()
 fed=next(line for line in text.splitlines() if "row('fed_stance'" in line)
 assert 'force_eligible=True' not in fed


def test_production_workflows_share_dispatch_contract_and_constraints():
 import yaml,re
 master=(ROOT/'.github/workflows/us500-full-research-pipeline.yml').read_text()
 assert 'dispatch_correlated_run.py' in master and 'git rebase origin/main;' not in master
 for path in (ROOT/'.github/workflows').glob('*.yml'):
  source=path.read_text();doc=yaml.safe_load(source)
  if 'correlation_id:' not in source:continue
  # PyYAML's YAML 1.1 parser maps the GitHub `on` key to boolean True.
  on=doc.get('on',doc.get(True));inputs=on['workflow_dispatch']['inputs']
  assert {'correlation_id','source_ref'}<=set(inputs)
  assert 'inputs.correlation_id' in doc['run-name']
  assert 'PIP_CONSTRAINT' in doc['env']
  for name,job in doc['jobs'].items():
   if name=='record-failed-attempt':continue
   for step in job.get('steps',[]):
    if step.get('uses')=='actions/checkout@v4':assert step['with']['ref']=='${{ inputs.source_ref || github.sha }}'


def test_master_is_only_production_data_publisher():
 fed=(ROOT/'.github/workflows/test-fed.yml').read_text();legacy=(ROOT/'.github/workflows/publish_research_data_v1.yml').read_text()
 assert 'git push' not in fed and 'git push' not in legacy and 'workflow_run:' not in legacy
 assert 'manifest.setdefault' not in (ROOT/'fed_intelligence_export_v1.py').read_text()


def test_failed_attempt_updates_metadata_only_and_retains_verified_data(tmp_path):
 from scripts.record_pipeline_attempt_v1 import record
 from scripts.verify_publication_integrity import run
 manifest(tmp_path,{'cpi.csv':b'release_date,actual\n2026-10-14,0.6\n','fed.json':b'{"available":true}'})
 before={n:(tmp_path/n).read_bytes() for n in ['cpi.csv','fed.json']}
 record(tmp_path,'FAILED','123',now=datetime(2026,10,16,tzinfo=timezone.utc))
 assert before=={n:(tmp_path/n).read_bytes() for n in before}
 assert run(tmp_path)['manifests'][0]['summary']['mismatch']==0
 obj=json.loads((tmp_path/'pipeline_attempt_v1.json').read_text())
 assert obj['status']=='FAILED' and obj['research_scores_changed'] is False


def test_attempt_recorder_refuses_corrupted_publication(tmp_path):
 from scripts.record_pipeline_attempt_v1 import record
 manifest(tmp_path,{'x':b'old'});(tmp_path/'x').write_bytes(b'bad')
 with pytest.raises(ValueError,match='unverified'):record(tmp_path,'FAILED','123')
 assert not (tmp_path/'pipeline_attempt_v1.json').exists()


def test_new_failed_attempt_is_visible_while_old_failure_does_not_override_new_health():
 from system_health_monitor_v1 import display_summary
 now=datetime(2026,10,16,12,tzinfo=timezone.utc)
 summary={'overall_health':'HEALTHY','as_of':'2026-10-16T10:00:00Z'}
 failed={'status':'FAILED','attempted_at':'2026-10-16T11:00:00Z','message':'Prior data retained'}
 r=display_summary(summary,now,failed);assert r['overall_health']=='FAILED' and r['attempt_warning']=='Prior data retained'
 failed['attempted_at']='2026-10-16T09:00:00Z'
 r=display_summary(summary,now,failed);assert r['overall_health']=='HEALTHY' and 'attempt_warning' not in r


@pytest.mark.parametrize('value',[None,float('nan'),False,'False','false','unknown','',0])
def test_unknown_boolean_flags_never_verify_evidence(value):
 from evidence_adapters.common import as_bool
 assert as_bool(value) is False


def test_stale_sentiment_remains_schema_valid_and_ineligible(tmp_path):
 import shutil
 from evidence_adapters.sentiment import build
 from research_evidence_schema_v1 import AVAILABILITY_STATUS
 names=['aaii_sentiment_research_v1.csv','vix_sentiment_research_v1.csv','cot_positioning_research_v1.csv']
 latest=[]
 for name in names:
  shutil.copy2(ROOT/'public_data'/name,tmp_path/name)
  latest.append(pd.to_datetime(pd.read_csv(tmp_path/name).availability_date).max())
 pd.DataFrame([{'context_date':(max(latest)+pd.Timedelta(days=30)).date().isoformat()}]).to_csv(tmp_path/'research_context_summary_v1.csv',index=False)
 rows=apply_quality(build(tmp_path))
 assert all(r['availability_status'] in AVAILABILITY_STATUS and not r['decision_engine_eligible'] for r in rows)
