"""One predeclared credit hypothesis; as-of receipts, no live forecasting."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import numpy as np
import pandas as pd
import ath_record_high_research_v6 as base
from ath_official_vintage_backfill_v1 import Client,SourceError,API,immutable_receipt

SID='BAA10Y'
CREDIT=['baa_spread_pct','baa_change_30_calendar_days_pp']
PROTOCOL={'version':'ATH_CREDIT_V8','series':SID,
 'source_url':'https://fred.stlouisfed.org/series/BAA10Y',
 'semantics':'Baa corporate yield minus 10-year Treasury yield, percent units; not EBP or duration-matched OAS.',
 'features':CREDIT,'comparison':'PRICE, MARKET, CREDIT_ONLY, PRICE_PLUS_CREDIT, MARKET_PLUS_CREDIT, CLIMATOLOGY on identical complete cases',
 'cohort_and_labels':'Frozen V6 record-high cohort, labels, maturity, 3-calendar-month sampling',
 'lookback_calendar_days':30,'maximum_reference_age_days':10,'maximum_baseline_age_days':10,
 'minimum_training_events':12,'ridge_penalty':10.,'evaluation_start':'2019-01-01',
 'primary_comparison':'MARKET_PLUS_CREDIT versus MARKET and CLIMATOLOGY; other comparisons exploratory',
 'primary_horizon':'3M','secondary_horizons':['1M','UNTIL_RECOVERY'],
 'status':'EXPLORATORY; prior years inspected. No pristine holdout or confirmed edge claim.',
 'live_forecast':None,'research_only':True}


def write_json(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,indent=2,sort_keys=True,allow_nan=False))


def metadata(payload):
    rows=payload.get('seriess',[])
    if len(rows)!=1:raise SourceError('Credit metadata unavailable')
    r=rows[0]
    if (r.get('id'),r.get('frequency'),r.get('units'),r.get('seasonal_adjustment'))!=(SID,'Daily','Percent','Not Seasonally Adjusted'):
        raise SourceError('Credit series identity/semantics mismatch')
    return {k:r.get(k) for k in ['id','title','frequency','units','seasonal_adjustment']}


def features(asof,payload):
    if payload.get('realtime_start')!=asof or payload.get('realtime_end')!=asof:
        raise SourceError('Credit as-of metadata mismatch')
    rows=[];seen=set();cutoff=pd.Timestamp(asof)
    for r in payload.get('observations',[]):
        d=pd.Timestamp(r['date']);v=pd.to_numeric(r.get('value'),errors='coerce')
        if d>cutoff:raise SourceError('Future credit reference date')
        if d in seen:raise SourceError('Duplicate credit reference date')
        seen.add(d)
        if np.isfinite(v):rows.append((d,float(v)))
    rows.sort(reverse=True)
    if not rows:raise SourceError('No finite credit history')
    latest,value=rows[0]
    if (cutoff-latest).days>10:raise SourceError('Credit latest reference stale','STALE')
    # Calendar anchor relative to the latest observed level; never use a later
    # observation in place of a missing baseline or interpret percent as bps.
    target=latest-pd.Timedelta(days=30)
    prior=next(((d,v) for d,v in rows if d<=target),None)
    if prior is None or (target-prior[0]).days>10:
        raise SourceError('Credit 30-day baseline unavailable','UNAVAILABLE_DERIVED_FEATURE')
    return {'baa_spread_pct':value,'baa_change_30_calendar_days_pp':value-prior[1],
            'reference_date':latest.date().isoformat(),'baseline_date':prior[0].date().isoformat(),
            'release_date':None,'verification_status':'PROVIDER_ASOF_VERIFIED_AGENCY_RELEASE_TIME_UNVERIFIED'}


def load_credit(root):
    records={}
    for path in sorted((Path(root)/'receipts').glob('*.json')):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();r=json.loads(raw)
        if r.get('series')!=SID or path.name!=f"{SID}-{r['as_of_date']}-{sha}.json":raise SourceError('Credit receipt checksum/identity mismatch')
        metadata({'seriess':[r['metadata']]})
        if r.get('source')!=API+'series/observations':raise SourceError('Unexpected credit receipt source')
        key=r['as_of_date']
        if key in records and records[key]['sha']!=sha:raise SourceError('Conflicting credit vintages; review explicitly')
        if r['response'].get('realtime_start')!=key or r['response'].get('realtime_end')!=key:raise SourceError('Receipt as-of mismatch')
        records[key]={'record':r,'sha':sha}
    return records


def discontinued(asof, payload):
    """Require provider metadata for this exact historical as-of, never today's title."""
    metadata(payload)
    row = payload['seriess'][0]
    if (payload.get('realtime_start') != asof or payload.get('realtime_end') != asof
            or row.get('realtime_start') != asof or row.get('realtime_end') != asof
            or 'DISCONTINUED' not in str(row.get('title', '')).upper()):
        raise SourceError('Historical discontinuation metadata not verified')
    return True


