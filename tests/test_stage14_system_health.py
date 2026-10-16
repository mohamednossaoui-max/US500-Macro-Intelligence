from datetime import datetime,timezone,timedelta
from pathlib import Path
import json
import system_health_monitor_v1 as h


def reg():
 return {'nodes':[{'id':'core','kind':'source_layer','criticality':'critical','freshness_sla_days':2,'pit_policy':'availability-date','outputs':['core.json'],'depends_on':[]},{'id':'ctx','kind':'source_layer','criticality':'contextual','freshness_sla_days':2,'pit_policy':'PIT_LIMITED','outputs':['ctx.json'],'depends_on':['core']}]}

def touch(p,dt):
 import os,hashlib
 p.write_text(json.dumps({'as_of_date':dt.isoformat()}))
 os.utime(p,(dt.timestamp(),dt.timestamp()))
 manifest=p.parent/'manifest.json'
 obj=json.loads(manifest.read_text()) if manifest.exists() else {'files':{}}
 raw=p.read_bytes();obj['files'][p.name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 manifest.write_text(json.dumps(obj))

def test_healthy_and_lkg(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'core.json',now); touch(tmp_path/'ctx.json',now)
 o=h.derive_health(reg(),[],tmp_path,now); assert o['summary']['overall_health']=='HEALTHY'; assert all(x['last_known_good'] for x in o['layers'])

def test_stale_critical_degrades(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'core.json',now-timedelta(days=3)); touch(tmp_path/'ctx.json',now)
 o=h.derive_health(reg(),[],tmp_path,now); assert o['summary']['overall_health']=='DEGRADED'; assert o['layers'][0]['state']=='STALE'

def test_failed_critical_is_not_false_healthy(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'core.json',now); touch(tmp_path/'ctx.json',now)
 led=[{'finished_at':now.isoformat(),'steps':[{'node_id':'core','status':'FAILED','reason':'collector failed'}]}]
 o=h.derive_health(reg(),led,tmp_path,now); assert o['summary']['overall_health']=='FAILED'; assert o['layers'][0]['failure_reason']=='collector failed'

def test_blocked_visible(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'core.json',now); touch(tmp_path/'ctx.json',now)
 led=[{'finished_at':now.isoformat(),'steps':[{'node_id':'ctx','status':'BLOCKED','reason':'upstream failure'}]}]
 o=h.derive_health(reg(),led,tmp_path,now); assert [x for x in o['layers'] if x['id']=='ctx'][0]['state']=='BLOCKED'

def test_missing_output_failed(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'ctx.json',now)
 o=h.derive_health(reg(),[],tmp_path,now); assert o['summary']['overall_health']=='FAILED'

def test_publish_contract(tmp_path):
 now=datetime(2026,9,30,tzinfo=timezone.utc); touch(tmp_path/'core.json',now); touch(tmp_path/'ctx.json',now)
 o=h.derive_health(reg(),[],tmp_path,now); h.publish(o,tmp_path)
 assert json.loads((tmp_path/'system_health_summary_v1.json').read_text())['research_only'] is True
 assert len(json.loads((tmp_path/'system_health_layers_v1.json').read_text()))==2
