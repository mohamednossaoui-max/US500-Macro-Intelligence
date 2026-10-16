"""Dispatch a pinned workflow and identify it by a unique run-name token."""
import argparse,json,os,subprocess,sys,time,uuid

def gh(args):return subprocess.check_output(['gh']+args,text=True)
def select_run(runs,token,sha):
    matches=[r for r in runs if r.get('displayTitle','').endswith('['+token+']') and r.get('headSha')==sha and r.get('event')=='workflow_dispatch']
    if len(matches)>1:raise RuntimeError('Ambiguous correlated runs; refuse artifact selection')
    return str(matches[0]['databaseId']) if matches else None

def main():
    ap=argparse.ArgumentParser();ap.add_argument('workflow');ap.add_argument('--ref',default='main');ap.add_argument('--sha',required=True);ap.add_argument('--field',action='append',default=[]);a=ap.parse_args()
    token=uuid.uuid4().hex
    args=['workflow','run',a.workflow,'--ref',a.ref,'-f','correlation_id='+token,'-f','source_ref='+a.sha]
    for f in a.field:args+=['-f',f]
    subprocess.run(['gh']+args,check=True,stdout=sys.stderr)
    for attempt in range(45):
        runs=json.loads(gh(['run','list','--workflow',a.workflow,'--branch',a.ref,'--limit','100','--json','databaseId,displayTitle,headSha,event']))
        run=select_run(runs,token,a.sha)
        if run:print(run);return
        time.sleep(2)
    raise SystemExit('No uniquely correlated run found; refuse latest-run fallback')
if __name__=='__main__':main()
