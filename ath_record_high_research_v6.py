"""Prospective-at-record-close cohort; no hindsight-selected pullbacks.

Available-history cash-index closing records are not independently proven
intraday ATHs, ES highs, or broker US500 highs. Live forecasting stays disabled.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import ath_pullback_edge_v3 as old
from ath_macro_edge_research_v4 import MACRO_FEATURES,attach
from ath_official_vintage_backfill_v1 import load_receipts,observation,SourceError

CLASSES=('NO_MEANINGFUL_PULLBACK','LIMITED','MEDIUM','CRASH')
PRICE=[x for x in old.PRICE if x!='days_since_peak']
MARKET=PRICE+[x for x in old.MARKET if x not in old.PRICE]
FULL=MARKET+list(MACRO_FEATURES)+['effective_fed_rate_pct','gdp_saar_pct']
PROTOCOL={'version':'ATH_RECORD_HIGH_V6','warmup_sessions':252,'cohort_spacing_calendar_months':3,
          'class_thresholds_pct':[3,5,20],'minimum_training_events':12,'ridge_penalty':10.0,
          'evaluation_start':'2019-01-01','minimum_evaluation_events':30,'minimum_evaluation_crashes':3,
          'models':['PRICE_RIDGE','MARKET_RIDGE','FULL_CONTEXT_RIDGE','CLIMATOLOGY'],
          'hypothesis':'Context known at a closing record high adds information about subsequent depth beyond price history and climatology.',
          'selection':'First strict available-history record close after a 252-session warmup and the previous selected decision plus 3 calendar months plus one day. Selection uses past/current data only.',
          'horizons':{'1M':'Maximum drawdown from a rolling closing peak over one calendar month after decision availability.',
                      '3M':'Same over three calendar months.',
                      'UNTIL_RECOVERY':'Original anchor loss until the first subsequent close >= anchor. If the next close sets/recovers the record, label is zero. No future requirement to drop 3%.'},
          'status':'EXPLORATORY: prior studies inspected these calendar years; not a pristine holdout.',
          'live_forecast':'DISABLED_PENDING_INDEPENDENT_VERIFICATION_AND_CALIBRATION'}


def label(value):
    return CLASSES[3] if value>=20 else CLASSES[2] if value>=5 else CLASSES[1] if value>=3 else CLASSES[0]


def cohort(data):
    peak=-np.inf;cooldown=None;events=[]
    for idx,row in data.iterrows():
        is_record=float(row.SP500)>peak
        peak=max(peak,float(row.SP500))
        if not is_record or idx<PROTOCOL['warmup_sessions']:continue
        if cooldown is not None and row.available<=cooldown:continue
        features=old.features(data,idx,row.date)
        features.pop('days_since_peak',None)
        events.append({'episode_id':hashlib.sha256(('AT_RECORD:'+row.date.isoformat()).encode()).hexdigest()[:24],
                       'peak_date':row.date.date().isoformat(),'decision_at':row.available.isoformat(),
                       'anchor_index':idx,'reference_close_peak':float(row.SP500),**features})
        cooldown=row.available.normalize()+pd.DateOffset(months=3)+pd.Timedelta(days=1)
    return pd.DataFrame(events)


def labels(data,anchors):
    rows=[]
    for _,anchor in anchors.iterrows():
        origin=pd.Timestamp(anchor.decision_at);following=data[data.index>anchor.anchor_index]
        for horizon in ('1M','3M','UNTIL_RECOVERY'):
            value=0.;peak=float(anchor.reference_close_peak)
            if horizon=='UNTIL_RECOVERY':
                recovery=following[following.SP500>=peak]
                complete=not recovery.empty
                window=following if not complete else following[following.index<=recovery.index[0]]
                for price in window.SP500:value=max(value,old.depth(peak,price))
                available=None if not complete else recovery.iloc[0].available.isoformat()
            else:
                end=origin.normalize()+pd.DateOffset(months=int(horizon[0]))
                window=following[following.date<=end]
                for price in window.SP500:
                    peak=max(peak,float(price));value=max(value,old.depth(peak,price))
                complete=data.date.iloc[-1]>=end
                available=(end+pd.Timedelta(days=1)).isoformat() if complete else None
            row=anchor.to_dict();row.pop('anchor_index')
            row.update(horizon=horizon,depth_pct=value,class_label=label(value),complete=complete,label_available_at=available)
            rows.append(row)
    return pd.DataFrame(rows)


def context(frame,receipts):
    out,coverage=attach(frame,receipts)
    for feature,sid in [('effective_fed_rate_pct','DFF'),('gdp_saar_pct','A191RL1Q225SBEA')]:
        out[feature]=np.nan
        for idx,row in out.iterrows():
            asof=(pd.Timestamp(row.decision_at)-pd.Timedelta(days=1)).date().isoformat()
            record=receipts.get((sid,asof));status='UNAVAILABLE_RECEIPT'
            if record:
                try:
                    value=observation(sid,asof,record['record']['response'])['level']
                    out.loc[idx,feature]=value;status='ASOF_VERIFIED'
                except SourceError as e:status=e.status
            coverage.append({'episode_id':row.episode_id,'decision_at':row.decision_at,'feature':feature,'as_of_date':asof,'status':status})
    return out,coverage


def prior(train):
    counts=np.array([train.class_label.eq(c).sum()+1 for c in CLASSES],dtype=float)
    return counts/counts.sum()


def ridge(train,event,columns):
    x=train[columns].to_numpy(float);q=event[columns].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(q).all():raise ValueError('Missing predictors cannot be imputed.')
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1
    x=(x-center)/scale;q=(q-center)/scale
    y=np.column_stack([train.class_label.eq(c).to_numpy(float) for c in CLASSES])
    base=prior(train)
    weights=np.linalg.solve(x.T@x+10*np.eye(len(columns)),x.T@(y-base))
    p=np.clip(base+q@weights,.001,1);return p/p.sum()


def score(probability,actual):
    return float(np.sum((probability-np.array([float(c==actual) for c in CLASSES]))**2))


def evaluate(frame,with_full=False):
    columns=FULL if with_full else MARKET
    usable=frame[frame.complete & frame[columns].apply(lambda c:np.isfinite(pd.to_numeric(c,errors='coerce'))).all(axis=1)].sort_values('decision_at')
    results=[]
    for _,event in usable.iterrows():
        train=usable[(usable.decision_at<event.decision_at)&(usable.label_available_at<event.decision_at)]
        if len(train)<12:continue
        r={'episode_id':event.episode_id,'decision_at':event.decision_at,'actual_class':event.class_label,
           'training_count':len(train),'latest_training_label_available_at':train.label_available_at.max(),
           'development':event.decision_at<PROTOCOL['evaluation_start']}
        models=[('price',PRICE),('market',MARKET),('climatology',None)]
        if with_full:models.append(('full_context',FULL))
        for name,cols in models:
            p=prior(train) if cols is None else ridge(train,event,cols)
            r[name+'_brier']=score(p,event.class_label);r[name+'_probabilities']=p.tolist()
        results.append(r)
    return results


def summarize(predictions):
    test=[r for r in predictions if not r['development']]
    names=['price','market','climatology']+(['full_context'] if test and 'full_context_brier' in test[0] else [])
    return {'evaluations':len(test),'class_counts':{c:sum(r['actual_class']==c for r in test) for c in CLASSES},
            'scores':{n:None if not test else float(np.mean([r[n+'_brier'] for r in test])) for n in names},
            'status':'NO_CONFIRMED_EDGE','live_probabilities':None,
            'note':'Descriptive exploratory comparison only; no calibrated live model or independent confirmation.'}


def run(public_data,official_vix,cache=None):
    path=Path(public_data)/'cross_asset_research_v1.csv';data=old.history(pd.read_csv(path))
    data,vix=old.official_vix(data,official_vix)
    anchors=cohort(data)
    if anchors.empty:raise ValueError('No eligible record highs.')
    events=labels(data,anchors)
    receipts=load_receipts(cache) if cache else {}
    events,coverage=context(events,receipts)
    predictions=[];analyses=[]
    for horizon in ('1M','3M','UNTIL_RECOVERY'):
        frame=events[events.horizon.eq(horizon)];market=evaluate(frame);full=evaluate(frame,True)
        analyses.append({'horizon':horizon,'selected_records':len(frame),'mature_records':int(frame.complete.sum()),
                         'historical_class_counts':frame[frame.complete].class_label.value_counts().to_dict(),
                         'full_context_feature_rows':int(frame[FULL].notna().all(axis=1).sum()),
                         'price_and_market_common_sample':summarize(market),'full_context_common_sample':summarize(full)})
        predictions += [{'horizon':horizon,'comparison':'PRICE_MARKET',**p} for p in market]
        predictions += [{'horizon':horizon,'comparison':'FULL_CONTEXT',**p} for p in full]
    audit={'version':'ATH_RECORD_HIGH_V6','protocol':PROTOCOL,'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
           'history_start':data.date.iloc[0].date().isoformat(),'history_end':data.date.iloc[-1].date().isoformat(),
           'selected_records':len(anchors),'unique_decisions':anchors.decision_at.nunique(),'official_vix':vix,
           'validated_receipts':len(receipts),'analyses':analyses,'context_coverage':coverage,
           'scope':'At an available-history closing record, not after an observed 3% pullback.',
           'research_only':True,'live_forecast':None,'execution':False,
           'limitations':['The cash-index available-history closing record is not an independently verified intraday ATH or an ES/broker US500 price.',
             'Closing-price availability is conservatively proxied by the next day, not verified publication timestamps.',
             'Many consecutive new records are omitted by a fixed three-calendar-month sampling rule.',
             'Existing receipts at 3% trigger dates cannot be reused as if they were known at earlier record-high dates.',
             'Until-recovery includes immediate new highs with zero depth; excluding them would select future pullbacks.',
             'Calendar years were inspected in prior studies; this is exploratory, not fresh confirmatory validation.',
             'No high-confidence or calibrated probability claim is permitted.']}
    return audit,events,predictions


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--public-data',type=Path,default=Path('public_data'))
    parser.add_argument('--official-vix',type=Path,required=True);parser.add_argument('--cache',type=Path)
    parser.add_argument('--output',type=Path,required=True);a=parser.parse_args()
    if 'public_data' in a.output.resolve().parts:parser.error('Output must be outside public_data')
    r,events,predictions=run(a.public_data,a.official_vix,a.cache);a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'record_high_v6_audit.json').write_text(json.dumps(r,indent=2,allow_nan=False))
    events.to_csv(a.output/'record_high_v6_events.csv',index=False)
    (a.output/'record_high_v6_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    print(json.dumps({k:v for k,v in r.items() if k!='context_coverage'},indent=2))

if __name__=='__main__':main()
