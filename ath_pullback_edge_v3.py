"""Frozen exploratory protocol: depth after a known 3% closing pullback.

Closing records in available cash-index history are NOT intraday ATHs or ES
prices. No training, model selection, or normalization uses future outcomes.
This is candidate-edge research, not a certified live forecasting service.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ath_context_archive_v1 import utc

CLASSES = ('LIMITED', 'MEDIUM', 'CRASH')
PRICE = ['return20', 'vol20', 'above_ma60', 'days_since_peak']
MARKET = PRICE + ['vix_level', 'vix_change20', 'nasdaq_relative20', 'dxy_return20', 'us10y_vendor_change20']
PROTOCOL = {'version':'ATH_EDGE_V3', 'trigger_min_pct':3, 'trigger_max_exclusive_pct':5,
            'warmup_sessions':63, 'ridge_penalty':10.0, 'minimum_training_episodes':12,
            'development_end':'2018-12-31', 'evaluation_start':'2019-01-01',
            'bootstrap_draws':2000, 'bootstrap_block_episodes':3, 'bootstrap_seed':20261004,
            'minimum_evaluation_episodes_for_candidate':30, 'minimum_evaluation_crashes_for_candidate':3,
            'family_comparisons':6, 'models':['PRICE_RIDGE','MARKET_CONTEXT_RIDGE'],
            'hypothesis':'Market volatility and relative risk-asset behaviour add information about depth after an observed 3% closing drawdown.',
            'human_research_status':'EXPLORATORY: 2019-2026 calendar periods were also examined in earlier studies; not a pristine external holdout.',
            'live_forecast_policy':'DISABLED_PENDING_INDEPENDENT_DATA_VERIFICATION_CALIBRATION_AND_PROSPECTIVE_VALIDATION'}


def history(frame):
    required={'observation_date','availability_date','SP500', 'VIX','NASDAQ','DXY','US10Y'}
    if not required.issubset(frame):
        raise ValueError('Cross-asset close history and availability metadata are required.')
    data=frame.copy()
    data['date']=pd.to_datetime(data.observation_date,utc=True,errors='coerce').dt.normalize()
    data['available']=pd.to_datetime(data.availability_date,utc=True,errors='coerce')
    if data.date.isna().any() or data.date.duplicated().any() or data.available.isna().any():
        raise ValueError('Invalid/duplicate observation or availability dates.')
    if (data.available != data.date + pd.Timedelta(days=1)).any():
        raise ValueError('Conservative next-day price availability is required.')
    for col in ['SP500','VIX','NASDAQ','DXY','US10Y']:
        data[col]=pd.to_numeric(data[col],errors='coerce')
    data=data[data.SP500.notna()].sort_values('date').reset_index(drop=True)
    if data.empty or not np.isfinite(data.SP500).all() or (data.SP500<=0).any():
        raise ValueError('Cash-index prices must be finite and positive.')
    # Unknown source flags cannot be silently promoted to verified vintages.
    return data


def depth(peak, price):
    return round(max(0,100*(1-float(price)/float(peak))),10)


def category(value):
    return 'CRASH' if value>=20 else 'MEDIUM' if value>=5 else 'LIMITED'


def features(data, index, peak_date):
    past=data.iloc[:index+1]
    if len(past)<PROTOCOL['warmup_sessions']:
        return None
    closes=past.SP500
    latest=past.iloc[-1]
    out={'return20':100*(closes.iloc[-1]/closes.iloc[-21]-1),
         'vol20':100*closes.pct_change().tail(20).std(),
         'above_ma60':100*(closes.iloc[-1]/closes.tail(60).mean()-1),
         'days_since_peak':float((latest.date-peak_date).days)}
    for field in MARKET[len(PRICE):]:out[field]=np.nan
    if pd.notna(latest.VIX) and latest.VIX>0:
        out['vix_level']=float(latest.VIX)
    old=past.iloc[-21]
    if pd.notna(old.VIX) and old.VIX>0 and pd.notna(latest.VIX):
        out['vix_change20']=100*(latest.VIX/old.VIX-1)
    if pd.notna(latest.NASDAQ) and pd.notna(old.NASDAQ) and old.NASDAQ>0:
        out['nasdaq_relative20']=100*(latest.NASDAQ/old.NASDAQ-closes.iloc[-1]/closes.iloc[-21])
    if pd.notna(latest.DXY) and pd.notna(old.DXY) and old.DXY>0:
        out['dxy_return20']=100*(latest.DXY/old.DXY-1)
    if pd.notna(latest.US10Y) and pd.notna(old.US10Y):
        # Vendor ^TNX quote units; explicitly not labelled basis points.
        out['us10y_vendor_change20']=float(latest.US10Y-old.US10Y)
    return out


def episodes(data):
    """Every crossing is tracked, even in warmup or after a gap to >=5%.

    Excluded early/gapped episodes cannot be re-entered later with hindsight.
    New eligible episodes require a strictly new closing record after recovery.
    """
    peak=float(data.SP500.iloc[0]);peak_date=data.date.iloc[0]
    armed=True;active=None;out=[]
    for index,row in data.iterrows():
        price=float(row.SP500)
        if active is not None:
            active['observed_depth']=max(active['observed_depth'],depth(peak,price))
            if price >= peak:
                active['recovery_index']=index
                active['recovery_available']=row.available.isoformat()
                out.append(active);active=None;armed=False
            else:
                continue
        if price>peak:
            peak,peak_date,armed=price,row.date,True
        dd=depth(peak,price)
        if armed and dd>=PROTOCOL['trigger_min_pct']:
            f=features(data,index,peak_date)
            reason=None
            if f is None:reason='WARMUP_OR_LEFT_CENSORED'
            elif dd>=PROTOCOL['trigger_max_exclusive_pct']:reason='ALREADY_MEDIUM_AT_FIRST_OBSERVED_CROSSING'
            active={'episode_id':hashlib.sha256((peak_date.isoformat()+row.date.isoformat()).encode()).hexdigest()[:24],
                    'peak_date':peak_date.date().isoformat(),'reference_close_peak':peak,
                    'trigger_date':row.date.date().isoformat(),'decision_at':row.available.isoformat(),
                    'trigger_index':index,'activation_depth_pct':dd,'observed_depth':dd,
                    'eligible':reason is None,'exclusion_reason':reason,'features':f,
                    'recovery_index':None,'recovery_available':None}
            armed=False
    if active is not None:out.append(active)
    return out


def event_table(data, horizon):
    rows=[];cooldown=None
    for event in episodes(data):
        if not event['eligible']:continue
        origin=utc(event['decision_at'])
        if horizon!='UNTIL_RECOVERY' and cooldown is not None and origin<=cooldown:continue
        maximum=event['activation_depth_pct'];peak=event['reference_close_peak']
        if horizon=='UNTIL_RECOVERY':
            maximum=event['observed_depth']
            matured=event['recovery_index'] is not None
            available=event['recovery_available']
            metric='ORIGINAL_CLOSING_PEAK_UNTIL_RECOVERY'
        else:
            if horizon not in ('1M','3M'):raise ValueError('Unknown horizon.')
            end=origin.normalize()+pd.DateOffset(months=int(horizon[0]))
            cooldown=end+pd.Timedelta(days=1)
            window=data[(data.index>event['trigger_index']) & (data.date<=end)]
            for price in window.SP500:
                peak=max(peak,float(price));maximum=max(maximum,depth(peak,price))
            matured=data.date.iloc[-1]>=end
            available=(end+pd.Timedelta(days=1)).isoformat() if matured else None
            metric='CLOSING_ROLLING_PEAK_INCLUDING_KNOWN_ACTIVATION_DEPTH'
        row={k:event[k] for k in ['episode_id','peak_date','trigger_date','decision_at','reference_close_peak','activation_depth_pct']}
        row.update(event['features']);row.update(horizon=horizon,depth_pct=maximum,class_label=category(maximum),
                                               complete=matured,label_available_at=available,metric=metric)
        rows.append(row)
    return pd.DataFrame(rows)


def prior(train):
    counts=np.array([train.class_label.eq(c).sum() for c in CLASSES],dtype=float)+1
    return counts/counts.sum()


def ridge(train, target, columns):
    x=train[columns].to_numpy(dtype=float);q=np.array([target[c] for c in columns],dtype=float)
    if not len(train) or not np.isfinite(x).all() or not np.isfinite(q).all():
        raise ValueError('Missing/nonfinite predictors are not imputed.')
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1
    x=(x-center)/scale;q=(q-center)/scale
    y=np.column_stack([train.class_label.eq(c).astype(float).to_numpy() for c in CLASSES])
    base=prior(train)
    weights=np.linalg.solve(x.T@x+PROTOCOL['ridge_penalty']*np.eye(len(columns)),x.T@(y-base))
    probability=np.clip(base+q@weights,0.001,1)
    return probability/probability.sum()


def brier(probability, actual):
    return float(np.sum((np.asarray(probability)-np.array([float(c==actual) for c in CLASSES]))**2))


def evaluate(frame):
    if frame.empty:return []
    frame=frame.sort_values('decision_at').copy()
    if frame.episode_id.duplicated().any():raise ValueError('Duplicate episodes.')
    complete=frame.complete & frame[MARKET].apply(lambda s:np.isfinite(pd.to_numeric(s,errors='coerce'))).all(axis=1)
    usable=frame[complete]
    results=[]
    for _,event in usable.iterrows():
        train=usable[(usable.decision_at<event.decision_at)&(usable.label_available_at<event.decision_at)]
        if len(train)<PROTOCOL['minimum_training_episodes']:continue
        p0,p1,pc=ridge(train,event,PRICE),ridge(train,event,MARKET),prior(train)
        results.append({'episode_id':event.episode_id,'decision_at':event.decision_at,
                        'label_available_at':event.label_available_at,'actual_class':event.class_label,
                        'development':utc(event.decision_at)<utc(PROTOCOL['evaluation_start']),
                        'training_episodes':len(train),'training_latest_label_available_at':train.label_available_at.max(),
                        'price_brier':brier(p0,event.class_label),'market_brier':brier(p1,event.class_label),
                        'climatology_brier':brier(pc,event.class_label),
                        'price_probabilities':p0.tolist(),'market_probabilities':p1.tolist(),
                        'climatology_probabilities':pc.tolist()})
    return results


def interval(values):
    x=np.asarray(values,dtype=float)
    if len(x)<2:return None
    rng=np.random.default_rng(PROTOCOL['bootstrap_seed']);samples=[];n=len(x);block=PROTOCOL['bootstrap_block_episodes']
    for _ in range(PROTOCOL['bootstrap_draws']):
        starts=rng.integers(0,n,size=int(np.ceil(n/block)))
        ids=np.concatenate([(np.arange(block)+s)%n for s in starts])[:n]
        samples.append(x[ids].mean())
    alpha=.05/PROTOCOL['family_comparisons']
    return {'mean':float(x.mean()),'lower':float(np.quantile(samples,alpha/2)),
            'upper':float(np.quantile(samples,1-alpha/2)),
            'method':'Exploratory moving-block percentile bootstrap, adjusted alpha=0.05/6; coverage is not guaranteed'}


def summary(predictions):
    test=[r for r in predictions if not r['development']]
    price=interval([r['price_brier']-r['market_brier'] for r in test])
    climate=interval([r['climatology_brier']-r['market_brier'] for r in test])
    crashes=sum(r['actual_class']=='CRASH' for r in test)
    sufficient=len(test)>=PROTOCOL['minimum_evaluation_episodes_for_candidate'] and crashes>=PROTOCOL['minimum_evaluation_crashes_for_candidate']
    positive=price is not None and climate is not None and price['lower']>0 and climate['lower']>0
    return {'development_predictions':sum(r['development'] for r in predictions),'evaluation_predictions':len(test),
            'test_class_counts':{c:sum(r['actual_class']==c for r in test) for c in CLASSES},
            'mean_scores':{k:None if not test else float(np.mean([r[k] for r in test]))
                           for k in ['price_brier','market_brier','climatology_brier']},
            'improvement_vs_price':price,'improvement_vs_climatology':climate,
            'candidate_status':'CANDIDATE_ONLY' if sufficient and positive else 'NO_CONFIRMED_EDGE',
            'live_probabilities':None, 'high_confidence_claim_allowed':False}


def official_vix(data, path):
    raw=Path(path).read_bytes()
    official=pd.read_csv(path)
    if not {'DATE','CLOSE'}.issubset(official):raise ValueError('Invalid official VIX schema.')
    dates=pd.to_datetime(official.DATE,format='%m/%d/%Y',utc=True,errors='coerce')
    values=pd.to_numeric(official.CLOSE,errors='coerce')
    if dates.isna().any() or dates.duplicated().any() or not np.isfinite(values).all() or (values<=0).any():
        raise ValueError('Invalid official VIX observations.')
    matched=data.date.map(dict(zip(dates,values)))
    if matched.isna().any():raise ValueError('Official VIX does not cover every closing session; no vendor fallback.')
    delta=(data.VIX-matched).abs()
    out=data.copy();out['VIX']=matched
    return out,{'source_url':'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv',
                'sha256':hashlib.sha256(raw).hexdigest(),'matched_sessions':len(data),
                'vendor_differences_above_0_02':int((delta>0.02).sum()),
                'maximum_absolute_difference':float(delta.max()),
                'verification':'OFFICIAL_CURRENT_HISTORY_NOT_CERTIFIED_HISTORICAL_VINTAGES'}


def run(public_data, official_vix_path=None):
    path=Path(public_data)/'cross_asset_research_v1.csv';data=history(pd.read_csv(path))
    vix_receipt=None
    if official_vix_path is not None:data,vix_receipt=official_vix(data,official_vix_path)
    events=[];predictions=[];analyses=[]
    for horizon in ('1M','3M','UNTIL_RECOVERY'):
        frame=event_table(data,horizon);p=evaluate(frame)
        analyses.append({'horizon':horizon,'eligible_episodes':len(frame),
                         'completed_episodes':int(frame.complete.sum()) if not frame.empty else 0,**summary(p)})
        events.append(frame);predictions.extend([{'horizon':horizon,**r} for r in p])
    result={'version':'ATH_EDGE_V3','protocol':PROTOCOL,'source_file':path.name,
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'history_start':data.date.iloc[0].date().isoformat(),'history_end':data.date.iloc[-1].date().isoformat(),
            'official_vix':vix_receipt,'closing_sessions':len(data),'instrument':'^GSPC CASH_INDEX_CLOSE_PROXY',
            'source_pit_status':'PIT_LIMITED_VENDOR_HISTORY_WITH_PLUS_ONE_DAY_PROXY',
            'analyses':analyses,'live_forecast':None,'forecast_status':'NOT_VALIDATED',
            'scope':'Risk AFTER observed 3%-<5% close drawdown; not risk at the ATH and not trading rules.',
            'limitations':['Closing-record highs are not intraday ATHs or ES/broker-US500 highs.',
                           'Historical source vintages/session publication times are not independently certified.',
                           'Macro/Fed/Decision are not backcast into historical predictors.',
                           'The 2019-2026 periods are reused exploratory research, not untouched confirmatory data.',
                           'Calendar completeness and individual vendor unit consistency have not been independently verified.',
                           'Bootstrap intervals are diagnostic; rare crises and small samples limit inference.'],
            'research_only':True,'execution':False}
    return result,pd.concat(events,ignore_index=True),predictions


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--public-data',type=Path,default=Path('public_data'))
    p.add_argument('--output',type=Path,default=Path('ath_pullback_research_v3'))
    p.add_argument('--official-vix',type=Path)
    a=p.parse_args()
    if a.output.resolve()==a.public_data.resolve() or a.public_data.resolve() in a.output.resolve().parents:
        p.error('Research output must be outside public_data.')
    result,events,predictions=run(a.public_data,a.official_vix)
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'edge_v3_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    events.to_csv(a.output/'edge_v3_events.csv',index=False)
    (a.output/'edge_v3_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
