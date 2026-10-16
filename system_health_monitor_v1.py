from __future__ import annotations
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from content_health_v1 import output_facts

ROOT=Path(__file__).resolve().parent
REGISTRY=ROOT/'autonomy_source_registry_v1.json'
LEDGER=ROOT/'autonomy_run_ledger_v1.jsonl'
PUBLIC=ROOT/'public_data'


def _dt(v):
    if not v: return None
    try: return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)
    except Exception: return None

def load_registry(path=REGISTRY): return json.loads(Path(path).read_text(encoding='utf-8'))

def load_ledger(path=LEDGER):
    p=Path(path)
    if not p.exists(): return []
    out=[]
    for line in p.read_text(encoding='utf-8').splitlines():
        try: out.append(json.loads(line))
        except Exception: pass
    if isinstance(attempt,dict):
        attempted=_dt(attempt.get('attempted_at'))
        out['latest_attempt_status']=attempt.get('status','UNKNOWN')
        out['latest_attempt_at']=attempt.get('attempted_at')
        out['latest_attempt_url']=attempt.get('run_url','')
        if attempted and (stamp is None or attempted>=stamp) and attempt.get('status') in {'FAILED','BLOCKED','CANCELLED'}:
            out['overall_health']='FAILED' if attempt['status']=='FAILED' else 'DEGRADED'
            out['attempt_warning']=attempt.get('message','Latest refresh did not complete; prior data retained.')
    return out

def _last_output_change(node, public):
    stamps=[]
    for name in node.get('outputs',[]):
        p=Path(public)/name
        if p.is_file(): stamps.append(datetime.fromtimestamp(p.stat().st_mtime,tz=timezone.utc))
    return max(stamps) if stamps else None

def _last_step(node_id, ledger):
    for run in reversed(ledger):
        for step in run.get('steps',[]):
            if step.get('node_id')==node_id:
                return run,step
    return None,None

