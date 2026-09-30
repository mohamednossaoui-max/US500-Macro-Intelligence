from __future__ import annotations
import argparse, json, os, shutil, tempfile, uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from autonomy_dependency_planner_v1 import load_registry, affected

ROOT = Path(__file__).resolve().parent
PUBLIC_DATA = ROOT / 'public_data'
LEDGER = ROOT / 'autonomy_run_ledger_v1.jsonl'

@dataclass
class StepResult:
    node_id: str
    status: str
    reason: str = ''

class OrchestrationError(RuntimeError): pass


def _utcnow(): return datetime.now(timezone.utc).isoformat()

def _node_map(reg): return {n['id']: n for n in reg['nodes']}

def build_plan(reg, changed):
    return affected(reg['nodes'], changed)

def _copy_public_data(src: Path, dst: Path):
    if dst.exists(): shutil.rmtree(dst)
    shutil.copytree(src, dst)

def validate_node_outputs(node, staging_public: Path):
    missing=[x for x in node.get('outputs',[]) if not (staging_public/x).is_file()]
    if missing: raise OrchestrationError(f"{node['id']} missing outputs: {missing}")
    empty=[x for x in node.get('outputs',[]) if (staging_public/x).stat().st_size == 0]
    if empty: raise OrchestrationError(f"{node['id']} empty outputs: {empty}")
    return True

def atomic_publish(staging_public: Path, live_public: Path, failpoint: str|None=None):
    """Directory-swap publication with rollback. Never leaves a partial live tree."""
    parent=live_public.parent
    incoming=parent/(live_public.name+'.incoming')
    backup=parent/(live_public.name+'.lkg')
    for p in (incoming, backup):
        if p.exists(): shutil.rmtree(p)
    shutil.copytree(staging_public, incoming)
    if failpoint == 'before_swap':
        shutil.rmtree(incoming); raise OrchestrationError('injected publication failure before swap')
    moved_live=False
    try:
        os.replace(live_public, backup); moved_live=True
        if failpoint == 'after_backup': raise OrchestrationError('injected publication failure after backup')
        os.replace(incoming, live_public)
        if failpoint == 'after_swap': raise OrchestrationError('injected publication failure after swap')
        shutil.rmtree(backup)
    except Exception:
        if live_public.exists() and moved_live: shutil.rmtree(live_public)
        if moved_live and backup.exists(): os.replace(backup, live_public)
        if incoming.exists(): shutil.rmtree(incoming)
        raise


def run_orchestration(changed, registry_path=None, live_public=PUBLIC_DATA, ledger_path=LEDGER,
                      executor: Callable|None=None, publish=False, fail_node=None, publish_failpoint=None):
    """Safe orchestrator. Default executor is validation-only; no workflow is executed implicitly.

    executor(node, staging_root, staging_public) may mutate staging and must raise on failure.
    Publication is opt-in and occurs only after every planned node validates.
    """
    reg=load_registry(registry_path) if registry_path else load_registry()
    if not reg['policy'].get('atomic_publication_required') or not reg['policy'].get('last_known_good_required'):
        raise OrchestrationError('registry safety policy is not sufficient')
    plan=build_plan(reg, changed); by=_node_map(reg)
    run_id=str(uuid.uuid4()); started=_utcnow(); steps=[]
    tmp=Path(tempfile.mkdtemp(prefix='us500-autonomy-'))
    staging_root=tmp/'repo'; staging_public=staging_root/'public_data'
    staging_root.mkdir(parents=True)
    _copy_public_data(Path(live_public), staging_public)
    status='RUNNING'; published=False
    try:
        blocked=False
        for node_id in plan:
            node=by[node_id]
            if blocked:
                steps.append(StepResult(node_id,'BLOCKED','upstream failure')); continue
            try:
                if node_id == fail_node: raise OrchestrationError('injected node failure')
                if executor: executor(node, staging_root, staging_public)
                validate_node_outputs(node, staging_public)
                steps.append(StepResult(node_id,'PASSED'))
            except Exception as e:
                steps.append(StepResult(node_id,'FAILED',str(e))); blocked=True; status='FAILED'
        if status != 'FAILED':
            status='VALIDATED'
            if publish:
                atomic_publish(staging_public, Path(live_public), publish_failpoint)
                published=True; status='PUBLISHED'
    except Exception as e:
        status='FAILED'
        if not any(s.status=='FAILED' for s in steps): steps.append(StepResult('publication','FAILED',str(e)))
    finally:
        record={'run_id':run_id,'started_at':started,'finished_at':_utcnow(),'changed':list(changed),
                'plan':plan,'status':status,'published':published,'manual_mode_preserved':reg['policy'].get('manual_mode_preserved',False),
                'steps':[asdict(x) for x in steps]}
        lp=Path(ledger_path); lp.parent.mkdir(parents=True,exist_ok=True)
        with lp.open('a',encoding='utf-8') as f: f.write(json.dumps(record,sort_keys=True)+'\n')
        shutil.rmtree(tmp,ignore_errors=True)
    return record


def main():
    ap=argparse.ArgumentParser(description='US500 safe autonomous orchestrator (validation/dry-run by default).')
    ap.add_argument('--changed',nargs='+',required=True); ap.add_argument('--registry'); ap.add_argument('--publish',action='store_true')
    args=ap.parse_args()
    if args.publish:
        raise SystemExit('Direct CLI publication is disabled in v1; use the tested CI executor in Stage 13C.')
    rec=run_orchestration(args.changed, registry_path=args.registry, publish=False)
    print(json.dumps(rec,indent=2))

if __name__=='__main__': main()
