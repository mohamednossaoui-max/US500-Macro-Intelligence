import hashlib, json, shutil
from pathlib import Path
import pytest
import autonomy_orchestrator_v1 as ao

ROOT=Path(__file__).resolve().parents[1]
REG=ROOT/'autonomy_source_registry_v1.json'

def tree_hash(p):
    h=hashlib.sha256()
    for f in sorted(x for x in p.rglob('*') if x.is_file()):
        h.update(str(f.relative_to(p)).encode()); h.update(f.read_bytes())
    return h.hexdigest()

def sandbox(tmp_path):
    live=tmp_path/'public_data'; shutil.copytree(ROOT/'public_data',live)
    return live,tmp_path/'ledger.jsonl'

def test_happy_path_validates_without_publication(tmp_path):
    live,ledger=sandbox(tmp_path); before=tree_hash(live)
    r=ao.run_orchestration(['economic'],REG,live,ledger,publish=False)
    assert r['status']=='VALIDATED' and not r['published']
    assert tree_hash(live)==before
    assert r['plan'][0]=='economic' and r['plan'][-1]=='publication'

def test_failure_blocks_downstream_and_preserves_lkg(tmp_path):
    live,ledger=sandbox(tmp_path); before=tree_hash(live)
    r=ao.run_orchestration(['economic'],REG,live,ledger,publish=False,fail_node='research_context')
    assert r['status']=='FAILED' and not r['published'] and tree_hash(live)==before
    st={x['node_id']:x['status'] for x in r['steps']}
    assert st['research_context']=='FAILED' and st['evidence_quality']=='BLOCKED' and st['publication']=='BLOCKED'

def test_missing_output_fails_validation(tmp_path):
    live,ledger=sandbox(tmp_path); before=tree_hash(live)
    def executor(node,root,pub):
        if node['id']=='technical': (pub/node['outputs'][0]).unlink(missing_ok=True)
    r=ao.run_orchestration(['technical'],REG,live,ledger,executor=executor)
    assert r['status']=='FAILED' and tree_hash(live)==before
    assert r['steps'][0]['node_id']=='technical' and r['steps'][0]['status']=='FAILED'

def test_atomic_publish_success_and_ledger(tmp_path):
    live,ledger=sandbox(tmp_path)
    def executor(node,root,pub):
        if node['id']=='economic': (pub/'stage13b_probe.txt').write_text('validated',encoding='utf-8')
    r=ao.run_orchestration(['economic'],REG,live,ledger,executor=executor,publish=True)
    assert r['status']=='PUBLISHED' and r['published']
    assert (live/'stage13b_probe.txt').read_text()=='validated'
    row=json.loads(ledger.read_text().splitlines()[-1]); assert row['run_id']==r['run_id'] and row['status']=='PUBLISHED'

def test_atomic_publish_failure_rolls_back(tmp_path):
    live,ledger=sandbox(tmp_path); before=tree_hash(live)
    def executor(node,root,pub):
        if node['id']=='economic': (pub/'stage13b_probe.txt').write_text('must rollback')
    r=ao.run_orchestration(['economic'],REG,live,ledger,executor=executor,publish=True,publish_failpoint='after_backup')
    assert r['status']=='FAILED' and not r['published'] and tree_hash(live)==before
    assert not (live/'stage13b_probe.txt').exists()

def test_manual_mode_and_cli_publish_guard():
    reg=ao.load_registry(REG)
    assert reg['policy']['manual_mode_preserved'] is True
    assert reg['policy']['schedules_enabled'] is False
