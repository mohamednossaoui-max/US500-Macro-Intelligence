import json
import os
from datetime import datetime, timezone
import pytest
import autonomy_due_detector_v1 as dd

NOW=datetime(2026,10,16,12,tzinfo=timezone.utc)

def reg(outputs=None,frequency='daily',node_id='technical'):
    return {'nodes':[{'id':node_id,'frequency':frequency,'outputs':outputs or ['data.csv'],'depends_on':[]},
                     {'id':'research_context','depends_on':[node_id],'outputs':['ctx.csv']}]}

def write(root,name,text):
    folder=root/'public_data';folder.mkdir(exist_ok=True)
    (folder/name).write_text(text)

@pytest.mark.parametrize('date,due', [('2026-09-01',True),('2026-10-16',False),('2026-10-17',True)])
def test_content_overrides_file_timestamp(tmp_path,date,due):
    write(tmp_path,'data.csv','observation_date,value\n'+date+',1\n')
    os.utime(tmp_path/'public_data/data.csv',None)
    out=dd.detect_due(reg(),NOW,tmp_path)
    assert ('technical' in out['due_roots']) is due
    assert out['detail'][0]['freshness_basis']=='CONTENT'
    assert ('research_context' in out['plan']) is due

@pytest.mark.parametrize('body',['value\n1\n','observation_date\ninvalid\n'])
def test_unknown_dates_require_check(tmp_path,body):
    write(tmp_path,'data.csv',body)
    assert dd.detect_due(reg(),NOW,tmp_path)['due_roots']==['technical']

def test_missing_file_requires_check(tmp_path):
    assert dd.detect_due(reg(),NOW,tmp_path)['due_roots']==['technical']

def test_oldest_required_output_bounds_node(tmp_path):
    write(tmp_path,'data.csv','availability_date\n2026-10-16\n')
    write(tmp_path,'old.csv','availability_date\n2026-09-01\n')
    assert dd.detect_due(reg(['data.csv','old.csv']),NOW,tmp_path)['due_roots']==['technical']

def test_weekly_available_date_not_observation_date(tmp_path):
    write(tmp_path,'data.csv','observation_date,availability_date\n2026-10-06,2026-10-13\n')
    assert not dd.detect_due(reg(frequency='weekly'),NOW,tmp_path)['due_roots']

def test_new_generation_does_not_refresh_old_json(tmp_path):
    write(tmp_path,'data.json',json.dumps({'generated_at':'2026-10-16','latest_asof_date':'2026-09-01'}))
    assert dd.detect_due(reg(['data.json']),NOW,tmp_path)['due_roots']==['technical']

def test_release_source_checked_even_with_current_data(tmp_path):
    write(tmp_path,'data.csv','availability_date\n2026-10-16\n')
    assert dd.detect_due(reg(node_id='economic'),NOW,tmp_path)['due_roots']==['economic']

def test_no_git_or_mtime_fallback(tmp_path,monkeypatch):
    write(tmp_path,'data.csv','availability_date\n2026-09-01\n')
    def forbidden(*args,**kwargs): raise AssertionError('Git date must not determine freshness')
    monkeypatch.setattr(dd,'_git_last_change',forbidden)
    assert dd.detect_due(reg(),NOW,tmp_path)['due_roots']==['technical']
