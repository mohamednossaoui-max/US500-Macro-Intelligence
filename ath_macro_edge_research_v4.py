"""Exploratory receipt-backed macro comparison; never a live forecast.

As-of source receipts must pass hashes, semantics and provider vintage checks.
A revised/current value is never substituted for a missing historical feature.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import ath_pullback_edge_v3 as base
from ath_official_vintage_backfill_v1 import load_receipts,observation,SourceError

MACRO_FEATURES={'nfp_change_jobs':('PAYEMS','monthly_change_jobs'),
                'unemployment_pct':('UNRATE','level'),
                'cpi_yoy_sa_pct':('CPIAUCSL','yoy_sa_index_pct'),
                'core_pce_yoy_sa_pct':('PCEPILFE','yoy_sa_index_pct'),
                'industrial_production_mom_pct':('INDPRO','mom_pct')}
COLUMNS=base.PRICE+list(MACRO_FEATURES)
PROTOCOL={'version':'ATH_MACRO_EDGE_V4','ridge_penalty':10.0,'minimum_training_episodes':12,
          'evaluation_start':'2019-01-01','macro_features':MACRO_FEATURES,
          'hypothesis':'Employment, inflation and industrial production as known at the decision date add depth information after an observed 3%-<5% closing drawdown.',
          'models':['MACRO_RIDGE','PRICE_RIDGE','MARKET_CONTEXT_RIDGE','CLIMATOLOGY'],
          'status':'EXPLORATORY_REUSED_CALENDAR_PERIODS_NOT_CONFIRMATORY',
          'minimum_evaluation_episodes':30,'minimum_evaluation_crashes':3,
          'interval_family_comparisons':9,'live_forecast':'DISABLED'}


def attach(frame,receipts):
    out=frame.copy();coverage=[]
    for name in MACRO_FEATURES:out[name]=np.nan
    for idx,event in out.iterrows():
        decision=pd.Timestamp(event.decision_at)
        if decision.tzinfo is None or decision!=decision.normalize():raise ValueError('Invalid decision cutoff')
        asof=(decision-pd.Timedelta(days=1)).date().isoformat()
        for name,(series,field) in MACRO_FEATURES.items():
            saved=receipts.get((series,asof));status='UNAVAILABLE_RECEIPT'
            if saved:
                try:
                    derived=observation(series,asof,saved['record']['response'])
                    value=derived.get(field)
                    if value is None or not np.isfinite(value):status='UNAVAILABLE_DERIVED_FEATURE'
                    else:out.loc[idx,name]=float(value);status='ASOF_VERIFIED'
                except SourceError as error:status=error.status
            coverage.append({'episode_id':event.episode_id,'decision_at':event.decision_at,'feature':name,
                             'as_of_date':asof,'status':status})
    return out,coverage


def evaluate(frame):
    if frame.empty:return []
    usable=frame[frame.complete & frame[COLUMNS+base.MARKET].apply(lambda x:np.isfinite(pd.to_numeric(x,errors='coerce'))).all(axis=1)].sort_values('decision_at')
    results=[]
    for _,event in usable.iterrows():
        train=usable[(usable.decision_at<event.decision_at)&(usable.label_available_at<event.decision_at)]
        if len(train)<PROTOCOL['minimum_training_episodes']:continue
        row={'episode_id':event.episode_id,'decision_at':event.decision_at,'actual_class':event.class_label,
             'training_count':len(train),'latest_training_label_available_at':train.label_available_at.max(),
             'development':event.decision_at<PROTOCOL['evaluation_start'],'label_available_at':event.label_available_at}
        for name,columns in [('macro',COLUMNS),('price',base.PRICE),('market',base.MARKET),('climatology',None)]:
            probability=base.prior(train) if columns is None else base.ridge(train,event,columns)
            row[name+'_probabilities']=probability.tolist();row[name+'_brier']=base.brier(probability,event.class_label)
        results.append(row)
    return results


def interval(values):
    # Same diagnostic algorithm as V3; new comparison family recorded explicitly.
    x=np.asarray(values,dtype=float)
    if len(x)<2:return None
    rng=np.random.default_rng(base.PROTOCOL['bootstrap_seed']);samples=[];n=len(x);block=3
    for _ in range(2000):
        starts=rng.integers(0,n,size=int(np.ceil(n/block)))
        ids=np.concatenate([(np.arange(block)+s)%n for s in starts])[:n];samples.append(x[ids].mean())
    alpha=.05/PROTOCOL['interval_family_comparisons']
    return {'mean':float(x.mean()),'lower':float(np.quantile(samples,alpha/2)),
            'upper':float(np.quantile(samples,1-alpha/2)),'method':'Exploratory block percentile bootstrap, alpha=0.05/9; no guaranteed coverage'}


def run(study,cache):
    study=Path(study);receipts=load_receipts(cache)
    events=pd.read_csv(study/'edge_v3_events.csv')
    audit=json.loads((study/'edge_v3_audit.json').read_text())
    if events.duplicated(['horizon','episode_id']).any():raise ValueError('Duplicate labels')
    frames=[];rows=[];coverage=[];analyses=[]
    for horizon in ('1M','3M','UNTIL_RECOVERY'):
        frame,checks=attach(events[events.horizon.eq(horizon)],receipts)
        p=evaluate(frame);test=[x for x in p if not x['development']]
        comparisons={name:interval([x[name+'_brier']-x['macro_brier'] for x in test]) for name in ('price','market','climatology')}
        crashes=sum(x['actual_class']=='CRASH' for x in test)
        positive=all(v is not None and v['lower']>0 for v in comparisons.values())
        enough=len(test)>=30 and crashes>=3
        analyses.append({'horizon':horizon,'eligible_episodes':len(frame),
                         'complete_macro_feature_rows':int(frame[list(MACRO_FEATURES)].notna().all(axis=1).sum()),
                         'evaluation_predictions':len(test),'evaluation_crashes':crashes,
                         'scores':{name:None if not test else float(np.mean([x[name+'_brier'] for x in test])) for name in ('macro','price','market','climatology')},
                         'improvements':comparisons,'candidate_status':'CANDIDATE_ONLY' if positive and enough else 'NO_CONFIRMED_EDGE'})
        frames.append(frame);coverage+=checks;rows += [{'horizon':horizon,**x} for x in p]
    result={'version':'ATH_MACRO_EDGE_V4','protocol':PROTOCOL,'validated_receipts':len(receipts),
            'study_source_sha256':hashlib.sha256((study/'edge_v3_events.csv').read_bytes()).hexdigest(),
            'price_source_sha256':audit['source_sha256'],'analyses':analyses,
            'live_forecast':None,'high_confidence_claim_allowed':False,'research_only':True,
            'limitations':['This predicts conditional risk after 3% closing drawdown, not at the ATH.',
                'No historical DFF/Fed stance substituted into the candidate; new DFF acquisition still required.',
                'The inspected years are exploratory; future independent validation and calibration are required.',
                'The price series is the cash index, not ES or broker US500.',
                'Small independent episode and crash counts limit conclusions.'],
            'feature_coverage':coverage}
    return result,pd.concat(frames,ignore_index=True),rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--study',type=Path,required=True)
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if 'public_data' in a.output.resolve().parts:p.error('Research outputs must be outside public_data')
    r,events,predictions=run(a.study,a.cache);a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'macro_edge_v4_audit.json').write_text(json.dumps(r,indent=2,allow_nan=False))
    events.to_csv(a.output/'macro_edge_v4_events.csv',index=False)
    (a.output/'macro_edge_v4_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in r.items() if k!='feature_coverage'},indent=2))

if __name__=='__main__':main()
