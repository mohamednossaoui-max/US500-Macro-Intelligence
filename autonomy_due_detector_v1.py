from __future__ import annotations
import argparse, json, subprocess
from datetime import datetime, timezone
from pathlib import Path
from autonomy_dependency_planner_v1 import load_registry, affected

ROOT=Path(__file__).resolve().parent
CADENCE_DAYS={'daily':1,'daily_weekly':1,'weekly':7,'release_driven':1}

def _git_last_change(path:Path, repo:Path=ROOT):
    try:
        p=subprocess.run(['git','log','-1','--format=%ct','--',str(path.relative_to(repo))],cwd=repo,text=True,capture_output=True,check=False)
        if p.returncode==0 and p.stdout.strip(): return datetime.fromtimestamp(int(p.stdout.strip()),tz=timezone.utc)
    except Exception: pass
    if path.exists(): return datetime.fromtimestamp(path.stat().st_mtime,tz=timezone.utc)
    return None

def root_nodes(reg): return [n for n in reg['nodes'] if not n.get('depends_on') and n.get('kind')!='publication_gate']

def detect_due(reg, now=None, repo=ROOT):
    now=now or datetime.now(timezone.utc); repo=Path(repo); due=[]; detail=[]
    for n in root_nodes(reg):
        cadence=CADENCE_DAYS.get(n.get('frequency'),1)
        stamps=[]
        for out in n.get('outputs',[]):
            ts=_git_last_change(repo/'public_data'/out,repo)
            if ts: stamps.append(ts)
        last=max(stamps) if stamps else None
        age=(now-last).total_seconds()/86400 if last else None
        is_due=(last is None) or age>=cadence
        detail.append({'id':n['id'],'frequency':n.get('frequency'),'cadence_days':cadence,'last_change':last.isoformat() if last else None,'age_days':round(age,2) if age is not None else None,'due':is_due})
        if is_due: due.append(n['id'])
    plan=affected(reg['nodes'],due) if due else []
    return {'as_of':now.isoformat(),'due_roots':due,'plan':plan,'detail':detail}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--registry'); ap.add_argument('--json',action='store_true'); args=ap.parse_args()
    reg=load_registry(args.registry) if args.registry else load_registry(); out=detect_due(reg)
    if args.json: print(json.dumps(out,indent=2))
    else:
        print('DUE_ROOTS='+' '.join(out['due_roots'])); print('PLAN='+' '.join(out['plan']))
if __name__=='__main__': main()
