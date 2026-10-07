"""Temporal conditional-depth comparison with genuine cause/context receipts.

Starts after FIRST closing 3% drawdown from a known high record. Outcome uses
future Low before High recovery or 63 sessions. Unknown intraday order is null.
No current context is backcast onto historic events, and no live forecast is certified.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import ath_ema19_touch_research_v12 as prices
import ath_cause_context_v1 as context

PRICE_FEATURES=['return20','vol20','days_from_peak']
ALL_FEATURES=PRICE_FEATURES+list(context.FEATURES)
PROTOCOL={'version':'ATH_CAUSE_DEPTH_V1','research_only':True,'live_forecast':None,
          'stage_pct':3,'targets_pct':[5,10,20,30],'horizon_sessions':63,'warmup_sessions':252,
          'minimum_training_cases':30,'ridge_penalty':10.,'evaluation_start':'2019-01-01',
          'origin':'First close >=3% below available-history High record per cycle; known next calendar day.',
          'target':'Future Low reaches frozen-peak target before High recovery or 63 sessions.',
          'historical_features':ALL_FEATURES,'historical_scope':'Context-confirmation subset, not a trained headline causal model.',
          'capture':'Genuine capture availability only; no backdating source/observation dates.',
          'promotion':'No live probabilities without independent prospective validation and adequate calibration.'}


def events(d,warmup=252,horizon=63):
    peak=-np.inf;peak_date=None;seen=False;anchors=[]
    for i,r in d.iterrows():
        if r.High>peak:peak=float(r.High);peak_date=r.date;seen=False
        depth=max(0.,100*(1-float(r.Close)/peak))
        if depth+1e-9>=3 and not seen:
            seen=True
            if i>=warmup:
                closes=d.Close.iloc[:i+1]
                anchors.append({'index':i,'event_id':r.observation_date,'cycle_id':peak_date.date().isoformat(),
                                'decision_at':r.available.isoformat(),'peak':peak,'observed_depth_pct':depth,
                                'return20':float(100*(closes.iloc[-1]/closes.iloc[-21]-1)),
                                'vol20':float(closes.pct_change().tail(20).std()*100),
                                'days_from_peak':float((r.date-peak_date).days)})
    output=[]
    for a in anchors:
        i=a['index'];terminal=i+horizon;window=d.iloc[i+1:min(terminal+1,len(d))]
        recovery=window[window.High>=a['peak']]
        if not recovery.empty:terminal=int(recovery.index[0]);window=window.loc[:terminal]
        mature=terminal<len(d)
        for target in PROTOCOL['targets_pct']:
            # If today's range already touched target, it is not a future forecast event.
            already=100*(1-float(d.Low.iloc[i])/a['peak'])+1e-9>=target
            hit=False;ambiguous=False
            for _,r in window.iterrows():
                reaches=r.Low<=a['peak']*(1-target/100)+1e-9
                recovers=r.High>=a['peak']
                if recovers:
                    if reaches and not hit:ambiguous=True
                    break
                if reaches:hit=True
            row={k:v for k,v in a.items() if k!='index'}
            row.update(target_pct=target,complete=mature,eligible=not already and not ambiguous,
                       exclusion='TARGET_ALREADY_REACHED' if already else 'TARGET_RECOVERY_ORDER_UNKNOWN' if ambiguous else '',
                       label_available_at=d.available.iloc[terminal].isoformat() if mature else None,
                       hit=int(hit) if mature and not ambiguous and not already else None)
            output.append(row)
    return pd.DataFrame(output)


def attach(frame,receipts):
    result=frame.copy()
    for name in context.FEATURES:result[name]=np.nan
    result['context_snapshot_id']=None;result['context_available_at']=None
    for i,r in result.iterrows():
        cutoff=context.utc(r.decision_at)
        candidates=[x for x in receipts if context.utc(x['available_at'])<cutoff and
                    cutoff-context.utc(x['available_at'])<=pd.Timedelta(days=7)]
        if not candidates:continue
        rec=max(candidates,key=lambda x:x['available_at']);values=rec['payload']['context_features']
        evidence={x['feature']:x for x in rec['payload']['feature_evidence']}
        for name in context.FEATURES:
            if name not in values or name not in evidence:continue
            e=evidence[name]
            if context.utc(e['available_at'])>=cutoff or context.utc(e['as_of'])>cutoff:continue
            if cutoff-context.utc(e['as_of'])>pd.Timedelta(days=context.AGE[name]):continue
            value=float(values[name])
            if np.isfinite(value):result.loc[i,name]=value
        result.loc[i,'context_snapshot_id']=rec['snapshot_id']
        result.loc[i,'context_available_at']=rec['available_at']
    return result


def probability(train,event,fields):
    x=train[fields].to_numpy(float);q=event[fields].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(q).all():raise ValueError('Missing features cannot be neutral-imputed.')
    base=float((train.hit.sum()+1)/(len(train)+2))
    mean=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1
    x=(x-mean)/scale;q=(q-mean)/scale
    w=np.linalg.solve(x.T@x+PROTOCOL['ridge_penalty']*np.eye(len(fields)),x.T@(train.hit.to_numpy(float)-base))
    return base,float(np.clip(base+q@w,.001,.999))


def evaluate(frame,fields,min_train=30):
    if frame.empty:return []
    good=frame.eligible & frame.complete
    good &= frame[fields].apply(pd.to_numeric,errors='coerce').apply(lambda s:np.isfinite(s)).all(axis=1)
    usable=frame[good].sort_values(['decision_at','target_pct']);pred=[]
    for _,r in usable.iterrows():
        train=usable[(usable.target_pct==r.target_pct)&(usable.decision_at<r.decision_at)&
                     (usable.label_available_at<r.decision_at)&(usable.cycle_id!=r.cycle_id)]
        if len(train)<min_train:continue
        base,model=probability(train,r,fields)
        pred.append({'event_id':r.event_id,'cycle_id':r.cycle_id,'target_pct':int(r.target_pct),
                     'decision_at':r.decision_at,'training_count':len(train),
                     'latest_training_label_at':train.label_available_at.max(),
                     'hit':int(r.hit),'baseline_probability':base,'model_probability':model,
                     'baseline_brier':float((base-r.hit)**2),'model_brier':float((model-r.hit)**2)})
    return pred


def summarize(pred):
    rows=[]
    for target in PROTOCOL['targets_pct']:
        selected=[x for x in pred if x['target_pct']==target and x['decision_at']>=PROTOCOL['evaluation_start']]
        rows.append({'target_pct':target,'evaluations':len(selected),'hits':sum(x['hit'] for x in selected),
                     'baseline_brier':float(np.mean([x['baseline_brier'] for x in selected])) if selected else None,
                     'model_brier':float(np.mean([x['model_brier'] for x in selected])) if selected else None,
                     'calibration':[{ 'lower':lo,'upper':hi,'count':len(bucket),
                        'mean_probability':float(np.mean([x['model_probability'] for x in bucket])) if bucket else None,
                        'observed_rate':float(np.mean([x['hit'] for x in bucket])) if bucket else None}
                       for lo,hi in [(0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.0001)]
                       for bucket in [[x for x in selected if lo<=x['model_probability']<hi]]],
                     'status':'INSUFFICIENT_HISTORICAL_CONTEXT' if not selected else 'EXPLORATORY_NOT_VALIDATED',
                     'live_probability':None})
    return rows


def run(root,cache,archive,output,as_of=None):
    output=prices.gate.safe_output(output)
    current=context.assess(root,as_of)
    capture=context.capture(current,archive)
    receipt=prices.study(cache,output/'source_validation')
    d=prices.history(pd.read_csv(Path(cache)/'ohlc.csv'))
    # Historical research ends at genuinely assessed cutoff; never use future bars.
    d=d[d.available<=context.utc(current['as_of'])].reset_index(drop=True)
    table=attach(events(d),context.load(archive))
    price_predictions=evaluate(table,PRICE_FEATURES)
    common_price=evaluate(table[table[list(context.FEATURES)].notna().all(axis=1)],PRICE_FEATURES)
    contextual=evaluate(table,ALL_FEATURES)
    current['probability_status']='INSUFFICIENT_HISTORICAL_CAUSE_VINTAGES' if not contextual else 'NO_INDEPENDENT_VALIDATED_EDGE'
    current['depth_probabilities']=None
    current['targets']=[{'target_pct':x,'probability':None,'status':current['probability_status']} for x in PROTOCOL['targets_pct']]
    audit={'protocol':PROTOCOL,'code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
           'source_sha256':receipt['source_sha256'],'snapshot_count':capture['snapshot_count'],
           'capture':capture,'event_rows':len(table),'events_with_full_context':int(table[list(context.FEATURES)].notna().all(axis=1).sum()),
           'price_only_comparison':summarize(price_predictions),
           'common_sample_price_comparison':summarize(common_price),'context_comparison':summarize(contextual),
           'live_forecast':None,'status':current['probability_status'],
           'limitations':['Current programme context/news cannot fill historical vintages.',
                          'Same previously examined cash-price history; no pristine holdout.',
                          'Headlines produce candidates, not trained causal probabilities.',
                          'Full context model covers five numerical confirmation channels, not all eight headline causes.',
                          'First closing 3% landmark differs from real-time intraday touch.',
                          'Unknown target/recovery ordering and already-reached targets are excluded.',
                          'A genuine forward archive is required; preserve workflow artifact snapshots between runs.',
                          'Partial coverage or better retrospective Brier alone cannot release live probabilities.']}
    table.to_csv(output/'ath_cause_depth_events_v1.csv',index=False)
    (output/'ath_cause_depth_predictions_v1.json').write_text(json.dumps({'price_only':price_predictions,'common_price':common_price,'context':contextual},indent=2,allow_nan=False))
    (output/'ath_cause_depth_audit_v1.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
    (output/'ath_cause_current_v1.json').write_text(json.dumps(current,indent=2,ensure_ascii=False,allow_nan=False))
    return audit,current


def main():
    p=argparse.ArgumentParser();p.add_argument('--public-data',type=Path,default=Path('public_data'))
    p.add_argument('--cache',type=Path,required=True);p.add_argument('--archive',type=Path,default=Path('research_history/ath_cause_v1'))
    p.add_argument('--output',type=Path,default=Path('ath_cause_run/study'));p.add_argument('--as-of')
    a=p.parse_args();audit,current=run(a.public_data,a.cache,a.archive,a.output,a.as_of)
    print(json.dumps({'status':audit['status'],'event_rows':audit['event_rows'],
                      'events_with_full_context':audit['events_with_full_context'],'snapshots':audit['snapshot_count'],
                      'current_candidates':[{k:x[k] for k in ('cause','status')} for x in current['causes']],
                      'price_status':current['observed_market_response']['price_status'],'live_forecast':None},indent=2))


if __name__=='__main__':main()
