import json, shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
import autonomy_due_detector_v1 as dd
import autonomy_orchestrator_v1 as ao
from scripts.rebuild_publication_manifest import rebuild
ROOT=Path(__file__).resolve().parents[1]; REG=ROOT/'autonomy_source_registry_v1.json'

def test_single_schedule_entrypoint_and_manual_mode():
    reg=ao.load_registry(REG); p=reg['policy']
    assert p['schedules_enabled'] is True and p['manual_mode_preserved'] is True
    assert p['single_orchestrator'] is True and p['schedule_entrypoint'].endswith('autonomous-intelligence-pipeline-v1.yml')

def test_macro_context_is_in_dependency_chain():
    reg=ao.load_registry(REG); plan=ao.build_plan(reg,['economic'])
    assert plan.index('economic') < plan.index('macro_context') < plan.index('research_context') < plan.index('decision_intelligence') < plan.index('publication')

def test_due_detector_uses_root_sources_and_expands_plan(monkeypatch):
    reg=ao.load_registry(REG); old=datetime.now(timezone.utc)-timedelta(days=20)
    monkeypatch.setattr(dd,'_git_last_change',lambda *a,**k: old)
    out=dd.detect_due(reg,datetime.now(timezone.utc),ROOT)
    assert 'economic' in out['due_roots'] and 'research_context' not in out['due_roots']
    assert 'research_context' in out['plan'] and out['plan'][-1]=='publication'

def test_success_cycle_can_publish_atomically(tmp_path):
    live=tmp_path/'public_data'; shutil.copytree(ROOT/'public_data',live); ledger=tmp_path/'ledger.jsonl'
    r=ao.run_orchestration(['technical'],REG,live,ledger,publish=True)
    assert r['status']=='PUBLISHED' and r['published'] and r['plan'][-1]=='publication'

def test_failure_cycle_preserves_lkg(tmp_path):
    live=tmp_path/'public_data'; shutil.copytree(ROOT/'public_data',live); before=(live/'manifest.json').read_bytes(); ledger=tmp_path/'ledger.jsonl'
    r=ao.run_orchestration(['technical'],REG,live,ledger,publish=True,fail_node='research_context')
    assert r['status']=='FAILED' and not r['published'] and (live/'manifest.json').read_bytes()==before

def test_manifest_rebuild_is_self_consistent(tmp_path):
    live=tmp_path/'public_data'; shutil.copytree(ROOT/'public_data',live)
    m=rebuild(live,'stage13c-test'); assert 'manifest.json' not in m['files'] and len(m['files'])>0
    obj=json.loads((live/'manifest.json').read_text()); assert obj['files']==m['files']
