from __future__ import annotations
import argparse, csv, json, subprocess
from datetime import datetime, timezone, timedelta
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

# Availability/publication takes precedence over the observation period.
DATE_FIELDS=('available_at_utc','availability_date','available_at','available_as_of',
             'published_at','release_date','asof_date','context_date','as_of_date',
             'date','observation_date')
JSON_FIELDS=('latest_asof_date','analysis_date_end','date_end', 'context_date',
             'as_of_date','asof_date','as_of')

def _parse_date(value):
    try:
        stamp=datetime.fromisoformat(str(value).strip().replace('Z','+00:00'))
        return stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)
    except (ValueError,TypeError): return None

def _content_date(path):
    """Read only data dates; copying, committing and JSON generation cannot refresh them."""
    try:
        if path.suffix.lower()=='.csv':
            with path.open(encoding='utf-8-sig',newline='') as handle:
                reader=csv.DictReader(handle)
                names={n.lower():n for n in reader.fieldnames or []}
                column=next((names[n] for n in DATE_FIELDS if n in names),None)
                if column is None: return None
                newest=None
                for row in reader:
                    stamp=_parse_date(row.get(column))
                    if stamp is not None and (newest is None or stamp>newest): newest=stamp
                return newest
        if path.suffix.lower()=='.json':
            obj=json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(obj,dict): return None
            key=next((n for n in JSON_FIELDS if obj.get(n)),None)
            return _parse_date(obj[key]) if key else None
    except (OSError,ValueError,TypeError,csv.Error): pass
    return None

# These two producers explicitly use observation_date + 1 calendar day.
# This exception controls scheduling only; it never releases future evidence.
DEFERRED_FILES={'technical':'technical_intelligence_research_v1.csv',
                'cross_asset':'cross_asset_research_v1.csv'}

def _deferred_observation(node_id, path, now):
    if DEFERRED_FILES.get(node_id)!=path.name: return None
    try:
        with path.open(encoding='utf-8-sig',newline='') as handle:
            rows=csv.DictReader(handle)
            if not {'observation_date','availability_date'}<=set(rows.fieldnames or []): return None
            latest=None
            for row in rows:
                obs=_parse_date(row.get('observation_date'))
                avail=_parse_date(row.get('availability_date'))
                if obs is None or avail is None: return None
                if obs>now or avail!=obs+timedelta(days=1): return None
                if latest is None or obs>latest: latest=obs
            return latest if latest is not None and latest.date()==now.date() else None
    except (OSError,ValueError,TypeError,csv.Error): return None

def root_nodes(reg): return [n for n in reg['nodes'] if not n.get('depends_on') and n.get('kind')!='publication_gate']

def detect_due(reg, now=None, repo=ROOT):
    now=now or datetime.now(timezone.utc); repo=Path(repo); due=[]; detail=[]
    for n in root_nodes(reg):
        cadence=CADENCE_DAYS.get(n.get('frequency'),1)
        outputs=n.get('freshness_outputs',n.get('outputs',[]))
        stamps=[]; pending=[]
        for name in outputs:
            path=repo/'public_data'/name
            stamp=_content_date(path)
            if stamp is not None and stamp>now:
                observation=_deferred_observation(n['id'],path,now)
                if observation is not None:
                    pending.append(stamp)
                    stamp=observation
            stamps.append(stamp)
        known=bool(stamps) and all(ts is not None for ts in stamps)
        future=any(ts is not None and ts>now for ts in stamps)
        last=min(stamps) if known else None
        age=(now-last).total_seconds()/86400 if last else None
        forced=n.get('frequency')=='release_driven' or n['id'] in {'economic','event_news'}
        is_due=forced or not known or future or age>=cadence
        reason=('RELEASE_CHECK_REQUIRED' if forced else 'MISSING_OR_UNDATED_CONTENT' if not known
                else 'FUTURE_CONTENT_DATE' if future else 'CONTENT_AGE_DUE' if is_due else 'DEFERRED_AVAILABILITY_WAIT' if pending else 'CONTENT_WITHIN_CADENCE')
        detail.append({'id':n['id'],'frequency':n.get('frequency'),'cadence_days':cadence,
                       'last_change':last.isoformat() if last else None,
                       'last_data_at':last.isoformat() if last else None,'freshness_basis':'CONTENT',
                       'scheduling_basis':'OBSERVATION_WITH_DEFERRED_AVAILABILITY' if pending else 'CONTENT_AVAILABILITY',
                       'pending_available_at':max(pending).isoformat() if pending else None,
                       'age_days':round(age,2) if age is not None else None,'due':is_due,'reason':reason})
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
