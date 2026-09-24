#!/usr/bin/env python3
"""US500 MACRO INTELLIGENCE — DECISION ENGINE V1
Research-only. No trade execution. No BUY/SELL signals.
"""
from __future__ import annotations
import argparse, csv, glob, hashlib, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

STATES={"BULLISH_CONTEXT","BEARISH_CONTEXT","NEUTRAL_CONTEXT","CONFLICTED","INSUFFICIENT_DATA"}
TRUE_VALUES={"1","true","yes","y","pass","passed"}
FALSE_VALUES={"0","false","no","n","fail","failed"}

def parse_args():
    p=argparse.ArgumentParser(); p.add_argument("--artifacts-dir",default="artifacts"); p.add_argument("--output",default="decision_engine_research_v1.csv"); p.add_argument("--summary-output",default="decision_engine_summary_v1.csv"); return p.parse_args()

def nk(v): return str(v or "").strip().lower().replace("-","_").replace(" ","_")
def truthy(v):
    if v is None:return None
    s=str(v).strip().lower()
    if s in TRUE_VALUES:return True
    if s in FALSE_VALUES:return False
    return None

def read_csv(path):
    with open(path,"r",encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def date_field(r):
    for k in ("asof_date","date","context_date","event_date","reported_date","observation_date"):
        if r.get(k):return r[k]
    return ""

def discover(root):
    out=set()
    for p in glob.glob(os.path.join(root,"**","*.csv"),recursive=True):
        rp=os.path.realpath(p)
        if os.path.basename(rp).startswith("decision_engine_") or "/.git/" in rp:continue
        out.add(rp)
    return sorted(out)

def extract(r):
    low={nk(k):v for k,v in r.items()}; aliases={
        "economic_regime":["economic_regime","growth_regime","economic_context"],
        "fed_regime":["fed_regime","fed_context","monetary_regime"],
        "financial_stress_regime":["financial_stress_regime","research_regime","stress_regime"],
        "sentiment_regime":["sentiment_regime","sentiment_context"],
        "technical_regime":["technical_regime","technical_context"]}
    x={}
    for target,keys in aliases.items():
        for k in keys:
            if nk(k) in low and str(low[nk(k)]).strip():x[target]=low[nk(k)];break
    for k in ("point_in_time_safe","data_quality","availability_date"):
        if nk(k) in low:x[k]=low[nk(k)]
    return x

def locate(paths):
    keys=["economic_regime","fed_regime","financial_stress_regime","sentiment_regime","technical_regime"]
    candidates={k:[] for k in keys}
    for path in paths:
        try: rows=read_csv(path)
        except Exception: continue
        for r in rows:
            x=extract(r)
            for k in keys:
                if k in x:candidates[k].append((date_field(r),path,r,x))
    result={}
    for k,items in candidates.items():
        if not items:continue
        items.sort(key=lambda x:(x[0],x[1])); d,path,r,x=items[-1]
        result[k]={"value":x.get(k,""),"source_file":path,"source_date":d,"point_in_time_safe":x.get("point_in_time_safe",""),"data_quality":x.get("data_quality","")}
    return result

def score(name,value):
    v=nk(value); n=nk(name)
    if not v:return None
    if "economic" in n:
        if any(x in v for x in ("expansion","strong","positive","improving")):return 1
        if any(x in v for x in ("contraction","weak","negative","deteriorating","recession")):return -1
    if "fed" in n or "monetary" in n:
        if any(x in v for x in ("dovish","accommodative","easing")):return 1
        if any(x in v for x in ("hawkish","restrictive","tightening")):return -1
    if "stress" in n or "financial" in n:
        if any(x in v for x in ("low","normal","calm")):return 1
        if any(x in v for x in ("elevated","high","extreme","stress")):return -1
    if "sentiment" in n:
        if any(x in v for x in ("positive","bullish","optimistic","risk_on")):return 1
        if any(x in v for x in ("negative","bearish","pessimistic","risk_off")):return -1
    if "technical" in n:
        if any(x in v for x in ("bullish","uptrend","positive","strong")):return 1
        if any(x in v for x in ("bearish","downtrend","negative","weak")):return -1
    return 0

def build(layers):
    keys=["economic_regime","fed_regime","financial_stress_regime","sentiment_regime","technical_regime"]
    values={k:layers.get(k,{}).get("value","") for k in keys}
    evidence={k.replace("_regime","_evidence"):layers.get(k,{}).get("source_file","") for k in keys}
    dates=[layers.get(k,{}).get("source_date","") for k in keys if layers.get(k,{}).get("source_date","")]
    scores={k:score(k,values[k]) for k in keys}; scores={k:v for k,v in scores.items() if v is not None}
    pos=sum(v>0 for v in scores.values()); neg=sum(v<0 for v in scores.values()); neu=sum(v==0 for v in scores.values()); missing=5-len(scores)
    if len(scores)<2: state="INSUFFICIENT_DATA"
    elif pos>=3 and neg==0: state="BULLISH_CONTEXT"
    elif neg>=3 and pos==0: state="BEARISH_CONTEXT"
    elif pos>0 and neg>0: state="CONFLICTED"
    else: state="NEUTRAL_CONTEXT"
    confidence=round(max(pos,neg,neu)/len(scores),4) if scores else 0.0
    safe=[truthy(layers[k].get("point_in_time_safe")) for k in keys if layers.get(k)]
    safe=[x for x in safe if x is not None]
    pit="PASS" if safe and all(safe) else ("REVIEW" if not safe else "FAIL")
    quality="INSUFFICIENT" if missing>=3 else ("REVIEW" if missing else "PASS")
    rec={"asof_date":max(dates) if dates else datetime.now(timezone.utc).date().isoformat(),**values,**evidence,
         "evidence_count":len(scores),"supportive_count":pos,"contradictory_count":neg,"neutral_count":neu,"missing_count":missing,
         "decision_state":state,"decision_confidence":confidence,"conflict_flag":"YES" if state=="CONFLICTED" else "NO",
         "data_quality":quality,"point_in_time_safe":pit,"research_only":"TRUE"}
    rec["record_id"]=hashlib.sha256(json.dumps(rec,sort_keys=True).encode()).hexdigest()[:16]
    return rec

def write(path,rows):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    with open(path,"w",encoding="utf-8",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    a=parse_args(); paths=discover(a.artifacts_dir); rec=build(locate(paths)); write(a.output,[rec])
    summary={"run_timestamp_utc":datetime.now(timezone.utc).isoformat(),"decision_state":rec["decision_state"],"decision_confidence":rec["decision_confidence"],"evidence_count":rec["evidence_count"],"supportive_count":rec["supportive_count"],"contradictory_count":rec["contradictory_count"],"missing_count":rec["missing_count"],"point_in_time_safe":rec["point_in_time_safe"],"data_quality":rec["data_quality"],"research_only":"TRUE","source_csv_count":len(paths)}
    write(a.summary_output,[summary]); print("DECISION ENGINE V1"); print(json.dumps(summary,indent=2)); return 0
if __name__=="__main__":raise SystemExit(main())
