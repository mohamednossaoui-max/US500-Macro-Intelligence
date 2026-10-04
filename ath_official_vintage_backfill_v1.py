"""Read-only ALFRED as-of feature acquisition. Never backfill current vintages.

Provider as-of date is not an agency release timestamp. Missing history fails
closed. No trading, live probabilities, canonical writes or API-key logging.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
from pathlib import Path
import numpy as np
import pandas as pd
import requests

# Verified original agency series metadata; index base-year changes are allowed.
SERIES={
 'PAYEMS':('Monthly','Seasonally Adjusted','Thousands of Persons','BLS'),
 'UNRATE':('Monthly','Seasonally Adjusted','Percent','BLS'),
 'CPIAUCSL':('Monthly','Seasonally Adjusted','Index','BLS'),
 'PCEPILFE':('Monthly','Seasonally Adjusted','Index','BEA'),
 'A191RL1Q225SBEA':('Quarterly','Seasonally Adjusted Annual Rate','Percent Change from Preceding Period','BEA'),
 'INDPRO':('Monthly','Seasonally Adjusted','Index','Federal Reserve'),
 'DFF':('Daily','Not Seasonally Adjusted','Percent','Federal Reserve'),
 'T10Y3M':('Daily','Not Seasonally Adjusted','Percent','Federal Reserve'),
 'NFCI':('Weekly, Ending Friday','Not Seasonally Adjusted','Index','Chicago Fed'),
 'ANFCI':('Weekly, Ending Friday','Not Seasonally Adjusted','Index','Chicago Fed')}
API='https://api.stlouisfed.org/fred/'

class SourceError(Exception):pass

class Client:
    def __init__(self,key,session=None,pace=.6):
        if not key:raise SourceError('FRED_API_KEY is required; do not paste it into reports.')
        self.key=key;self.session=session or requests.Session();self.pace=pace
    def get(self,endpoint,params):
        # Exception text/URLs can contain a key: never propagate them.
        try:
            for attempt in range(3):
                if self.pace:time.sleep(self.pace)
                response=self.session.get(API+endpoint,params={**params,'api_key':self.key,'file_type':'json'},timeout=30)
                if response.status_code==429 and attempt<2:
                    time.sleep(2);continue
                if response.status_code!=200:raise SourceError('Official provider HTTP '+str(response.status_code))
                payload=response.json()
                if 'error_code' in payload:raise SourceError('Official provider rejected request')
                return payload
        except SourceError:raise
        except Exception:raise SourceError('Official provider request/JSON failed') from None


def verify_metadata(series,payload):
    rows=payload.get('seriess',[])
    if len(rows)!=1 or rows[0].get('id')!=series:raise SourceError('Series identity unavailable')
    row=rows[0];freq,sa,units,_=SERIES[series]
    if row.get('frequency')!=freq or row.get('seasonal_adjustment')!=sa or not row.get('units','').startswith(units):
        raise SourceError('Official series semantics changed or unverified')
    return {k:row.get(k) for k in ('id','title','frequency','seasonal_adjustment','units')}


def observation(series,asof,payload):
    # Provider must attest the requested vintage, not silently return today.
    if payload.get('realtime_start')!=asof or payload.get('realtime_end')!=asof:
        raise SourceError('Provider as-of metadata does not match requested vintage')
    rows=[]
    for item in payload.get('observations',[]):
        date=pd.Timestamp(item['date']);value=pd.to_numeric(item.get('value'),errors='coerce')
        if date>pd.Timestamp(asof):raise SourceError('Future reference period in historical vintage')
        if np.isfinite(value):rows.append((date,float(value)))
    rows=sorted(rows,reverse=True)
    if not rows:raise SourceError('Historical vintage has no finite observations')
    if len({r[0] for r in rows})!=len(rows):raise SourceError('Duplicate reference periods')
    newest,value=rows[0]
    max_age={'Daily':10,'Weekly, Ending Friday':28,'Monthly':120,'Quarterly':200}[SERIES[series][0]]
    if (pd.Timestamp(asof)-newest).days>max_age:raise SourceError('Historical vintage is stale')
    result={'series':series,'agency':SERIES[series][3],'reference_period':newest.date().isoformat(),
            'as_of_date':asof,'level':value,'release_date':None,'release_time':None,
            'verification_status':'PROVIDER_ASOF_VERIFIED_AGENCY_RELEASE_TIME_UNVERIFIED'}
    if series=='PAYEMS' or series in ('CPIAUCSL','PCEPILFE','INDPRO'):
        if len(rows)<2 or newest.to_period('M')-rows[1][0].to_period('M')!=pd.offsets.MonthEnd(1):
            raise SourceError('Consecutive monthly levels unavailable')
        previous=rows[1][1]
        if series=='PAYEMS':result['monthly_change_jobs']=(value-previous)*1000
        else:
            if previous<=0 or value<=0:raise SourceError('Nonpositive index')
            result['mom_pct']=100*(value/previous-1)
        # Only derive YoY from exactly 12 months earlier, same as-of vintage.
        old=next((v for d,v in rows if d.to_period('M')==newest.to_period('M')-12),None)
        if series!='PAYEMS':result['yoy_sa_index_pct']=None if old is None or old<=0 else 100*(value/old-1)
    return result


def immutable_receipt(root,series,asof,metadata,payload):
    record={'series':series,'as_of_date':asof,'source':API+'series/observations',
            'metadata':metadata,'response':payload}
    raw=json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest=hashlib.sha256(raw).hexdigest();path=Path(root)/'receipts'/f'{series}-{asof}-{digest}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_bytes()!=raw:raise SourceError('Immutable receipt conflict')
    if not path.exists():path.write_bytes(raw)
    return digest


def backfill(events,client,output):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    decisions=pd.to_datetime(events.decision_at,utc=True,errors='raise').drop_duplicates().sort_values()
    if decisions.empty:raise ValueError('No decision dates')
    metadata={};errors={}
    for series in SERIES:
        try:metadata[series]=verify_metadata(series,client.get('series',{'series_id':series}))
        except SourceError as exc:errors[series]=str(exc)
    results=[]
    for decision in decisions:
        if decision != decision.normalize():raise ValueError('Decision date must be conservative midnight UTC')
        asof=(decision-pd.Timedelta(days=1)).date().isoformat()
        for series in SERIES:
            row={'series':series,'decision_at':decision.isoformat(),'as_of_date':asof,'status':'SOURCE_ERROR'}
            try:
                if series in errors:raise SourceError(errors[series])
                payload=client.get('series/observations',{'series_id':series,'realtime_start':asof,'realtime_end':asof,
                    'observation_end':asof,'sort_order':'desc','limit':90,'units':'lin','output_type':1})
                derived=observation(series,asof,payload)
                row.update(derived,status='ASOF_VERIFIED',receipt_sha256=immutable_receipt(output,series,asof,metadata[series],payload))
            except SourceError as exc:row['reason']=str(exc)
            results.append(row)
    report={'research_only':True,'live_forecast':None,'rows':len(results),
            'verified':sum(r['status']=='ASOF_VERIFIED' for r in results),
            'source_errors':sum(r['status']=='SOURCE_ERROR' for r in results),
            'limitations':['Provider as-of vintage is not an agency release timestamp.',
                'No synthetic historical Fed stance, Decision scores or neutral missing-value fallback.',
                'Authenticated live acquisition must run with FRED_API_KEY; fixtures do not prove endpoint availability.'],
            'results':results}
    (output/'official_vintage_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);args=parser.parse_args()
    if 'public_data' in args.output.resolve().parts:parser.error('Output must be outside public_data')
    try:client=Client(os.environ.get('FRED_API_KEY'))
    except SourceError as exc:parser.exit(2,str(exc)+'\n')
    report=backfill(pd.read_csv(args.events),client,args.output)
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    return 1 if report['source_errors'] else 0

if __name__=='__main__':raise SystemExit(main())
