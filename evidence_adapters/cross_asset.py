import pandas as pd
from .common import row

def build(p):
 d=pd.read_csv(p/'cross_asset_research_v1.csv'); x=d.iloc[-1]; out=[]
 for a in ['SP500','NASDAQ','GOLD','DXY','VIX','US10Y','WTI','BITCOIN']:
  val=x.get(a); avail=not pd.isna(val)
  out.append(row('CROSS_ASSET','CROSS_ASSET',a,value='' if not avail else val,observation_date=x.observation_date,available_at=x.availability_date,as_of_date=x.availability_date,source_name='Yahoo Finance via yfinance',source_artifact='cross_asset_research_v1.csv',pit_status='PIT_LIMITED',availability_status='AVAILABLE' if avail else 'UNAVAILABLE',expected_frequency='DAILY',limitations='Current artifact uses observation_date + 1 calendar day; session-aware availability is not yet represented'))
 return out
