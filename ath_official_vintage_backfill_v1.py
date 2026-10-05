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
 'DFF':('Daily, 7-Day','Not Seasonally Adjusted','Percent','Federal Reserve'),
 'T10Y3M':('Daily','Not Seasonally Adjusted','Percent','Federal Reserve'),
 'NFCI':('Weekly, Ending Friday','Not Seasonally Adjusted','Index','Chicago Fed'),
 'ANFCI':('Weekly, Ending Friday','Not Seasonally Adjusted','Index','Chicago Fed')}
API='https://api.stlouisfed.org/fred/'

class SourceError(Exception):
    def __init__(self,message,status='SOURCE_ERROR'):
        super().__init__(message);self.status=status

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
    max_age={'Daily':10,'Daily, 7-Day':10,'Weekly, Ending Friday':28,'Monthly':120,'Quarterly':200}[SERIES[series][0]]
    reference_end=newest
    if SERIES[series][0]=='Monthly':
        month=newest.to_period('M')
        if newest!=month.start_time:raise SourceError('Monthly reference date is not a month start')
        reference_end=month.end_time.normalize()
        if reference_end>pd.Timestamp(asof):raise SourceError('Unfinished month in completed monthly history')
    if SERIES[series][0]=='Quarterly':
        quarter=newest.to_period('Q')
        if newest!=quarter.start_time:raise SourceError('Quarterly reference date is not a quarter start')
        reference_end=quarter.end_time.normalize()
        if reference_end>pd.Timestamp(asof):raise SourceError('Unfinished quarter in completed GDP history')
    age=(pd.Timestamp(asof)-reference_end).days
    if age>max_age:raise SourceError('Historical vintage is stale','STALE')
    result={'series':series,'agency':SERIES[series][3],'reference_period':newest.date().isoformat(),
            'as_of_date':asof,'level':value,'release_date':None,'release_time':None,
            'reference_period_end':reference_end.date().isoformat(),'age_since_reference_period_end_days':age,
            'verification_status':'PROVIDER_ASOF_VERIFIED_AGENCY_RELEASE_TIME_UNVERIFIED'}
    if series=='PAYEMS' or series in ('CPIAUCSL','PCEPILFE','INDPRO'):
        adjacent=len(rows)>=2 and newest.to_period('M')-rows[1][0].to_period('M')==pd.offsets.MonthEnd(1)
        if series=='PAYEMS':
            if not adjacent:raise SourceError('Consecutive monthly levels unavailable')
            result['monthly_change_jobs']=(value-rows[1][1])*1000
        else:
            if value<=0 or (adjacent and rows[1][1]<=0):raise SourceError('Nonpositive index')
            # A missing month blocks MoM, not independently verifiable level/YoY.
            # Never bridge a gap or carry forward an observation ourselves.
            result['mom_pct']=100*(value/rows[1][1]-1) if adjacent else None
            old=next((v for d,v in rows if d.to_period('M')==newest.to_period('M')-12),None)
            result['yoy_sa_index_pct']=None if old is None or old<=0 else 100*(value/old-1)
            result['derived_field_statuses']={
                'mom_pct':'ASOF_VERIFIED' if adjacent else 'UNAVAILABLE_CONSECUTIVE_MONTH',
                'yoy_sa_index_pct':'ASOF_VERIFIED' if old is not None and old>0 else 'UNAVAILABLE_YEAR_REFERENCE'}
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


def load_receipts(root):
    records={}
    for path in sorted((Path(root)/'receipts').glob('*.json')):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if not path.stem.endswith('-'+sha):raise SourceError('Receipt checksum mismatch')
        item=json.loads(raw);sid=item['series'];asof=item['as_of_date']
        if sid not in SERIES or path.name!=f'{sid}-{asof}-{sha}.json':raise SourceError('Receipt identity mismatch')
        verify_metadata(sid,{'seriess':[item['metadata']]})
        if item.get('source')!=API+'series/observations':raise SourceError('Unexpected receipt source')
        if item['response'].get('realtime_start')!=asof or item['response'].get('realtime_end')!=asof:
            raise SourceError('Receipt vintage mismatch')
        key=(sid,asof)
        if key in records and records[key]['sha']!=sha:raise SourceError('Conflicting historical receipts; review revisions explicitly')
        records[key]={'record':item,'sha':sha}
    return records


