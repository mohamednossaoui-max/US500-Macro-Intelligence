"""Common-case breadth test on frozen V9 outcomes; research only.

Historical membership is the project's public reconstruction, not certified
as-of membership/price vintages. Timing is a conservative next-day proxy.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import ath_sequential_pullback_research_v9 as v9
import ath_extended_history_research_v10 as v10

BREADTH = ['pct_advancing_mean20', 'net_advances_pct_mean5']
PROTOCOL = {'version':'ATH_BREADTH_V11','base_protocol':'Frozen V9',
            'minimum_coverage_pct':90,'lookback_sessions':20,'features':BREADTH,
            'minimum_training_cases':30,'ridge_penalty':10,
            'comparison':'Conditional baseline, price, price+breadth on identical complete cases.',
            'membership':'Existing historical reconstruction; current constituents never substituted.',
            'timing':'Next-day proxy; no claim of certified historical publication timestamps.',
            'status':'EXPLORATORY_AFTER_INSPECTING_V9_RESULTS','live_forecast':None}


def truth(series):
    return series.astype(str).str.strip().str.lower().isin(['true','1'])


def breadth_features(raw,prices):
    required={'asof_date','coverage_pct','universe_count','price_eligible_count',
              'advances','declines','unchanged','point_in_time_reconstructed','cross_validated'}
    if not required.issubset(raw):raise ValueError('Missing breadth provenance/count fields.')
    raw=raw.copy();raw['date']=pd.to_datetime(raw.asof_date,utc=True,errors='coerce').dt.normalize()
    if raw.date.isna().any() or raw.date.duplicated().any():raise ValueError('Invalid or duplicate breadth dates.')
    for name in ['coverage_pct','universe_count','price_eligible_count','advances','declines','unchanged']:
        raw[name]=pd.to_numeric(raw[name],errors='coerce')
        if not np.isfinite(raw[name]).all() or (raw[name]<0).any():raise ValueError('Invalid breadth counts/coverage.')
    if (raw.universe_count<=0).any() or (raw.price_eligible_count<=0).any():raise ValueError('Invalid denominator.')
    if (raw.price_eligible_count>raw.universe_count).any():raise ValueError('Eligible exceeds historical universe.')
    if not np.allclose(raw.advances+raw.declines+raw.unchanged,raw.price_eligible_count):
        raise ValueError('Advance/decline counts do not match eligible universe.')
    if not np.allclose(raw.coverage_pct,100*raw.price_eligible_count/raw.universe_count,atol=.001,rtol=0):
        raise ValueError('Reported coverage does not match historical denominator.')
    dates=pd.to_datetime(prices.observation_date,utc=True)
    unknown=raw[~raw.date.isin(dates)]
    # Rows outside price scope may be harmless; in-scope non-session rows are not.
    if unknown.date.between(dates.min(),dates.max()).any():raise ValueError('Breadth on unexpected cash session.')
    aligned=raw.set_index('date').reindex(pd.DatetimeIndex(dates))
    good=aligned.coverage_pct.ge(90)&truth(aligned.point_in_time_reconstructed)&truth(aligned.cross_validated)
    advances=(100*aligned.advances/aligned.price_eligible_count).where(good)
    net=(100*(aligned.advances-aligned.declines)/aligned.price_eligible_count).where(good)
    features=pd.DataFrame(index=aligned.index)
    features[BREADTH[0]]=advances.rolling(20,min_periods=20).mean()
    features[BREADTH[1]]=net.rolling(5,min_periods=5).mean()
    features.loc[features[BREADTH[0]].isna(),BREADTH[1]]=np.nan
    audit={'source_rows':len(raw),'source_start':raw.date.min().date().isoformat(),
           'source_end':raw.date.max().date().isoformat(),
           'rows_meeting_quality_gate':int(good.sum()),'full_20_session_windows':int(features.notna().all(axis=1).sum()),
           'membership_vintages_certified':False,'price_vintages_certified':False,
           'availability_verified':False,'verification':'RESEARCH_RECONSTRUCTION_WITH_TIMING_PROXY'}
    return features,audit


def attach(events,features):
    events=events.copy();coverage=[]
    for f in BREADTH:events[f]=np.nan
    for index,event in events.iterrows():
        cutoff=(pd.Timestamp(event.decision_at)-pd.Timedelta(days=1)).normalize()
        row=features.loc[cutoff] if cutoff in features.index else None
        valid=row is not None and row.notna().all()
        if valid:
            for f in BREADTH:events.loc[index,f]=float(row[f])
        coverage.append({'event_id':event.event_id,'stage_pct':int(event.stage_pct),'target_pct':int(event.target_pct),
                         'decision_at':event.decision_at,'breadth_reference_date':cutoff.date().isoformat(),
                         'availability_proxy':(cutoff+pd.Timedelta(days=1)).isoformat(),
                         'status':'RESEARCH_FEATURES_AVAILABLE' if valid else 'UNAVAILABLE_OR_QUALITY_BLOCKED'})
    return events,coverage


def ridge(train,event,cols):
    x=train[cols].to_numpy(float);q=event[cols].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(q).all():raise ValueError('No neutral imputation.')
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1
    x=(x-center)/scale;q=(q-center)/scale
    base=float((train.hit.sum()+1)/(len(train)+2))
    w=np.linalg.solve(x.T@x+10*np.eye(len(cols)),x.T@(train.hit.to_numpy(float)-base))
    return float(np.clip(base+q@w,.001,.999))


def evaluate(events):
    cols=v9.FEATURES+BREADTH
    usable=events[events.eligible & events.complete & events[cols].notna().all(axis=1)].sort_values('decision_at')
    rows=[]
    for _,e in usable.iterrows():
        train=usable[(usable.stage_pct==e.stage_pct)&(usable.target_pct==e.target_pct)
                     &(usable.decision_at<e.decision_at)&(usable.label_available_at<e.decision_at)
                     &(usable.cycle_id!=e.cycle_id)]
        if len(train)<30:continue
        base,price=v9.probability(train,e);breadth=ridge(train,e,cols)
        row={'event_id':e.event_id,'stage_pct':int(e.stage_pct),'target_pct':int(e.target_pct),
             'decision_at':e.decision_at,'hit':int(e.hit),'training_count':len(train),
             'latest_training_label_at':train.label_available_at.max(),
             'development':e.decision_at<v9.PROTOCOL['evaluation_start']}
        for name,p in [('baseline',base),('price',price),('price_breadth',breadth)]:
            row[name+'_probability']=p;row[name+'_brier']=float((p-e.hit)**2)
        rows.append(row)
    return rows


def summarize(events,predictions):
    rows=[]
    for stage in v9.PROTOCOL['stages_pct']:
        for target in v9.PROTOCOL['targets_pct']:
            if target<=stage:continue
            sample=events[(events.stage_pct==stage)&(events.target_pct==target)&events.eligible&events.complete
                          &events[BREADTH].notna().all(axis=1)]
            test=[p for p in predictions if not p['development'] and p['stage_pct']==stage and p['target_pct']==target]
            rows.append({'stage_pct':stage,'target_pct':target,'complete_breadth_cases':len(sample),
                         'evaluations':len(test),'hits':sum(p['hit'] for p in test) if test else None,
                         'brier':{name:float(np.mean([p[name+'_brier'] for p in test])) if test else None
                                  for name in ['baseline','price','price_breadth']},
                         'status':'NO_CONFIRMED_EDGE' if test else 'INSUFFICIENT_COMMON_SAMPLE',
                         'high_confidence_probability':None})
    return rows


def run(cache,breadth,output):
    output=v10.safe_output(output);cache=Path(cache);breadth=Path(breadth)
    # Replay the existing acquisition and calendar gate, preserving V9 as control.
    v10.study(cache,output/'price_control')
    prices=pd.read_csv(cache/'validated_prices.csv');data=v9.history(prices)
    events=v9.outcomes(data,v9.landmarks(data))
    features,quality=breadth_features(pd.read_csv(breadth),prices)
    events,coverage=attach(events,features);predictions=evaluate(events)
    comparisons=summarize(events,predictions)
    audit={'protocol':PROTOCOL,'base_protocol':v9.PROTOCOL,'breadth_sha256':v10.sha(breadth),
           'prices_sha256':v10.sha(cache/'validated_prices.csv'),'code_sha256':v10.sha(__file__),
           'quality':quality,'coverage':coverage,'comparisons':comparisons,
           'status':'NO_CONFIRMED_EDGE' if any(c['evaluations'] for c in comparisons) else 'INSUFFICIENT_COMMON_SAMPLE',
           'live_forecast':None,'research_only':True,
           'limitations':['No certified membership or historical price vintages; reconstruction flags are preserved.',
                         'Breadth history is shorter than cash-price history; identical common cases are mandatory.',
                         'Missing/low coverage windows are excluded, never assigned neutral breadth.',
                         'No independent holdout and no live high-confidence certificate.']}
    events.to_csv(output/'breadth_v11_events.csv',index=False)
    (output/'breadth_v11_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    (output/'breadth_v11_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
    return audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True)
    p.add_argument('--breadth',type=Path,default=Path('public_data/market_breadth_records_v1.csv'))
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    r=run(a.cache,a.breadth,a.output)
    print(json.dumps({k:v for k,v in r.items() if k!='coverage'},indent=2,allow_nan=False))


if __name__=='__main__':main()
