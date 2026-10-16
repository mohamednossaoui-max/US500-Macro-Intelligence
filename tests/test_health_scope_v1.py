from datetime import datetime, timezone, timedelta
import json,hashlib
import pytest
import system_health_monitor_v1 as health

NOW=datetime(2026,10,16,18,tzinfo=timezone.utc)

def setup(root,core_age=0,core_missing=False):
    manifest={'files':{}}
    nodes=[]
    for name,age,excluded in [('core',core_age,False),('breadth',59,True),('cross_asset',0,True)]:
        node={'id':name,'kind':'source_layer','criticality':'critical' if name=='core' else 'contextual',
              'freshness_sla_days':5,'pit_policy':'PIT_LIMITED' if name=='cross_asset' else 'availability-date',
              'outputs':[name+'.json'],'depends_on':[]}
        if excluded:node['affects_system_health']=False
        nodes.append(node)
        if name=='core' and core_missing:continue
        raw=json.dumps({'as_of_date':(NOW-timedelta(days=age)).isoformat()}).encode()
        (root/(name+'.json')).write_bytes(raw)
        manifest['files'][name+'.json']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    (root/'manifest.json').write_text(json.dumps(manifest))
    return {'nodes':nodes}

def test_excluded_layers_keep_states_and_attention(tmp_path):
    r=health.derive_health(setup(tmp_path),[],tmp_path,NOW)
    assert r['summary']['overall_health']=='HEALTHY'
    assert r['summary']['attention']==2 and r['summary']['stale']==1
    assert r['summary']['excluded_from_overall']==['breadth','cross_asset']
    assert r['summary']['assessed_layer_count']==1
    assert [x['state'] for x in r['layers']]==['HEALTHY','STALE','PIT_LIMITED']

@pytest.mark.parametrize('age,missing,expected',[(10,False,'DEGRADED'),(0,True,'FAILED')])
def test_core_failures_still_control_summary(tmp_path,age,missing,expected):
    r=health.derive_health(setup(tmp_path,age,missing),[],tmp_path,NOW)
    assert r['summary']['overall_health']==expected

def test_failed_observational_layer_visible(tmp_path):
    reg=setup(tmp_path)
    ledger=[{'finished_at':NOW.isoformat(),'steps':[{'node_id':'breadth','status':'FAILED','reason':'test failure'}]}]
    r=health.derive_health(reg,ledger,tmp_path,NOW)
    assert r['summary']['overall_health']=='HEALTHY'
    assert r['summary']['failed']==1
    assert r['layers'][1]['state']=='FAILED'
    assert r['layers'][1]['failure_reason']=='test failure'

def test_exclusion_is_reversible(tmp_path):
    reg=setup(tmp_path);reg['nodes'][1]['affects_system_health']=True
    assert health.derive_health(reg,[],tmp_path,NOW)['summary']['overall_health']=='DEGRADED'

def test_only_boolean_false_excludes(tmp_path):
    reg=setup(tmp_path);reg['nodes'][1]['affects_system_health']='False'
    assert health.derive_health(reg,[],tmp_path,NOW)['summary']['overall_health']=='DEGRADED'

def test_stale_monitor_and_failed_pipeline_still_override(tmp_path):
    r=health.derive_health(setup(tmp_path),[],tmp_path,NOW)['summary']
    assert health.display_summary(r,NOW+timedelta(days=2))['overall_health']=='DEGRADED'
    attempt={'status':'FAILED','attempted_at':NOW.isoformat()}
    assert health.display_summary(r,NOW,attempt)['overall_health']=='FAILED'

def test_registry_scopes_only_requested_layers():
    r=health.load_registry()
    assert {n['id'] for n in r['nodes'] if n.get('affects_system_health') is False}=={'breadth','cross_asset'}