def lifecycle_receipt(output, asof, payload):
    discontinued(asof, payload)
    record = {'source':API+'series', 'series':SID, 'as_of_date':asof, 'response':payload}
    raw = json.dumps(record,sort_keys=True,separators=(',', ':'),allow_nan=False).encode()
    sha = hashlib.sha256(raw).hexdigest()
    path = Path(output)/'lifecycle_receipts'/f'{SID}-{asof}-{sha}.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and path.read_bytes()!=raw:
        raise SourceError('Lifecycle receipt changed')
    if not path.exists():path.write_bytes(raw)
    return sha


def load_lifecycle(root):
    result = {}
    for path in sorted((Path(root)/'lifecycle_receipts').glob('*.json')):
        raw=path.read_bytes();sha=hashlib.sha256(raw).hexdigest();r=json.loads(raw)
        key=r['as_of_date']
        if (r.get('source')!=API+'series' or r.get('series')!=SID
                or path.name!=f'{SID}-{key}-{sha}.json'):
            raise SourceError('Lifecycle receipt checksum/identity mismatch')
        discontinued(key,r['response'])
        if key in result and result[key]['sha']!=sha:
            raise SourceError('Conflicting lifecycle receipts')
        result[key]={'response':r['response'],'sha':sha}
    return result


def acquire(events,client,output,cache=None):
    cached=load_credit(cache) if cache else {};error=None;meta=None;first=None
    try:
        meta=metadata(client.get('series',{'series_id':SID}))
        dates=client.get('series/vintagedates',{'series_id':SID,'realtime_start':'1776-07-04','realtime_end':'9999-12-31','sort_order':'asc','limit':1}).get('vintage_dates',[])
        if len(dates)!=1 or pd.isna(pd.to_datetime(dates[0],errors='coerce')):raise SourceError('Earliest credit provider vintage unavailable')
        first=dates[0]
    except SourceError as exc:error=str(exc)
    lifecycle=load_lifecycle(cache) if cache else {}
    results=[]
    for decision in sorted(events.decision_at.drop_duplicates()):
        d=pd.Timestamp(decision)
        if d.tzinfo is None or d!=d.normalize() or d.utcoffset()!=pd.Timedelta(0):raise ValueError('Decision must be UTC midnight')
        asof=(d-pd.Timedelta(days=1)).date().isoformat()
        row={'series':SID,'decision_at':d.isoformat(),'as_of_date':asof}
        try:
            saved=cached.get(asof)
            if saved:payload=saved['record']['response'];used_meta=saved['record']['metadata'];row['acquisition']='REVALIDATED_IMMUTABLE_CACHE'
            else:
                if error:raise SourceError(error)
                if asof<first:raise SourceError('Date precedes verified provider archive','UNAVAILABLE_ARCHIVE')
                payload=client.get('series/observations',{'series_id':SID,'realtime_start':asof,'realtime_end':asof,
                    'observation_start':(d-pd.Timedelta(days=91)).date().isoformat(),'observation_end':asof,
                    'sort_order':'desc','limit':100,'units':'lin','output_type':1})
                used_meta=meta;row['acquisition']='OFFICIAL_PROVIDER_API'
            row['receipt_sha256']=immutable_receipt(output,SID,asof,used_meta,payload)
            row.update(features(asof,payload),status='ASOF_VERIFIED')
        except SourceError as exc:
            row.update(status=exc.status,reason=str(exc))
            # Only a stale or empty successful observations response can trigger
            # lifecycle verification. HTTP/identity/as-of errors remain errors.
            if (exc.status=='STALE' or str(exc)=='No finite credit history'):
                try:
                    proof = lifecycle[asof]['response'] if asof in lifecycle else client.get(
                        'series', {'series_id':SID,'realtime_start':asof,'realtime_end':asof})
                    sha=lifecycle_receipt(output,asof,proof)
                    row.update(status='UNAVAILABLE_PROVIDER_DISCONTINUED',
                               reason='Provider marks this exact historical vintage discontinued; excluded from model sample',
                               lifecycle_receipt_sha256=sha, lifecycle_source=API+'series')
                except SourceError as proof_error:
                    row['lifecycle_verification_error']=str(proof_error)
        results.append(row)
    passed=bool(results) and any(r['status']=='ASOF_VERIFIED' for r in results) and all(
        r['status'] in ('ASOF_VERIFIED','UNAVAILABLE_PROVIDER_DISCONTINUED') or (r['status']=='UNAVAILABLE_ARCHIVE' and first and r['as_of_date']<first) for r in results)
    report={'rows':len(results),'verified':sum(r['status']=='ASOF_VERIFIED' for r in results),
            'first_provider_vintage':first,'metadata_error':error,'results':results,
            'status':'VERIFIED_AVAILABLE_ARCHIVE' if passed else 'FAILED_SOURCE_VALIDATION',
            'research_only':True,'live_forecast':None}
    write_json(Path(output)/'credit_acquisition_audit.json',report)
    return report


