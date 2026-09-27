import pandas as pd
from .common import row

def build(p):
 d=pd.read_csv(p/'liquidity_intelligence_research_v1.csv'); x=d.iloc[-1]; out=[]
 specs=[('FED_TOTAL_ASSETS','SUPPORTIVE_IF_RISING'),('TREASURY_GENERAL_ACCOUNT','RESTRICTIVE_IF_RISING'),('ON_RRP','RESTRICTIVE_IF_RISING'),('RESERVE_BALANCES','SUPPORTIVE_IF_RISING'),('EFFR','CONTEXT'),('SOFR','CONTEXT')]
 for ind,interp in specs:
  out.append(row('LIQUIDITY','LIQUIDITY',ind,direction=interp,value=x.get(ind,''),observation_date=x.get(ind+'_observation_date',''),available_at=x.asof_date,as_of_date=x.asof_date,source_name='Published liquidity research',source_artifact='liquidity_intelligence_research_v1.csv',pit_status='PIT_SAFE' if x.point_in_time_safe else 'NOT_PIT_SAFE',expected_frequency='WEEKLY' if ind not in {'EFFR','SOFR','ON_RRP'} else 'DAILY',limitations='Exact publication timestamp not represented'))
 return out
