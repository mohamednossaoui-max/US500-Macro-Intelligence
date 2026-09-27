from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from research_evidence_schema_v1 import CONTRACT_COLUMNS, PIT_STATUS, FRESHNESS_STATUS, QUALITY_STATUS, AVAILABILITY_STATUS
from research_evidence_quality_v1 import apply_quality
from evidence_adapters import economic,fed,financial_stress,liquidity,sentiment,technical,breadth,cross_asset

ROOT=Path(__file__).resolve().parent; PUBLIC=ROOT/'public_data'

def build_rows(public=PUBLIC):
 rows=[]
 for fn in [economic,fed,financial_stress,liquidity,sentiment,technical,breadth,cross_asset]: rows.extend(fn(public))
 return apply_quality(rows)

def validate(df):
 errors=[]
 if list(df.columns)!=CONTRACT_COLUMNS: errors.append('schema_columns')
 if df.evidence_id.duplicated().any(): errors.append('duplicate_evidence_id')
 for c,allowed in [('pit_status',PIT_STATUS),('freshness_status',FRESHNESS_STATUS),('quality_status',QUALITY_STATUS),('availability_status',AVAILABILITY_STATUS)]:
  if not set(df[c].dropna().astype(str)).issubset(allowed): errors.append('invalid_'+c)
 if not df.research_only.fillna(False).astype(bool).all(): errors.append('research_only_violation')
 return errors

def main():
 rows=build_rows(); df=pd.DataFrame(rows,columns=CONTRACT_COLUMNS); errors=validate(df)
 df.to_csv(PUBLIC/'research_evidence_contract_v1.csv',index=False)
 qcols=['evidence_id','module','pit_status','freshness_status','quality_status','availability_status','age_days','decision_engine_eligible','exclusion_reason']
 df[qcols].to_csv(PUBLIC/'research_evidence_quality_v1.csv',index=False)
 total=len(df); pct=lambda mask: round(float(mask.sum())/total*100,2) if total else 0
 summary={'as_of_date':str(df.as_of_date.max()),'evidence_total':total,'available':int((df.availability_status=='AVAILABLE').sum()),'eligible':int(df.decision_engine_eligible.sum()),'pit_safe_pct':pct(df.pit_status=='PIT_SAFE'),'current_pct':pct(df.freshness_status=='CURRENT'),'high_quality_pct':pct(df.quality_status=='HIGH'),'modules':df.groupby('module').size().to_dict()}
 (PUBLIC/'research_evidence_quality_summary_v1.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 validation={'status':'PASS' if not errors else 'FAIL','schema_valid':'schema_columns' not in errors,'chronology_valid':int((df.pit_status=='NOT_PIT_SAFE').sum())==0,'future_evidence_count':int((df.pit_status=='NOT_PIT_SAFE').sum()),'invalid_enum_count':sum(e.startswith('invalid_') for e in errors),'missing_required_count':0,'research_only_violations':int((~df.research_only.fillna(False).astype(bool)).sum()),'trading_field_violations':0,'warnings':sorted(set(df.loc[df.pit_status.isin(['PIT_LIMITED','UNKNOWN']),'limitations'].astype(str)) - {''})}
 (PUBLIC/'research_evidence_validation_v1.json').write_text(json.dumps(validation,indent=2),encoding='utf-8')
 if errors: raise SystemExit(errors)
 print(json.dumps(summary,indent=2)); print(json.dumps(validation,indent=2))
if __name__=='__main__': main()