def backfill(events,client,output,cache=None):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    cached=load_receipts(cache) if cache else {}
    decisions=pd.to_datetime(events.decision_at,utc=True,errors='raise').drop_duplicates().sort_values()
    if decisions.empty:raise ValueError('No decision dates')
    metadata={};errors={};bounds={};bounds_errors={}
    for series in SERIES:
        try:
            metadata[series]=verify_metadata(series,client.get('series',{'series_id':series}))
            dates=client.get('series/vintagedates',{'series_id':series,'realtime_start':'1776-07-04',
                                                 'realtime_end':'9999-12-31','sort_order':'asc','limit':1})
            first=dates.get('vintage_dates',[])
            if len(first)!=1 or pd.isna(pd.to_datetime(first[0],errors='coerce')):
                raise SourceError('Earliest provider vintage unavailable')
            bounds[series]=first[0]
        except SourceError as exc:
            if series not in metadata:errors[series]=str(exc)
            else:bounds_errors[series]=str(exc)
    results=[]
    for decision in decisions:
        if decision != decision.normalize():raise ValueError('Decision date must be conservative midnight UTC')
        asof=(decision-pd.Timedelta(days=1)).date().isoformat()
        for series in SERIES:
            row={'series':series,'decision_at':decision.isoformat(),'as_of_date':asof,'status':'SOURCE_ERROR'}
            try:
                saved=cached.get((series,asof))
                if saved:
                    payload=saved['record']['response'];meta=saved['record']['metadata']
                    row['acquisition']='REVALIDATED_IMMUTABLE_CACHE'
                else:
                    if series in errors:raise SourceError(errors[series])
                    if series in bounds_errors:raise SourceError(bounds_errors[series])
                    if asof<bounds[series]:
                        raise SourceError('Requested date precedes first provider vintage '+bounds[series], 'UNAVAILABLE_ARCHIVE')
                    payload=client.get('series/observations',{'series_id':series,'realtime_start':asof,'realtime_end':asof,
                        'observation_end':asof,'sort_order':'desc','limit':90,'units':'lin','output_type':1})
                    meta=metadata[series];row['acquisition']='OFFICIAL_API'
                # Save even a stale response for diagnosis, without accepting it as a predictor.
                row['receipt_sha256']=immutable_receipt(output,series,asof,meta,payload)
                row.update(observation(series,asof,payload),status='ASOF_VERIFIED')
            except SourceError as exc:row.update(reason=str(exc),status=exc.status)
            results.append(row)
    report={'research_only':True,'live_forecast':None,'rows':len(results),
            'verified':sum(r['status']=='ASOF_VERIFIED' for r in results),
            'source_errors':sum(r['status']=='SOURCE_ERROR' for r in results),
            'unavailable_archive':sum(r['status']=='UNAVAILABLE_ARCHIVE' for r in results),
            'stale':sum(r['status']=='STALE' for r in results),
            'unavailable_derived_fields':sum(v!='ASOF_VERIFIED' for r in results for v in r.get('derived_field_statuses',{}).values()),
            'first_provider_vintages':bounds,'archive_metadata_errors':bounds_errors,
            'limitations':['Provider as-of vintage is not an agency release timestamp.',
                'No synthetic historical Fed stance, Decision scores or neutral missing-value fallback.',
                'Partial research coverage does not permit live forecasting or CURRENT claims.'],
            'results':results}
    report['research_coverage_status']=research_coverage(report)
    (output/'official_vintage_audit.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    return report


def research_coverage(report):
    """Accept every obtainable vintage; explicit archive gaps never become CURRENT.

    Complete coverage remains the default CLI policy. This research-only policy
    allows proven dates before an archive began, not stale/source-failed rows.
    """
    rows=report.get('results',[])
    if len(rows)!=report.get('rows') or not rows:return 'FAILED_SOURCE_VALIDATION'
    if not any(x.get('status')=='ASOF_VERIFIED' for x in rows):return 'FAILED_SOURCE_VALIDATION'
    if len({(x.get('series'),x.get('decision_at')) for x in rows})!=len(rows):return 'FAILED_SOURCE_VALIDATION'
    partial=False
    for row in rows:
        if row.get('status')=='ASOF_VERIFIED':continue
        first=report.get('first_provider_vintages',{}).get(row.get('series'))
        if row.get('status')!='UNAVAILABLE_ARCHIVE' or not first or row.get('as_of_date','9999')>=first:
            return 'FAILED_SOURCE_VALIDATION'
        partial=True
    return 'VERIFIED_AVAILABLE_ARCHIVE_PARTIAL_TOTAL' if partial else 'VERIFIED_COMPLETE_REQUESTED_COVERAGE'


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--events',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--coverage-policy',choices=('complete','available-archive'),default='complete')
    args=parser.parse_args()
    if 'public_data' in args.output.resolve().parts:parser.error('Output must be outside public_data')
    try:client=Client(os.environ.get('FRED_API_KEY'))
    except SourceError as exc:parser.exit(2,str(exc)+'\n')
    report=backfill(pd.read_csv(args.events),client,args.output,args.cache)
    print(json.dumps({k:v for k,v in report.items() if k!='results'},indent=2))
    if args.coverage_policy=='available-archive':
        return 1 if report['research_coverage_status']=='FAILED_SOURCE_VALIDATION' else 0
    return 1 if report['verified']!=report['rows'] else 0

if __name__=='__main__':raise SystemExit(main())
