#!/usr/bin/env python3
"""Decision Engine V1 research-only validator."""
import argparse,csv,os
from datetime import datetime
from pathlib import Path
REQUIRED=["asof_date","economic_regime","fed_regime","financial_stress_regime","sentiment_regime","technical_regime","economic_evidence","fed_evidence","financial_stress_evidence","sentiment_evidence","technical_evidence","evidence_count","supportive_count","contradictory_count","neutral_count","missing_count","decision_state","decision_confidence","conflict_flag","data_quality","point_in_time_safe","research_only","record_id"]
STATES={"BULLISH_CONTEXT","BEARISH_CONTEXT","NEUTRAL_CONTEXT","CONFLICTED","INSUFFICIENT_DATA"}
def args():
 p=argparse.ArgumentParser();p.add_argument("--input",default="decision_engine_research_v1.csv");p.add_argument("--output",default="decision_engine_validation_v1.csv");p.add_argument("--summary-output",default="decision_engine_validation_v1_summary.csv");p.add_argument("--events-output",default="decision_engine_validation_v1_events.csv");return p.parse_args()
def chk(i,s,d):return {"check_id":i,"status":s,"detail":d}
def main():
 a=args();checks=[];exists=os.path.exists(a.input);checks.append(chk("INPUT_EXISTS","PASS" if exists else "FAIL",a.input))
 rows=[]
 if exists:
  with open(a.input,encoding="utf-8-sig",newline="") as f:rows=list(csv.DictReader(f))
 checks.append(chk("NON_EMPTY","PASS" if rows else "FAIL",f"rows={len(rows)}"))
 fields=list(rows[0]) if rows else []; miss=[x for x in REQUIRED if x not in fields];checks.append(chk("REQUIRED_COLUMNS","PASS" if not miss else "FAIL","All required columns present." if not miss else "Missing: "+", ".join(miss)))
 for n,r in enumerate(rows,start=2):
  st=r.get("decision_state","");checks.append(chk(f"STATE_ROW_{n}","PASS" if st in STATES else "FAIL",st))
  ro=r.get("research_only","").lower();checks.append(chk(f"RESEARCH_ONLY_ROW_{n}","PASS" if ro in {"true","1","yes"} else "FAIL",r.get("research_only","")))
  try:c=float(r.get("decision_confidence",""));ok=0<=c<=1
  except:ok=False
  checks.append(chk(f"CONFIDENCE_ROW_{n}","PASS" if ok else "FAIL",r.get("decision_confidence","")))
  try:
   e,s,co,ne,mi=[int(r.get(k,"")) for k in ("evidence_count","supportive_count","contradictory_count","neutral_count","missing_count")];ok=e>=0 and s+co+ne+mi==5 and e==s+co+ne
  except:ok=False
  checks.append(chk(f"COUNTS_ROW_{n}","PASS" if ok else "FAIL","internally consistent"))
  pit=r.get("point_in_time_safe","");checks.append(chk(f"PIT_ROW_{n}","PASS" if pit in {"PASS","REVIEW","FAIL"} else "FAIL",pit))
  forbidden={"BUY","SELL","LONG","SHORT","OPEN_LONG","OPEN_SHORT"};bad=st in forbidden;checks.append(chk(f"NO_TRADE_SIGNAL_ROW_{n}","FAIL" if bad else "PASS","no executable trading signal state"))
 Path(a.output).parent.mkdir(parents=True,exist_ok=True)
 for path,data in [(a.output,checks),(a.events_output,[x for x in checks if x["status"]!="PASS"])]:
  with open(path,"w",encoding="utf-8",newline="") as f:w=csv.DictWriter(f,fieldnames=["check_id","status","detail"]);w.writeheader();w.writerows(data)
 p=sum(x["status"]=="PASS" for x in checks);rv=sum(x["status"]=="REVIEW" for x in checks);f=sum(x["status"]=="FAIL" for x in checks);summary=[{"run_timestamp_utc":datetime.utcnow().isoformat()+"Z","total_checks":len(checks),"pass":p,"review":rv,"fail":f,"status":"PASSED" if f==0 else "FAILED","research_only":"TRUE"}]
 with open(a.summary_output,"w",encoding="utf-8",newline="") as q:w=csv.DictWriter(q,fieldnames=list(summary[0]));w.writeheader();w.writerows(summary)
 print(f"PASS={p} REVIEW={rv} FAIL={f}");return 0 if f==0 else 1
if __name__=="__main__":raise SystemExit(main())