def derive_health(registry=None, ledger=None, public=PUBLIC, now=None):
    reg=registry or load_registry(); led=load_ledger() if ledger is None else ledger
    now=now or datetime.now(timezone.utc); rows=[]
    for node in reg['nodes']:
        if node.get('kind')=='publication_gate': continue
        sla=float(node.get('freshness_sla_days') or 1)
        last_data, verified, complete = output_facts(node,public)
        file_updated=_last_output_change(node,public)
        age=(now-last_data).total_seconds()/86400 if last_data else None
        run,step=_last_step(node['id'],led)
        last_attempt=_dt(run.get('finished_at')) if run else None
        last_success=None
        for rr in reversed(led):
            if any(s.get('node_id')==node['id'] and s.get('status')=='PASSED' for s in rr.get('steps',[])):
                last_success=_dt(rr.get('finished_at')); break
        failure_reason=''
        if step and step.get('status')=='FAILED': state='FAILED'; failure_reason=step.get('reason','')
        elif step and step.get('status')=='BLOCKED': state='BLOCKED'; failure_reason=step.get('reason','')
        elif not complete:
            state='FAILED'; failure_reason='Required published output missing'
        elif last_data is None:
            state='UNKNOWN'; failure_reason='Content freshness unknown; file modification time is not data availability'
        elif age < -1:
            state='BLOCKED'; failure_reason='Future content timestamp'
        elif not verified:
            state='UNKNOWN'; failure_reason='Published outputs not verified against canonical manifest'
        elif age > sla: state='STALE'
        elif age > sla*0.75: state='AGING'
        else: state='HEALTHY'
        pit=str(node.get('pit_policy','unknown'))
        if 'limited' in pit.lower(): state='PIT_LIMITED' if state=='HEALTHY' else state
        next_check=(last_data+timedelta(days=sla)).isoformat() if last_data else None
        rows.append({'id':node['id'],'kind':node.get('kind'),'criticality':node.get('criticality','important'),
          'state':state,'last_success':last_success.isoformat() if last_success else None,
          'last_attempt':last_attempt.isoformat() if last_attempt else None,
          'last_data_update':last_data.isoformat() if last_data else None,'file_modified_at':file_updated.isoformat() if file_updated else None,'age_days':round(age,2) if age is not None else None,
          'freshness_sla_days':sla,'pit_status':'UNKNOWN','pit_policy':pit,'last_known_good':verified,'last_known_good_basis':'CANONICAL_MANIFEST_HASH_VERIFIED' if verified else 'UNVERIFIED','rollback_requires_previous_commit':True,'publication_verified':verified,'output_complete':complete,
          'failure_reason':failure_reason,'next_expected_check':next_check,
          'affects_system_health':node.get('affects_system_health') is not False,
          'health_scope_reason':node.get('health_scope_reason','Included in overall operational health'),
          'downstream_impact':[]})
    by={r['id']:r for r in rows}
    for n in reg['nodes']:
        for dep in n.get('depends_on',[]):
            if dep in by and n['id'] in by: by[dep]['downstream_impact'].append(n['id'])
    assessed=[r for r in rows if r['affects_system_health']]
    excluded=[r for r in rows if not r['affects_system_health']]
    critical=[r for r in assessed if r['criticality']=='critical']
    if any(r['state']=='FAILED' for r in critical): overall='FAILED'
    elif any(r['state'] in {'BLOCKED','STALE'} for r in critical): overall='DEGRADED'
    elif any(r['state'] in {'FAILED','BLOCKED','STALE','AGING','UNKNOWN'} for r in assessed): overall='DEGRADED'
    else: overall='HEALTHY'
    summary={'as_of':now.isoformat(),'overall_health':overall,'layer_count':len(rows),
      'healthy':sum(r['state']=='HEALTHY' for r in rows),'attention':sum(r['state']!='HEALTHY' for r in rows),
      'failed':sum(r['state']=='FAILED' for r in rows),'stale':sum(r['state']=='STALE' for r in rows),
      'lkg_available':sum(bool(r['last_known_good']) for r in rows),'research_only':True,
      'assessed_layer_count':len(assessed),'excluded_from_overall':[r['id'] for r in excluded],
      'excluded_attention':sum(r['state']!='HEALTHY' for r in excluded),
      'overall_health_scope':'Registry-selected layers; all layer states and counts remain visible'}
    return {'summary':summary,'layers':rows}

def publish(out=None, public=PUBLIC):
    out=out or derive_health(public=public); p=Path(public); p.mkdir(parents=True,exist_ok=True)
    (p/'system_health_summary_v1.json').write_text(json.dumps(out['summary'],indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (p/'system_health_layers_v1.json').write_text(json.dumps(out['layers'],indent=2,sort_keys=True)+'\n',encoding='utf-8')
    return out

if __name__=='__main__':
    print(json.dumps(publish()['summary'],indent=2))


def display_summary(summary, now=None, attempt=None):
    """A previously healthy monitor snapshot cannot stay green indefinitely."""
    out=dict(summary);now=now or datetime.now(timezone.utc);stamp=_dt(out.get('as_of'))
    age=(now-stamp).total_seconds()/3600 if stamp else None
    out['snapshot_age_hours']=round(age,2) if age is not None else None
    out['snapshot_freshness']='CURRENT' if age is not None and 0<=age<=24 else 'STALE' if age is not None and age>24 else 'UNKNOWN'
    if out['snapshot_freshness']!='CURRENT' and out.get('overall_health')=='HEALTHY':out['overall_health']='DEGRADED'
    if isinstance(attempt,dict):
        attempted=_dt(attempt.get('attempted_at'))
        out['latest_attempt_status']=attempt.get('status','UNKNOWN')
        out['latest_attempt_at']=attempt.get('attempted_at')
        out['latest_attempt_url']=attempt.get('run_url','')
        if attempted and (stamp is None or attempted>=stamp) and attempt.get('status') in {'FAILED','BLOCKED','CANCELLED'}:
            out['overall_health']='FAILED' if attempt['status']=='FAILED' else 'DEGRADED'
            out['attempt_warning']=attempt.get('message','Latest refresh did not complete; prior data retained.')
    return out
