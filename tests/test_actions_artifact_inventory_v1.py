import json
from pathlib import Path
import subprocess
import sys
import pytest
from scripts.actions_artifact_inventory_v1 import flatten,select


def artifact(i,name='unrelated',expired=False,date='2026-10-01T00:00:00Z'):
    return {'id':i,'name':name,'expired':expired,'created_at':date}


def test_sources_after_first_hundred_are_found():
    first={'artifacts':[artifact(i) for i in range(1,101)]}
    second={'artifacts':[artifact(101,'cot-historical-v1'),artifact(102,'aaii-historical-v1'),artifact(103,'vix-historical-v1')]}
    inventory=flatten([first,second])
    assert inventory['pages_scanned']==2 and inventory['total_count']==103
    assert select(inventory,'cot-historical-v1')['id']==101
    assert select(inventory,'aaii-historical-v1')['id']==102


def test_expired_newer_and_other_types_do_not_replace_source():
    inventory=flatten([{'artifacts':[artifact(1,'cot-historical-v1'),artifact(2,'cot-historical-v1',True,'2026-10-05T00:00:00Z'),artifact(3,'cot-positioning-v1')]}])
    assert select(inventory,'cot-historical-v1')['id']==1
    with pytest.raises(ValueError):select(inventory,'aaii-historical-v1')


def test_duplicate_inventory_deterministic_and_conflict_blocked():
    a=artifact(1,'vix-historical-v1');b=artifact(2,'vix-historical-v1')
    assert select(flatten([{'artifacts':[a,b,a]}]),'vix-historical-v1')['id']==2
    assert flatten([{'artifacts':[a,b]}])==flatten([{'artifacts':[b,a]}])
    with pytest.raises(ValueError):flatten([{'artifacts':[a,{**a,'expired':True}]}])


@pytest.mark.parametrize('data',[[],{},[{}],[{'artifacts':[{'id':1}]}]])
def test_malformed_inventory_never_success(data):
    with pytest.raises(ValueError):flatten(data)


def test_cli_pagination_and_missing_source_fail(tmp_path):
    root=Path(__file__).resolve().parents[1];page=tmp_path/'pages.json';out=tmp_path/'artifacts.json'
    page.write_text(json.dumps([{'artifacts':[artifact(1,'cot-historical-v1')]},{'artifacts':[artifact(2,'aaii-historical-v1')]}]))
    args=[sys.executable,str(root/'scripts/actions_artifact_inventory_v1.py'),'--pages',str(page),'--output',str(out)]
    r=subprocess.run(args+['--name','aaii-historical-v1'],capture_output=True,text=True)
    assert r.returncode==0 and r.stdout.strip()=='2'
    assert json.loads(out.read_text())['pages_scanned']==2
    r=subprocess.run(args+['--name','vix-historical-v1'],capture_output=True,text=True)
    assert r.returncode==1 and 'refresh the source' in r.stderr
