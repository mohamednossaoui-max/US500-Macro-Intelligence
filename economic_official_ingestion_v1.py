"""Release-aware, append-only Economic ingestion. Audit is read-only by default.

Production writes workspace canonical files only after all 14 indicators pass.
Public data is the baseline, never a fallback declared CURRENT after a failure.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from economic_official_sources_v1 import Client, MAPPINGS, MetadataError, collect, http_error_diagnostic
from point_in_time import validate_temporal_order

EVENTS='economic_historical_events_v1.csv'
QUALITY='economic_historical_quality_v1.csv'
ACCEPT={'CURRENT','NEW_RELEASE','REVISION'}


from economic_observation_order_v1 import latest, period_key


def compare(row,canonical):
    i=row['indicator'];old=latest(canonical,i)
    report=dict(indicator=i,agency=MAPPINGS[i]['agency'],official_latest_reference_period=row.get('reference_period'),official_release_date=row.get('release_date'),official_value=row.get('actual'),
                canonical_latest_reference_period=None if old is None else old.reference_period,canonical_release_date=None if old is None else old.release_date,canonical_value=None if old is None else float(old.actual),
                status='METADATA_UNVERIFIED',revision_detected=False,source_verification=row.get('verification_status'),reason=row.get('reason',''))
    if row.get('verification_status')!='VERIFIED':
        report['status']=row.get('verification_status','METADATA_UNVERIFIED');return report
    try:
        if not math.isfinite(float(row['actual'])) or not row.get('source_url') or not row.get('reference_period') or not row.get('release_date'):
            raise ValueError('Incomplete source evidence')
        release=pd.Timestamp(row['release_date'])
        if release>pd.Timestamp(row['retrieved_at']).tz_localize(None).normalize():
            raise ValueError('Future official release')
    except (ValueError,TypeError,KeyError):
        report['reason']='Incomplete/invalid release evidence';return report
    same=latest(canonical,i,row['reference_period'])
    if same is not None and not math.isclose(float(same.actual),float(row['actual']),rel_tol=0,abs_tol=1e-8):
        report.update(status='REVISION',revision_detected=True,reason='Same reference period has a changed official value')
    elif old is None or release>pd.Timestamp(old.release_date):
        report.update(status='NEW_RELEASE',reason='New official release/vintage requires canonical merge')
    elif same is not None and release==pd.Timestamp(same.release_date) and math.isclose(float(same.actual),float(row['actual']),rel_tol=0,abs_tol=1e-8):
        report.update(status='CURRENT',reason='Official period, release and value match canonical')
    else:
        report.update(status='STALE',reason='Source/canonical release states disagree; refuse rollback')
    return report


def validate_batch(rows,reports):
    if len(reports)!=14 or {r['indicator'] for r in reports}!=set(MAPPINGS):
        raise RuntimeError('All 14 indicators must be audited exactly once')
    bad=[r['indicator']+':'+r['status'] for r in reports if r['status'] not in ACCEPT]
    if bad:raise RuntimeError('Official validation blocked: '+', '.join(bad))
    if not rows:raise RuntimeError('No source observations')
    for r in rows:
        if r.get('verification_status')!='VERIFIED' or r['indicator'] not in MAPPINGS or not math.isfinite(float(r['actual'])):
            raise RuntimeError('Unverified/invalid staging observation')
        if not validate_temporal_order(release_date=r['release_date'],vintage_date=r['vintage_date']):
            raise RuntimeError('Staging PIT temporal validation failed')


def merge(canonical,quality,rows):
    """Preserve old rows; revision becomes known on this release/ingestion date.

    Revised current-series values never claim to be their original release.
    Missing historical periods are not backfilled from a revised current API.
    """
    events=canonical.copy();q=quality.copy()
    changed=[];new_quality=[]
    for raw in rows:
        r=dict(raw);i=r['indicator'];same=latest(events,i,r['reference_period']);old=latest(events,i)
        # Only latest official period may initialize a missing historical period.
        if same is None and r.get('latest_official_period') and period_key(r['reference_period'])!=period_key(r['latest_official_period']):
            continue
        if same is not None:
            samevalue=math.isclose(float(same.actual),float(r['actual']),rel_tol=0,abs_tol=1e-8)
            if samevalue:
                # A repeated estimate with unchanged value but new release still
                # carries a new vintage for the latest official reference period.
                if str(same.release_date)==r['release_date'] or (r.get('latest_official_period') and period_key(r['reference_period'])!=period_key(r['latest_official_period'])):
                    continue
            elif pd.Timestamp(r['release_date'])<pd.Timestamp(same.release_date):
                raise RuntimeError('Refusing revision rollback')
            r['revision']=float(r['actual'])-float(same.actual)
            r['original_release_date']=same.get('original_release_date') if pd.notna(same.get('original_release_date')) else same.release_date
            r['publication_status']='REVISED'
            r['ingestion_event_type']='REVISION'
        else:
            r['ingestion_event_type']='NEW_RELEASE'
        # Conservative availability: API current vintage was observed today,
        # not necessarily on the earlier announced release date.
        r['source_snapshot_history']=bool(r.get('latest_official_period') and period_key(r['reference_period'])!=period_key(r['latest_official_period']))
        r['available_as_of']=pd.Timestamp(r['retrieved_at']).strftime('%Y-%m-%d')
        r['vintage_date']=r['release_date']
        r['observation_date']=r['release_date']
        ident={k:r.get(k) for k in ('indicator','reference_period','release_date','actual','source_series')}
        ident['reference_period']=period_key(ident['reference_period'])
        if same is not None:
            ident['supersedes']=str(same.get('event_id',''))+'|'+str(same.actual)+'|'+str(same.release_date)
        r['event_id']='official-'+hashlib.sha256(json.dumps(ident,sort_keys=True).encode()).hexdigest()[:24]
        if 'event_id' in events and (events.event_id==r['event_id']).any():continue
        changed.append(r)
        events=pd.concat([events,pd.DataFrame([r])],ignore_index=True,sort=False)
        new_quality.append(dict(record_id=r['event_id'],indicator=i,agency=r['agency'],release_date=r['release_date'],reference_period=r['reference_period'],point_in_time_safe=True,quality_issues='',historical_consensus_available=False,available_as_of=r['available_as_of']))
    if new_quality:q=pd.concat([q,pd.DataFrame(new_quality)],ignore_index=True,sort=False)
    events=events.sort_values(['release_date','indicator','reference_period'],kind='mergesort').reset_index(drop=True)
    return events,q,len(changed)


def run(root,staging,mode='audit',collector=collect,now=None):
    root,staging=Path(root),Path(staging);staging.mkdir(parents=True,exist_ok=True)
    now=now or datetime.now(timezone.utc)
    canonical=pd.read_csv(root/'public_data'/EVENTS);quality=pd.read_csv(root/'public_data'/QUALITY)
    client=Client(staging/'evidence');rows=[];reports=[]
    for indicator,mapping in MAPPINGS.items():
        try:
            batch=collector(client,indicator)
            if not batch:raise MetadataError('No official observations')
            for r in batch:r['retrieved_at']=now.isoformat()
            row=batch[-1]
            if row['indicator']!=indicator:raise MetadataError('Indicator mismatch')
            report=compare(row,canonical)
            prior_revisions=[r for r in batch if r.get('verification_status')=='VERIFIED' and (old:=latest(canonical,indicator,r.get('reference_period'))) is not None and not math.isclose(float(old.actual),float(r['actual']),rel_tol=0,abs_tol=1e-8)]
            report['revision_detected']=report['revision_detected'] or bool(prior_revisions)
            if prior_revisions and report['status']=='CURRENT':
                report.update(status='REVISION',reason='Latest release matches; earlier reference periods have revised official values')
            reports.append(report);rows.extend(batch)
        except Exception as exc:
            # HTTP exception strings/response bodies may expose secrets; use only
            # sanitized endpoint, method and status for HTTP diagnostics.
            status='METADATA_UNVERIFIED' if isinstance(exc,MetadataError) else 'SOURCE_ERROR'
            diagnostic=http_error_diagnostic(exc) if isinstance(exc,requests.HTTPError) else str(exc) if isinstance(exc,(MetadataError,RuntimeError)) else type(exc).__name__
            row=dict(indicator=indicator,verification_status=status,reason=diagnostic)
            reports.append(compare(row,canonical))
    pd.DataFrame(rows).to_csv(staging/'observations.csv',index=False)
    pd.DataFrame(reports).to_csv(staging/'comparison.csv',index=False)
    result=dict(provider='official',credentials_configured={'BLS_API_KEY':bool(os.environ.get('BLS_API_KEY')),'CENSUS_API_KEY':bool(os.environ.get('CENSUS_API_KEY'))},mode=mode,retrieved_at=now.isoformat(),passed=all(r['status'] in ACCEPT for r in reports),reports=reports,mapping=MAPPINGS)
    (staging/'audit.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    if mode=='merge':
        validate_batch(rows,reports)
        events,q,added=merge(canonical,quality,rows)
        # Prepare the pair before installing either; public_data stays read-only.
        assert_current(events,reports)
        events.to_csv(staging/EVENTS,index=False);q.to_csv(staging/QUALITY,index=False)
        for name in (EVENTS,QUALITY):
            data=(staging/name).read_bytes();tmp=root/(name+'.tmp');tmp.write_bytes(data);os.replace(tmp,root/name)
        result['added']=added
        assert_current(events,reports)
        status=dict(provider='official',as_of_date=now.date().isoformat(),retrieved_at=now.isoformat(),indicators=[dict(r,status='CURRENT') for r in reports],source_verification='VERIFIED')
        (root/'economic_ingestion_status_v1.json').write_text(json.dumps(status,indent=2)+'\n')
    return result


def assert_current(events,reports):
    bad=[]
    for r in reports:
        row=latest(events,r['indicator'],r['official_latest_reference_period'])
        if row is None or str(row.release_date)!=r['official_release_date'] or not math.isclose(float(row.actual),float(r['official_value']),rel_tol=0,abs_tol=1e-8):bad.append(r['indicator'])
    if bad:raise RuntimeError('Release-aware canonical gate failed: '+','.join(bad))


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--mode',choices=['audit','merge','gate'],default='audit');ap.add_argument('--root',default='.');ap.add_argument('--staging',default='economic_official_staging');args=ap.parse_args()
    if args.mode=='gate':
        stage=Path(args.staging);audit=json.loads((stage/'audit.json').read_text());rows=pd.read_csv(stage/'observations.csv').to_dict('records')
        validate_batch(rows,audit['reports']);assert_current(pd.read_csv(Path(args.root)/EVENTS),audit['reports'])
        print('OFFICIAL RELEASE-AWARE GATE: PASS');return
    result=run(args.root,args.staging,args.mode)
    for r in result['reports']:print(r['indicator'],r['status'],r['reason'])
    if not result['passed']:raise SystemExit(1)
    print('OFFICIAL ECONOMIC VALIDATION: PASS')

if __name__=='__main__':main()
