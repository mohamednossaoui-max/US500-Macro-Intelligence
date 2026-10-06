"""First daily-range EMA19 touch after an available-history high record.

EMA is frozen at the prior close. Context is assessed AFTER the touch day's
close, with next-day availability proxy. This is not an intraday forecast.
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
import ath_extended_history_research_v10 as gate

FEATURES=['return20','vol20','ema_slope5','close_vs_prior_ema_pct']
PROTOCOL={'version':'ATH_EMA19_TOUCH_V12','ema_span':19,'ema_adjust':False,
          'warmup_sessions':252,'horizon_sessions':63,'targets_pct':[5,10,20],
          'minimum_training_cases':30,'ridge_penalty':10,'evaluation_start':'2019-01-01',
          'selection':'First range touch Low <= prior-close EMA19 <= High, approached from above, per prior high-record cycle.',
          'anchor':'Prior observed daily High record; touch day must not regain/set the record.',
          'decision':'After touch-day close; conservative next-day availability proxy.',
          'label':'Future Low reaches target from frozen prior peak before High recovers peak or 63 subsequent sessions.',
          'same_day_policy':'Exclude already-reached targets at decision; unresolved target/recovery order excluded.',
          'features':FEATURES,'comparison':'Touch-conditioned historical baseline vs price/EMA context on identical cases.',
          'status':'EXPLORATORY; previously inspected years, no pristine holdout.',
          'live_forecast':None,'research_only':True,'execution':False}


def history(frame):
    required={'observation_date','availability_date','Open','High','Low','Close'}
    if not required.issubset(frame):raise ValueError('Explicit daily OHLC and availability required.')
    d=frame[sorted(required)].copy()
    d['date']=pd.to_datetime(d.observation_date,utc=True,errors='coerce').dt.normalize()
    d['available']=pd.to_datetime(d.availability_date,utc=True,errors='coerce')
    if d.date.isna().any() or d.date.duplicated().any() or d.available.isna().any():raise ValueError('Invalid/duplicate dates.')
    if (d.available != d.date+pd.Timedelta(days=1)).any():raise ValueError('Invalid availability proxy.')
    for f in ['Open','High','Low','Close']:
        d[f]=pd.to_numeric(d[f],errors='coerce')
        if not np.isfinite(d[f]).all() or (d[f]<=0).any():raise ValueError('Missing/nonpositive OHLC; no price fabrication.')
    if (d.High<d[['Open','Close','Low']].max(axis=1)).any() or (d.Low>d[['Open','Close','High']].min(axis=1)).any():
        raise ValueError('Inconsistent OHLC ranges.')
    d=d.sort_values('date').reset_index(drop=True)
    if d.empty:raise ValueError('Empty OHLC history.')
    d['ema19']=d.Close.ewm(span=19,adjust=False).mean()
    d['prior_ema19']=d.ema19.shift(1)
    return d


def select(data):
    peak=-np.inf;peak_date=None;seen=False;rows=[];excluded=[]
    for i,r in data.iterrows():
        ema=r.prior_ema19
        from_above=i>0 and data.Close.iloc[i-1]>ema
        touch=i>0 and from_above and r.Low<=ema<=r.High
        if r.High>=peak:
            if touch and i>=252:
                excluded.append({'date':r.date.date().isoformat(),'status':'TOUCH_AND_PEAK_RECOVERY_ORDER_UNRESOLVED'})
            if r.High>peak:
                peak=float(r.High);peak_date=r.date;seen=bool(touch)
            elif touch:
                seen=True
            continue
        if seen:continue
        if from_above and r.High<ema:
            seen=True
            if i>=252:excluded.append({'date':r.date.date().isoformat(),'status':'GAP_BELOW_EMA_NO_RANGE_TOUCH'})
            continue
        if not touch:continue
        seen=True
        if i<252:continue
        past=data.Close.iloc[:i+1]
        rows.append({'event_id':r.date.date().isoformat(),'cycle_id':peak_date.date().isoformat(),
                     'index':i,'decision_at':r.available.isoformat(),'peak':peak,
                     'touch_ema':float(ema),'touch_low':float(r.Low),
                     'known_depth_pct':100*(1-float(r.Low)/peak),
                     'return20':float(100*(past.iloc[-1]/past.iloc[-21]-1)),
                     'vol20':float(100*past.pct_change().tail(20).std()),
                     'ema_slope5':float(100*(ema/data.ema19.iloc[i-6]-1)),
                     'close_vs_prior_ema_pct':float(100*(r.Close/ema-1))})
    return pd.DataFrame(rows),excluded


def labels(data,events):
    rows=[]
    for _,event in events.iterrows():
        i=int(event['index']);last=i+63
        future=data.iloc[i+1:min(last+1,len(data))]
        recovery=future[future.High>=event.peak]
        if not recovery.empty:last=int(recovery.index[0]);future=future.loc[:last]
        complete=last<len(data)
        for target in [5,10,20]:
            hit=False;ambiguous=False
            for _,day in future.iterrows():
                reached=100*(1-day.Low/event.peak)+1e-9>=target
                recovered=day.High>=event.peak
                if recovered:
                    if reached and not hit:ambiguous=True
                    break
                if reached:hit=True
            already=event.known_depth_pct+1e-9>=target
            status='TARGET_ALREADY_REACHED' if already else 'INTRADAY_ORDER_UNRESOLVED' if ambiguous else 'ELIGIBLE'
            row=event.to_dict();row.pop('index')
            row.update(target_pct=target,eligible=status=='ELIGIBLE',status=status,complete=complete,
                       hit=int(hit) if complete and status=='ELIGIBLE' else None,
                       label_available_at=data.available.iloc[last].isoformat() if complete else None)
            rows.append(row)
    return pd.DataFrame(rows)


def predict(train,event):
    x=train[FEATURES].to_numpy(float);q=event[FEATURES].to_numpy(float)
    if not np.isfinite(x).all() or not np.isfinite(q).all():raise ValueError('No neutral imputation.')
    center=x.mean(axis=0);scale=x.std(axis=0);scale[scale<1e-12]=1
    x=(x-center)/scale;q=(q-center)/scale
    base=float((train.hit.sum()+1)/(len(train)+2))
    weights=np.linalg.solve(x.T@x+10*np.eye(len(FEATURES)),x.T@(train.hit.to_numpy(float)-base))
    return base,float(np.clip(base+q@weights,.001,.999))


def evaluate(events):
    rows=[]
    if events.empty:return rows
    usable=events[events.eligible&events.complete&events[FEATURES].notna().all(axis=1)].sort_values('decision_at')
    for _,e in usable.iterrows():
        train=usable[(usable.target_pct==e.target_pct)&(usable.decision_at<e.decision_at)
                     &(usable.label_available_at<e.decision_at)&(usable.cycle_id!=e.cycle_id)]
        if len(train)<30:continue
        base,model=predict(train,e)
        rows.append({'event_id':e.event_id,'target_pct':int(e.target_pct),'decision_at':e.decision_at,
                     'training_count':len(train),'latest_training_label_at':train.label_available_at.max(),
                     'hit':int(e.hit),'development':e.decision_at<'2019-01-01',
                     'baseline_probability':base,'model_probability':model,
                     'baseline_brier':float((base-e.hit)**2),'model_brier':float((model-e.hit)**2)})
    return rows


def summarize(events,predictions):
    out=[]
    for target in [5,10,20]:
        test=[p for p in predictions if p['target_pct']==target and not p['development']]
        calibration=[]
        for name in ['baseline','model']:
            for lo,hi in [(0,.2),(.2,.4),(.4,.6),(.6,.8),(.8,1.01)]:
                bucket=[p for p in test if lo<=p[name+'_probability']<hi]
                calibration.append({'model':name,'lower':lo,'upper':min(hi,1),'count':len(bucket),
                                    'mean_probability':float(np.mean([p[name+'_probability'] for p in bucket])) if bucket else None,
                                    'observed_rate':float(np.mean([p['hit'] for p in bucket])) if bucket else None})
        out.append({'target_pct':target,'evaluations':len(test),'hits':sum(p['hit'] for p in test) if test else None,
                    'baseline_brier':float(np.mean([p['baseline_brier'] for p in test])) if test else None,
                    'model_brier':float(np.mean([p['model_brier'] for p in test])) if test else None,
                    'calibration':calibration,'status':'NO_CONFIRMED_EDGE','high_confidence_probability':None})
    return out


def vendor(start,end):
    import yfinance as yf
    raw=yf.download('^GSPC',start=start,end=(pd.Timestamp(end)+pd.Timedelta(days=1)).date().isoformat(),
                    interval='1d',auto_adjust=False,progress=False,threads=False)
    if raw is None or raw.empty:raise RuntimeError('SOURCE_ERROR: vendor OHLC unavailable.')
    if isinstance(raw.columns,pd.MultiIndex):
        if set(raw.columns.get_level_values(1))!={'^GSPC'}:raise ValueError('Wrong or ambiguous symbol.')
        raw=raw.xs('^GSPC',axis=1,level=1)
    dates=pd.to_datetime(raw.index)
    if dates.tz is not None:dates=dates.tz_localize(None)
    out=raw[['Open','High','Low','Close']].reset_index(drop=True)
    out['observation_date']=dates.strftime('%Y-%m-%d')
    out['availability_date']=(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d')
    return out


def acquire(output,fetcher=None):
    output=gate.safe_output(output);start=gate.START
    end=(pd.Timestamp.now(tz='UTC').normalize()-pd.Timedelta(days=1)).date().isoformat()
    audit={'source_url':gate.SOURCE,'symbol':'^GSPC','start':start,'end':end,'status':'SOURCE_ERROR',
           'retrieved_at':pd.Timestamp.now(tz='UTC').isoformat(),'fallback_used':False,
           'price_vintages_certified':False,'ohlc_semantics':'Vendor unadjusted daily OHLC; intraday order unavailable.'}
    try:
        frame=(fetcher or vendor)(start,end);data=history(frame)
        if not data.date.between(pd.Timestamp(start,tz='UTC'),pd.Timestamp(end,tz='UTC')).all():
            raise ValueError('OHLC dates outside requested completed-day range.')
        proxy=frame.rename(columns={'Close':'SP500'})
        gate.write_calendar(output,proxy,start,end)
        frame.to_csv(output/'ohlc.csv',index=False)
        audit.update(status='VENDOR_OHLC_CALENDAR_MATCH',ohlc_sha256=gate.sha(output/'ohlc.csv'))
    except Exception as error:
        audit.update(error=str(error),error_type=type(error).__name__)
        (output/'ohlc_acquisition_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False));raise
    (output/'ohlc_acquisition_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
    return audit


def study(cache,output):
    cache=Path(cache);output=gate.safe_output(output)
    source=json.loads((cache/'ohlc_acquisition_audit.json').read_text())
    calendar=json.loads((cache/'calendar_audit.json').read_text())
    if source['status']!='VENDOR_OHLC_CALENDAR_MATCH' or source['symbol']!='^GSPC' or source['source_url']!=gate.SOURCE:
        raise ValueError('OHLC source gate did not pass.')
    if source['ohlc_sha256']!=gate.sha(cache/'ohlc.csv'):raise ValueError('OHLC changed after acquisition.')
    if calendar['status']!='CALENDAR_MATCH' or calendar['schedule_sha256']!=gate.sha(cache/'nyse_schedule.csv'):
        raise ValueError('Calendar gate did not pass.')
    raw=pd.read_csv(cache/'ohlc.csv');data=history(raw)
    if not data.date.between(pd.Timestamp(source['start'],tz='UTC'),pd.Timestamp(source['end'],tz='UTC')).all():
        raise ValueError('OHLC dates outside acquisition range.')
    check,_,_=gate.calendar_audit(raw.rename(columns={'Close':'SP500'}),source['start'],source['end'])
    if check['status']!='CALENDAR_MATCH':raise ValueError('Calendar replay mismatch.')
    selected,excluded=select(data);events=labels(data,selected);predictions=evaluate(events)
    audit={'protocol':PROTOCOL,'source_sha256':gate.sha(cache/'ohlc.csv'),'code_sha256':gate.sha(__file__),
           'history_start':data.date.iloc[0].isoformat(),'history_end':data.date.iloc[-1].isoformat(),
           'sessions':len(data),'zero_range_sessions':int(data.High.eq(data.Low).sum()),
           'touch_events':len(selected),'excluded_selection':excluded,
           'comparisons':summarize(events,predictions),'status':'NO_CONFIRMED_EDGE','live_forecast':None,
           'limitations':['Cash-index OHLC, not ES or broker US500; historical High/Low quality is vendor dependent.',
                         'EMA touch uses previous-day EMA; forecast evaluated after touch-day close only.',
                         'Intraday ordering unresolved cases excluded explicitly.',
                         'Daily availability proxy is not a certified historical release timestamp.',
                         'Previously inspected periods; no independent high-confidence forecast certificate.']}
    events.to_csv(output/'ema19_v12_events.csv',index=False)
    (output/'ema19_v12_predictions.json').write_text(json.dumps(predictions,indent=2,allow_nan=False))
    (output/'ema19_v12_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
    return audit


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['acquire','study'],required=True)
    p.add_argument('--cache',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.mode=='acquire':r=acquire(a.output)
    else:
        if not a.cache:p.error('--cache required')
        r=study(a.cache,a.output)
    print(json.dumps({k:v for k,v in r.items() if k not in ['excluded_selection','comparisons']},indent=2,allow_nan=False))


if __name__=='__main__':main()
