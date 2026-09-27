import pandas as pd
from .common import row

def build(p):
 out=[]
 for f,mod,freq in [('aaii_sentiment_research_v1.csv','AAII','WEEKLY'),('vix_sentiment_research_v1.csv','VIX','DAILY')]:
  d=pd.read_csv(p/f); x=d.iloc[-1]; out.append(row('SENTIMENT_'+mod,'SENTIMENT',mod,state=x.research_regime,observation_date=x.observation_date,available_at=x.availability_date,as_of_date=max(str(x.availability_date),str(x.observation_date)),source_name=x.get('source',''),source_artifact=f,pit_status='PIT_SAFE' if x.point_in_time_safe else 'NOT_PIT_SAFE',expected_frequency=freq,limitations=x.get('availability_semantics','')))
 d=pd.read_csv(p/'cot_positioning_research_v1.csv'); x=d.iloc[-1]
 for ind,col in [('COT Asset Manager','asset_manager_research_regime'),('COT Leveraged Money','leveraged_money_research_regime')]:
  out.append(row('SENTIMENT_COT','SENTIMENT',ind,state=x[col],observation_date=x.observation_date,available_at=x.availability_date,as_of_date=x.availability_date,source_name='CFTC COT',source_artifact='cot_positioning_research_v1.csv',pit_status='PIT_SAFE' if x.point_in_time_safe else 'NOT_PIT_SAFE',expected_frequency='WEEKLY'))
 return out
