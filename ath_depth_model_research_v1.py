"""Predeclared walk-forward depth experiment; not a live forecast service.

Only earlier, fully matured outcomes enter training. Scaling is fitted inside
each training fold. Price and partial-context models share the same rows.
Existing research dates are proxies, not certified vintage histories.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ath_pullback_context_v1 import bars, study, CLASSES
from ath_context_archive_v1 import load, utc

PRICE = ['return20_pct', 'vol20_pct', 'above_sma200_pct']
PARTIAL = PRICE + ['stress', 'sentiment', 'net_liquidity']
FULL = PARTIAL + ['inflation', 'labor', 'growth', 'fed']
K = 5  # fixed before seeing scores; no model/hyperparameter search
MIN_TRAIN = 5


def truth(value):
    return str(value).strip().lower() in {'true','1','1.0'}


def probabilities(train, target, features):
    """Nearest-neighbour class frequencies with one prior count per class."""
    x = train[features].to_numpy(dtype=float)
    q = np.asarray([target[f] for f in features],dtype=float)
    if not np.isfinite(x).all() or not np.isfinite(q).all() or len(train) == 0:
        raise ValueError('No implicit imputation of missing/nonfinite features.')
    center, scale = np.median(x,axis=0), np.std(x,axis=0)
    scale[scale < 1e-12] = 1
    distance = np.mean(((x-center)/scale-(q-center)/scale)**2,axis=1)
    selected = np.argsort(distance,kind='stable')[:min(K,len(train))]
    y = train.iloc[selected].class_lower
    counts = np.asarray([y.eq(c).sum() for c in CLASSES],dtype=float)+1
    return counts/counts.sum()


def unconditional(train):
    counts = np.asarray([train.class_lower.eq(c).sum() for c in CLASSES],dtype=float)+1
    return counts/counts.sum()


def score(probability, observed):
    y = np.asarray([float(c == observed) for c in CLASSES])
    return float(np.sum((np.asarray(probability)-y)**2))


def walk_forward(frame, features=PARTIAL, min_train=MIN_TRAIN):
    data = frame.sort_values('peak_date').copy()
    if data.peak_date.duplicated().any():
        raise ValueError('Duplicate anchor events.')
    rows=[]
    usable = data.complete & ~data.intraday_ambiguous
    usable &= data[features].apply(pd.to_numeric,errors='coerce').apply(lambda s: np.isfinite(s)).all(axis=1)
    data=data[usable].copy()
    for _, event in data.iterrows():
        train = data[(data.peak_date < event.peak_date) & (data.label_end < event.peak_date)]
        if len(train) < min_train:
            continue
        p0, p1, pc = probabilities(train,event,PRICE), probabilities(train,event,features), unconditional(train)
        rows.append({'peak_date':event.peak_date,'label_end':event.label_end,
                     'observed_class':event.class_lower, 'training_rows':len(train),
                     'training_latest_label_end':train.label_end.max(),
                     'price_brier':score(p0,event.class_lower),
                     'context_brier':score(p1,event.class_lower),
                     'climatology_brier':score(pc,event.class_lower),
                     'price_probabilities':p0.tolist(), 'context_probabilities':p1.tolist(),
                     'climatology_probabilities':pc.tolist()})
    return rows


def attach(frame, source, date, column, name, max_age, checks=()):
    if not {date,column,'point_in_time_safe',*checks}.issubset(source):
        frame[name] = np.nan
        return frame
    source=source.copy()
    source['_available']=pd.to_datetime(source[date],utc=True,errors='coerce')
    if source._available.isna().any() or source._available.duplicated().any():
        raise ValueError('Invalid/duplicate context dates for '+name)
    keep=source.point_in_time_safe.map(truth)
    for check in checks:
        keep &= source[check].map(truth)
    source.loc[~keep,column]=np.nan
    left=frame.copy();left['_anchor']=pd.to_datetime(left.peak_date,utc=True)
    merged=pd.merge_asof(left.sort_values('_anchor'),source[['_available',column]].sort_values('_available'),
                         left_on='_anchor',right_on='_available',direction='backward',allow_exact_matches=False)
    merged[name]=pd.to_numeric(merged[column],errors='coerce')
    merged.loc[merged._anchor-merged._available > pd.Timedelta(days=max_age),name]=np.nan
    return merged.drop(columns=['_anchor','_available',column])


def event_table(public_data, archive, horizon):
    root=Path(public_data)
    price=pd.read_csv(root/'technical_intelligence_research_v1.csv')
    data=bars(price)
    labels=study(price)
    frame=labels[labels.horizon.eq(horizon) & labels.descriptive_sample].copy()
    for f in PRICE:
        frame[f]=np.nan
    for i,row in frame.iterrows():
        # A peak is recognised at end of session. Use closes strictly before
        # its session; no future close, return, or rolling normalization.
        past=data[data.date < utc(row.peak_date)].close
        if len(past)>=200:
            frame.loc[i,'return20_pct']=100*(past.iloc[-1]/past.iloc[-21]-1)
            frame.loc[i,'vol20_pct']=100*past.pct_change().tail(20).std()
            frame.loc[i,'above_sma200_pct']=100*(past.iloc[-1]/past.tail(200).mean()-1)
    for file,date,column,name,age,checks in (
            ('financial_stress_research_v1.csv','asof_date','composite_stress_score','stress',7,('VIX_FRESH','NFCI_FRESH','ANFCI_FRESH')),
            ('sentiment_engine_research_v1.csv','asof_date','unified_sentiment_score','sentiment',7,()),
            ('liquidity_intelligence_research_v1.csv','asof_date','NET_LIQUIDITY_PROXY_MILLIONS','net_liquidity',14,
             ('FED_TOTAL_ASSETS_fresh','ON_RRP_fresh','TREASURY_GENERAL_ACCOUNT_fresh'))):
        path=root/file
        if not path.exists(): frame[name]=np.nan
        else: frame=attach(frame,pd.read_csv(path),date,column,name,age,checks)
    records=load(archive)
    for field in ['inflation','labor','growth','fed']:
        frame[field]=np.nan
    mapping={'economic_inflation':'inflation','economic_labor':'labor','economic_growth':'growth','fed_stance':'fed'}
    for i,row in frame.iterrows():
        # Snapshots created today cannot populate earlier dates, even if their
        # internal context_date claims an earlier date.
        eligible=[r for r in records if utc(r['available_at']) < utc(row.peak_date)
                  and utc(row.peak_date)-utc(r['available_at']) <= pd.Timedelta(days=7)]
        if not eligible: continue
        for feature in eligible[-1]['payload']['unified_state_vector_v1.csv']:
            if feature['feature'] not in mapping: continue
            if not truth(feature.get('eligible')) or feature.get('freshness') != 'CURRENT': continue
            if feature.get('pit_status') != 'PIT_SAFE': continue
            frame.loc[i,mapping[feature['feature']]]=pd.to_numeric(feature.get('value'),errors='coerce')
    return frame


def summarize(rows):
    if not rows:
        return {'evaluations':0,'price_brier':None,'context_brier':None,'climatology_brier':None,
                'incremental_brier_improvement':None,'test_class_counts':{c:0 for c in CLASSES}}
    return {'evaluations':len(rows),
            **{key:float(np.mean([r[key] for r in rows])) for key in ['price_brier','context_brier','climatology_brier']},
            'incremental_brier_improvement':float(np.mean([r['price_brier']-r['context_brier'] for r in rows])),
            'test_class_counts':{c:sum(r['observed_class']==c for r in rows) for c in CLASSES}}


def experiment(public_data, archive):
    analyses=[]; frames=[]; predictions=[]
    for horizon in ['1M','3M']:
        events=event_table(public_data,archive,horizon)
        frames.append(events)
        partial=walk_forward(events,PARTIAL)
        full=walk_forward(events,FULL)
        price_only=walk_forward(events,PRICE)
        predictions.extend([{'horizon':horizon,'model_scope':scope,**r}
                            for scope,rows in [('PRICE_ONLY',price_only),('PARTIAL_CONTEXT',partial),('FULL_CONTEXT',full)] for r in rows])
        analyses.append({'horizon':horizon,'sample_count':len(events),
                         'complete_unambiguous':int((events.complete & ~events.intraday_ambiguous).sum()),
                         'partial_feature_complete':int(events[PARTIAL].notna().all(axis=1).sum()),
                         'full_feature_complete':int(events[FULL].notna().all(axis=1).sum()),
                         'price_only':summarize(price_only),'partial_context_common_sample':summarize(partial),
                         'full_context_common_sample':summarize(full)})
    records=load(archive)
    result={'version':'ATH_DEPTH_MODEL_RESEARCH_V1','mode':'READ_ONLY_EXPERIMENT',
            'instrument':'^GSPC cash-index proxy; intraday records in available 2019+ history',
            'model':'Fixed k=5 nearest neighbours; one prior count per class; training-only scaling',
            'sampling':'First eligible record high, then more than three calendar months between anchors',
            'source_pit_status':'PIT_LIMITED_HISTORICAL_RESEARCH_PROXIES',
            'source_hashes':{name:hashlib.sha256((Path(public_data)/name).read_bytes()).hexdigest()
                             for name in ['technical_intelligence_research_v1.csv','financial_stress_research_v1.csv',
                                          'sentiment_engine_research_v1.csv','liquidity_intelligence_research_v1.csv']
                             if (Path(public_data)/name).exists()},
            'source_snapshot_count':len(records),
            'archive_snapshot_ids':[r['snapshot_id'] for r in records],
            'snapshot_first_available_at':None if not records else records[0]['available_at'],
            'analyses':analyses,'live_forecast':None,
            'forecast_status':'NOT_VALIDATED', 'incremental_edge_status':'NOT_ESTABLISHED',
            'gate_reasons':['Historical input vintages and exact publication times are not independently verified.',
                            'Independent crash cases and walk-forward evaluation sample are too small for high-confidence claims.',
                            'Partial-context experiment excludes historical Macro/Fed where no captured snapshot exists.',
                            'No separately calibrated prospective forecast or external validation has been performed.'],
            'until_recovery_model_status':'NOT_TRAINED_RETROSPECTIVE_EPISODE_SELECTION_IS_NOT_A_FORECAST_SAMPLE',
            'price_features':PRICE,'partial_features':PARTIAL,'full_features':FULL,
            'research_only':True,'execution':False}
    return result,pd.concat(frames,ignore_index=True),predictions


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--public-data',type=Path,default=Path('public_data'))
    p.add_argument('--archive',type=Path,default=Path('research_history/ath_context_v1'))
    p.add_argument('--output',type=Path,default=Path('ath_pullback_research'))
    a=p.parse_args()
    if a.output.resolve()==a.public_data.resolve() or a.public_data.resolve() in a.output.resolve().parents:
        p.error('Research output must be outside public_data.')
    result,events,predictions=experiment(a.public_data,a.archive)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'model_research_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    events.to_csv(a.output/'model_event_table.csv',index=False)
    (a.output/'walk_forward_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2))


if __name__=='__main__': main()
