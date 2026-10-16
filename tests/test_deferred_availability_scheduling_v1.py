from datetime import datetime,timezone
import json
import pytest
import autonomy_due_detector_v1 as dd
from scripts.breadth_validation_report_v1 import build_report,PATHS
NOW=datetime(2026,10,16,17,tzinfo=timezone.utc)

def run(tmp_path,node_id,body):
    name=dd.DEFERRED_FILES.get(node_id,'other.csv')
    public=tmp_path/'public_data';public.mkdir()
    p=public/name;p.write_text(body)
    before=p.read_bytes()
    r=dd.detect_due({'nodes':[{'id':node_id,'frequency':'daily','depends_on':[],'outputs':[name]}]},NOW,tmp_path)
    assert p.read_bytes()==before
    return r['detail'][0]

@pytest.mark.parametrize('node_id',['technical','cross_asset'])
def test_known_next_day_proxy_waits_without_releasing_row(tmp_path,node_id):
    r=run(tmp_path,node_id,'observation_date,availability_date\n2026-10-15,2026-10-16\n2026-10-16,2026-10-17\n')
    assert r['due'] is False
    assert r['reason']=='DEFERRED_AVAILABILITY_WAIT'
    assert r['pending_available_at']=='2026-10-17T00:00:00+00:00'
    assert r['last_data_at']=='2026-10-16T00:00:00+00:00'

@pytest.mark.parametrize('node_id,obs,avail',[
    ('technical','2026-10-17','2026-10-18'),
    ('technical','2026-10-16','2026-10-19'),
    ('technical','2026-10-16','2026-10-17T03:00:00+00:00'),
    ('other','2026-10-16','2026-10-17')])
def test_future_anomalies_still_require_check(tmp_path,node_id,obs,avail):
    r=run(tmp_path,node_id,'observation_date,availability_date\n'+obs+','+avail+'\n')
    assert r['due'] is True
    assert r['reason']=='FUTURE_CONTENT_DATE'

def test_invalid_older_row_prevents_exception(tmp_path):
    r=run(tmp_path,'technical','observation_date,availability_date\nbad,bad\n2026-10-16,2026-10-17\n')
    assert r['due'] is True

def test_old_completed_data_remains_due(tmp_path):
    r=run(tmp_path,'technical','observation_date,availability_date\n2026-10-13,2026-10-14\n')
    assert r['due'] is True
    assert r['reason']=='CONTENT_AGE_DUE'

@pytest.mark.parametrize('complete,status',[(False,'STALE'),(True,'CURRENT'),(None,'UNKNOWN')])
def test_breadth_validation_distinct_from_freshness(tmp_path,complete,status):
    for name in PATHS.values():
        p=tmp_path/name;p.parent.mkdir(exist_ok=True);p.write_text(json.dumps({'validation_pass':True}))
    m=tmp_path/'market_breadth_historical_v1/market_breadth_metadata_v1.json'
    m.write_text(json.dumps({'requested_range_complete':complete}))
    r=build_report(tmp_path)
    assert r['final_status']=='PASS'
    assert r['data_status']==status
    assert r['freshness_pass'] is (status=='CURRENT')
    assert bool(r['warnings']) is (status=='STALE')
