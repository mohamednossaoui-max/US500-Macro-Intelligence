import json
from .common import row

def build(p):
 x=json.load(open(p/'fed_intelligence_output_v1.json')); asof=x.get('as_of_date',''); out=[]
 for key,label in [('statement','FOMC Statement'),('chair_press','Press Conference'),('minutes','FOMC Minutes')]:
  v=x.get(key) or {}; available=bool(v.get('available'))
  out.append(row('FED','FED',label,state=v.get('tone',''),observation_date=x.get('latest_fomc',''),release_date=x.get('latest_fomc','') if available else '',available_at=x.get('latest_fomc','') if available else '',as_of_date=asof,source_name='Federal Reserve',source_artifact='fed_intelligence_output_v1.json',pit_status='PIT_SAFE' if available else 'UNKNOWN',availability_status='AVAILABLE' if available else 'UNAVAILABLE',expected_frequency='EVENT_DRIVEN',limitations='' if available else 'NOT_YET_PUBLISHED_OR_UNAVAILABLE'))
 return out
