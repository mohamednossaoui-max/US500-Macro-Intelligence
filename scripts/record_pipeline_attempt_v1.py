"""Publish only operational metadata against an already verified data generation."""
import argparse,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.verify_publication_integrity import run as verify

def record(public,status,run_id,run_url='',now=None):
    public=Path(public);report=verify(public)
    if report['errors'] or any(report['manifests'][0]['summary'][k] for k in ('mismatch','missing','error')):
        raise ValueError('Refuse operational update on an unverified publication')
    if status not in {'SUCCESS','FAILED','BLOCKED','CANCELLED'}:raise ValueError('Unknown attempt status')
    manifest=json.loads((public/'manifest.json').read_text())
    stamp=(now or datetime.now(timezone.utc)).isoformat()
    obj={'status':status,'attempted_at':stamp,'run_id':str(run_id),'run_url':run_url,
         'data_source_run_id':manifest.get('source_run_id'),
         'message':'Last verified research data retained; inspect workflow diagnostics.' if status!='SUCCESS' else 'Integrated publication passed its validation gate.',
         'research_scores_changed':False}
    raw=(json.dumps(obj,indent=2)+'\n').encode();(public/'pipeline_attempt_v1.json').write_bytes(raw)
    manifest['files']['pipeline_attempt_v1.json']={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
    manifest['generation_id']=hashlib.sha256(json.dumps(manifest['files'],sort_keys=True).encode()).hexdigest()
    manifest['operational_update_run_id']=str(run_id)
    (public/'manifest.json').write_text(json.dumps(manifest,indent=2,sort_keys=True)+'\n')
    return obj

def main():
    p=argparse.ArgumentParser();p.add_argument('--public-data',default='public_data');p.add_argument('--status',required=True);a=p.parse_args()
    run=os.getenv('GITHUB_RUN_ID','offline');repo=os.getenv('GITHUB_REPOSITORY','')
    url='https://github.com/'+repo+'/actions/runs/'+run if repo else ''
    print(json.dumps(record(a.public_data,a.status,run,url),indent=2))
if __name__=='__main__':main()
