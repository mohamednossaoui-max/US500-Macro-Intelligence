import pandas as pd
from .common import row

def build(p):
 d=pd.read_csv(p/'market_breadth_analysis_v1.csv'); x=d.iloc[-1]
 return [row('MARKET_BREADTH','BREADTH','Breadth State',state=x.breadth_research_state,value=x.coverage_pct,unit='coverage %',observation_date=x.asof_date,available_at=x.asof_date,as_of_date=x.asof_date,source_name=x.membership_source,source_artifact='market_breadth_analysis_v1.csv',pit_status='PIT_LIMITED' if not bool(x.pit_perfect) else 'PIT_SAFE',expected_frequency='DAILY',limitations='Historical constituent membership is a free-public reconstruction; pit_perfect=false')]