def attach(events,records):
    out=events.copy();coverage=[]
    for col in CREDIT:out[col]=np.nan
    for idx,r in out.iterrows():
        asof=(pd.Timestamp(r.decision_at)-pd.Timedelta(days=1)).date().isoformat()
        status='UNAVAILABLE_RECEIPT';saved=records.get(asof)
        if saved:
            try:
                derived=features(asof,saved['record']['response'])
                for col in CREDIT:out.loc[idx,col]=derived[col]
                status='ASOF_VERIFIED'
            except SourceError as e:status=e.status
        coverage.append({'episode_id':r.episode_id,'decision_at':r.decision_at,'as_of_date':asof,'status':status})
    return out,coverage


def evaluate(frame):
    cols=base.MARKET+CREDIT
    usable=frame[frame.complete & frame[cols].apply(lambda c:np.isfinite(pd.to_numeric(c,errors='coerce'))).all(axis=1)].sort_values('decision_at')
    results=[]
    for _,event in usable.iterrows():
        train=usable[(usable.decision_at<event.decision_at)&(usable.label_available_at<event.decision_at)]
        if len(train)<12:continue
        r={'episode_id':event.episode_id,'decision_at':event.decision_at,'actual_class':event.class_label,
           'training_count':len(train),'latest_training_label_available_at':train.label_available_at.max(),
           'development':event.decision_at<'2019-01-01'}
        for name,columns in [('price',base.PRICE),('market',base.MARKET),('credit_only',CREDIT),
                             ('price_plus_credit',base.PRICE+CREDIT),('market_plus_credit',base.MARKET+CREDIT),('climatology',None)]:
            p=base.prior(train) if columns is None else base.ridge(train,event,columns)
            r[name+'_brier']=base.score(p,event.class_label);r[name+'_probabilities']=p.tolist()
        results.append(r)
    return results


def summarize(predictions):
    rows=[r for r in predictions if not r['development']]
    names=['price','market','credit_only','price_plus_credit','market_plus_credit','climatology']
    return {'evaluations':len(rows),'class_counts':{c:sum(r['actual_class']==c for r in rows) for c in base.CLASSES},
            'brier':{n:float(np.mean([r[n+'_brier'] for r in rows])) if rows else None for n in names},
            'status':'NO_CONFIRMED_EDGE' if rows else 'BLOCKED_INSUFFICIENT_VERIFIED_CREDIT',
            'live_probabilities':None}


def study(events,cache,output):
    records=load_credit(cache) if cache else {};frame,coverage=attach(events,records)
    lifecycle=load_lifecycle(cache) if cache else {}
    for row in coverage:
        if row['status'] in ('STALE','SOURCE_ERROR') and row['as_of_date'] in lifecycle:
            row['status']='UNAVAILABLE_PROVIDER_DISCONTINUED'
            row['lifecycle_receipt_sha256']=lifecycle[row['as_of_date']]['sha']
    predictions=[];analyses=[]
    for horizon in ['1M','3M','UNTIL_RECOVERY']:
        subset=frame[frame.horizon.eq(horizon)];rows=evaluate(subset)
        analyses.append({'horizon':horizon,'credit_complete_rows':int(subset[CREDIT].notna().all(axis=1).sum()),**summarize(rows)})
        predictions.extend([{'horizon':horizon,**r} for r in rows])
    report={'protocol':PROTOCOL,'base_protocol':base.PROTOCOL,
            'study_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'input_events_sha256':hashlib.sha256(events.to_csv(index=False).encode()).hexdigest(),
            'validated_receipts':len(records),'analyses':analyses,'coverage':coverage,
            'research_only':True,'live_forecast':None,'status':'NO_CONFIRMED_EDGE' if predictions else 'BLOCKED_INSUFFICIENT_VERIFIED_CREDIT'}
    acquisition_path=Path(cache)/'credit_acquisition_audit.json' if cache else None
    if acquisition_path and acquisition_path.exists():
        report['source_validation_status']=json.loads(acquisition_path.read_text()).get('status')
        if report['source_validation_status']=='FAILED_SOURCE_VALIDATION':
            report['status']='PARTIAL_RESEARCH_NO_CONFIRMED_EDGE'
    write_json(Path(output)/'credit_edge_v8_audit.json',report)
    write_json(Path(output)/'credit_edge_v8_predictions.json',predictions)
    Path(output).mkdir(parents=True,exist_ok=True);frame.to_csv(Path(output)/'credit_edge_v8_events.csv',index=False)
    return report


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['protocol','acquire','study'],required=True)
    p.add_argument('--events',type=Path);p.add_argument('--cache',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if 'public_data' in a.output.resolve().parts:p.error('Research output must be outside public_data')
    if a.mode=='protocol':write_json(a.output/'credit_v8_protocol.json',PROTOCOL);return 0
    if not a.events:p.error('--events required')
    events=pd.read_csv(a.events)
    if a.mode=='acquire':
        try:r=acquire(events,Client(os.environ.get('FRED_API_KEY')),a.output,a.cache)
        except SourceError as e:p.exit(2,str(e)+'\n')
        print(json.dumps({k:v for k,v in r.items() if k!='results'},indent=2))
        return int(r['status']=='FAILED_SOURCE_VALIDATION')
    r=study(events,a.cache,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='coverage'},indent=2))
    return 0 if r['status']!='BLOCKED_INSUFFICIENT_VERIFIED_CREDIT' else 1

if __name__=='__main__':raise SystemExit(main())
