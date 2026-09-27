import pandas as pd
from .common import row

def build(p):
 d=pd.read_csv(p/'financial_stress_research_v1.csv'); x=d.iloc[-1]; return [row('FINANCIAL_STRESS','STRESS','Composite Stress',state=x.research_regime,value=x.composite_stress_score,unit='z-score composite',observation_date=x.asof_date,available_at=x.asof_date,as_of_date=x.asof_date,source_name='Published stress research',source_artifact='financial_stress_research_v1.csv',pit_status='PIT_SAFE' if x.point_in_time_safe else 'NOT_PIT_SAFE',expected_frequency='DAILY')]
