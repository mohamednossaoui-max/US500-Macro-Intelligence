"""Read-only price acquisition/calendar gate for the frozen V9 protocol.

Yahoo is the existing project's price vendor, not an official vintage archive.
NYSE sessions are independently reconstructed by pandas_market_calendars;
agreement does not certify the vendor's historical prices or timestamps.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import pandas as pd
import numpy as np
import pandas_market_calendars as calendars
import ath_sequential_pullback_research_v9 as v9

START = '1957-03-04'
SOURCE = 'https://finance.yahoo.com/quote/%5EGSPC/history/'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def safe_output(output):
    output=Path(output)
    if 'public_data' in output.resolve().parts:raise ValueError('Output must be outside public_data.')
    output.mkdir(parents=True,exist_ok=True)
    return output


def expected_sessions(start,end):
    return calendars.get_calendar('NYSE').schedule(start_date=start,end_date=end)


def calendar_audit(frame,start,end,schedule=None):
    required={'observation_date','availability_date','SP500'}
    if not required.issubset(frame):raise ValueError('Price/date/availability columns required.')
    dates=pd.to_datetime(frame.observation_date,utc=True,errors='coerce')
    if dates.isna().any() or dates.dt.normalize().duplicated().any():
        raise ValueError('Invalid or duplicate source dates.')
    available=pd.to_datetime(frame.availability_date,utc=True,errors='coerce')
    if available.isna().any() or (available != dates.dt.normalize()+pd.Timedelta(days=1)).any():
        raise ValueError('Invalid conservative availability proxy.')
    values=pd.to_numeric(frame.SP500,errors='coerce')
    invalid=frame.SP500.notna() & (~np.isfinite(values) | (values<=0))
    if invalid.any():raise ValueError('Invalid cash prices cannot be discarded.')
    schedule=expected_sessions(start,end) if schedule is None else schedule
    expected=set(schedule.index.strftime('%Y-%m-%d'))
    if not expected:raise ValueError('No calendar sessions in requested range.')
    day=dates.dt.strftime('%Y-%m-%d'); scope=day.between(start,end)
    observed=set(day[scope & values.notna()])
    missing=sorted(expected-observed);unexpected=sorted(observed-expected)
    excluded=[{'observation_date':d,'status':'MARKET_CLOSED_ACCORDING_TO_CALENDAR' if d not in expected
               else 'MISSING_CASH_PRICE_ON_EXPECTED_SESSION'} for d in day[scope & values.isna()]]
    audit={'start':start,'end':end,'calendar':'NYSE',
           'calendar_implementation':'pandas_market_calendars',
           'calendar_package_version':importlib.metadata.version('pandas_market_calendars'),
           'expected_sessions':len(expected),'observed_sessions':len(observed),
           'missing_sessions':missing,'unexpected_price_dates':unexpected,'excluded_rows':excluded,
           'status':'CALENDAR_MATCH' if not missing and not unexpected else 'CALENDAR_MISMATCH',
           'official_price_vintages_verified':False,
           'limitation':'Calendar-library agreement is not certification by NYSE or S&P of prices or vintages.'}
    clean=frame.loc[scope & values.notna(),sorted(required)].copy()
    clean['observation_date']=day[scope & values.notna()].values
    clean['availability_date']=(pd.to_datetime(clean.observation_date)+pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    clean['SP500']=values[scope & values.notna()].values
    return audit,clean.sort_values('observation_date').reset_index(drop=True),schedule


def vendor_prices(start,end):
    import yfinance as yf
    raw=yf.download('^GSPC',start=start,end=(pd.Timestamp(end)+pd.Timedelta(days=1)).date().isoformat(),
                    interval='1d',auto_adjust=False,progress=False,threads=False)
    if raw is None or raw.empty:raise RuntimeError('SOURCE_ERROR: Yahoo returned no daily cash history.')
    close=raw['Close']
    if isinstance(close,pd.DataFrame):
        if list(close.columns)!=['^GSPC']:raise ValueError('Ambiguous symbol in vendor response.')
        close=close['^GSPC']
    dates=pd.to_datetime(close.index)
    if dates.tz is not None:dates=dates.tz_localize(None)
    frame=pd.DataFrame({'observation_date':dates.strftime('%Y-%m-%d'),
                        'availability_date':(dates+pd.Timedelta(days=1)).strftime('%Y-%m-%d'),
                        'SP500':close.to_numpy()})
    return frame


def write_calendar(output,frame,start,end):
    audit,clean,schedule=calendar_audit(frame,start,end)
    schedule.to_csv(output/'nyse_schedule.csv')
    audit['schedule_sha256']=sha(output/'nyse_schedule.csv')
    (output/'calendar_audit.json').write_text(json.dumps(audit,indent=2,allow_nan=False))
    if audit['status']!='CALENDAR_MATCH':
        raise RuntimeError('CALENDAR_MISMATCH: research blocked; inspect calendar_audit.json.')
    clean.to_csv(output/'validated_prices.csv',index=False)
    return audit


def acquire(output,start=START,end=None,fetcher=None):
    output=safe_output(output)
    end=end or (pd.Timestamp.now(tz='UTC').normalize()-pd.Timedelta(days=1)).date().isoformat()
    if start<START:raise ValueError('Pre-launch predecessor history is outside this protocol.')
    if pd.Timestamp(end)>=pd.Timestamp.now(tz='UTC').normalize().tz_localize(None):
        raise ValueError('Only completed calendar days may be requested.')
    record={'source_url':SOURCE,'symbol':'^GSPC','start':start,'end':end,
            'price_field':'Unadjusted daily Close','retrieved_at':pd.Timestamp.now(tz='UTC').isoformat(),
            'provider_current_history':True,'official_vintage_archive':False,
            'fallback_used':False,'status':'SOURCE_ERROR'}
    try:
        frame=(fetcher or vendor_prices)(start,end)
        frame.to_csv(output/'vendor_prices.csv',index=False)
        record['vendor_prices_sha256']=sha(output/'vendor_prices.csv')
        write_calendar(output,frame,start,end)
        record['validated_prices_sha256']=sha(output/'validated_prices.csv')
        record['status']='VALIDATED_VENDOR_HISTORY_CALENDAR_MATCH'
    except Exception as error:
        record['error']=str(error);record['error_type']=type(error).__name__
        (output/'acquisition_audit.json').write_text(json.dumps(record,indent=2,allow_nan=False))
        raise
    (output/'acquisition_audit.json').write_text(json.dumps(record,indent=2,allow_nan=False))
    return record


def study(cache,output):
    cache=Path(cache);output=safe_output(output)
    acquisition=json.loads((cache/'acquisition_audit.json').read_text())
    calendar=json.loads((cache/'calendar_audit.json').read_text())
    if acquisition['status']!='VALIDATED_VENDOR_HISTORY_CALENDAR_MATCH' or calendar['status']!='CALENDAR_MATCH':
        raise ValueError('Acquisition/calendar gate did not pass; no fallback allowed.')
    if acquisition['source_url']!=SOURCE or acquisition['symbol']!='^GSPC':raise ValueError('Wrong source identity.')
    if acquisition['validated_prices_sha256']!=sha(cache/'validated_prices.csv'):
        raise ValueError('Validated prices changed after acquisition.')
    if calendar['schedule_sha256']!=sha(cache/'nyse_schedule.csv'):raise ValueError('Calendar receipt changed.')
    frame=pd.read_csv(cache/'validated_prices.csv')
    check,_,_=calendar_audit(frame,acquisition['start'],acquisition['end'])
    if check['status']!='CALENDAR_MATCH':raise ValueError('Calendar replay mismatch.')
    result=v9.run(cache/'validated_prices.csv',output)
    result['calendar_verification']='NYSE_LIBRARY_CALENDAR_MATCH'
    result['acquisition_audit_sha256']=sha(cache/'acquisition_audit.json')
    result['calendar_audit_sha256']=sha(cache/'calendar_audit.json')
    result['scope']='Expanded vendor cash-index history; frozen V9, not a live or independently validated forecasting model.'
    result['live_forecast']=None;result['status']='NO_CONFIRMED_EDGE'
    (output/'sequential_v9_audit.json').write_text(json.dumps(result,indent=2,allow_nan=False))
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--mode',choices=['calendar','acquire','study'],required=True)
    p.add_argument('--prices',type=Path);p.add_argument('--cache',type=Path)
    p.add_argument('--start',default=START);p.add_argument('--end');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.mode=='acquire':r=acquire(a.output,a.start,a.end)
    elif a.mode=='study':
        if not a.cache:p.error('--cache required')
        r=study(a.cache,a.output)
    else:
        if not a.prices:p.error('--prices required')
        frame=pd.read_csv(a.prices);good=frame[frame.SP500.notna()]
        r=write_calendar(safe_output(a.output),frame,str(good.observation_date.min()),str(good.observation_date.max()))
    print(json.dumps({k:v for k,v in r.items() if k not in ['excluded_rows','comparisons']},indent=2,allow_nan=False))


if __name__=='__main__':main()
