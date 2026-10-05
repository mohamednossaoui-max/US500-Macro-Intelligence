"""Normalize every gh --paginate --slurp page; fail closed on missing artifacts.

Existence is not data freshness. Existing downstream validation stays in charge.
"""
from pathlib import Path
import argparse
import json
import sys


def flatten(payload):
    pages=payload if isinstance(payload,list) else [payload]
    if not pages:raise ValueError('No artifact API pages returned')
    by_id={}
    for page in pages:
        if not isinstance(page,dict) or not isinstance(page.get('artifacts'),list):
            raise ValueError('Malformed artifact API page')
        for artifact in page['artifacts']:
            if not isinstance(artifact,dict) or not isinstance(artifact.get('id'),int):
                raise ValueError('Invalid artifact identity')
            if not isinstance(artifact.get('name'),str) or not isinstance(artifact.get('created_at'),str) or not isinstance(artifact.get('expired'),bool):
                raise ValueError('Incomplete artifact selection metadata')
            key=artifact['id']
            if key in by_id and by_id[key]!=artifact:raise ValueError('Conflicting duplicate artifact across pages; retry discovery')
            by_id[key]=artifact
    rows=sorted(by_id.values(),key=lambda r:(r['created_at'],r['id']),reverse=True)
    return {'total_count':len(rows),'pages_scanned':len(pages),'artifacts':rows}


def select(inventory,name):
    candidates=[a for a in inventory['artifacts'] if a['name']==name and a['expired'] is False]
    if not candidates:raise ValueError('No non-expired '+name+' artifact found after scanning '+str(inventory['pages_scanned'])+' pages; refresh the source workflow')
    return max(candidates,key=lambda a:(a['created_at'],a['id']))


def main():
    p=argparse.ArgumentParser();p.add_argument('--pages',type=Path,required=True)
    p.add_argument('--output',type=Path);p.add_argument('--name');a=p.parse_args()
    try:
        inventory=flatten(json.loads(a.pages.read_text()))
        if a.output:a.output.write_text(json.dumps(inventory,indent=2)+'\n')
        if a.name:print(select(inventory,a.name)['id'])
        elif not a.output:p.error('--output or --name required')
    except (ValueError,OSError) as e:
        print('Artifact discovery blocked: '+str(e),file=sys.stderr);return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
