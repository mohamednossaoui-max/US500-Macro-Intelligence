"""Offline revalidation of acquired provider receipts; never fabricates data."""
from pathlib import Path
import argparse
import json
import pandas as pd
from ath_official_vintage_backfill_v1 import backfill,load_receipts,SourceError,SERIES


def replay(events,acquisition_audit,cache,output):
    audit=json.loads(Path(acquisition_audit).read_text())
    receipts=load_receipts(cache)
    for row in audit['results']:
        if row.get('receipt_sha256'):
            saved=receipts.get((row['series'],row['as_of_date']))
            if not saved or saved['sha']!=row['receipt_sha256']:raise SourceError('Acquisition audit/receipt mismatch')
    class Offline:
        def get(self,endpoint,params):
            sid=params['series_id']
            if endpoint=='series':
                saved=next((v for (s,_),v in receipts.items() if s==sid),None)
                if not saved:raise SourceError('No acquired series metadata')
                return {'seriess':[saved['record']['metadata']]}
            if endpoint=='series/vintagedates':
                first=audit.get('first_provider_vintages',{}).get(sid)
                if not first or sid in audit.get('archive_metadata_errors',{}):raise SourceError('No verified acquired archive boundary')
                return {'vintage_dates':[first]}
            raise SourceError('Missing acquired receipt; offline replay cannot fetch or substitute')
    decisions=pd.to_datetime(events.decision_at,utc=True).drop_duplicates()
    requested={(sid,(d-pd.Timedelta(days=1)).date().isoformat()) for d in decisions for sid in SERIES}
    audited=[(r['series'],r['as_of_date']) for r in audit['results']]
    if len(audited)!=len(set(audited)) or set(audited)!=requested:
        raise SourceError('Acquisition audit does not match requested decisions')
    return backfill(events,Offline(),output,cache)


def main():
    p=argparse.ArgumentParser();p.add_argument('--events',type=Path,required=True)
    p.add_argument('--acquisition-audit',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if 'public_data' in a.output.resolve().parts:p.error('Replay output must be outside public_data')
    r=replay(pd.read_csv(a.events),a.acquisition_audit,a.cache,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='results'},indent=2))
    return int(r['research_coverage_status']=='FAILED_SOURCE_VALIDATION')

if __name__=='__main__':raise SystemExit(main())
