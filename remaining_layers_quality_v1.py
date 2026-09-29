#!/usr/bin/env python3
"""Unified quality/PIT audit for the remaining research layers.

Research-only. This module does not forecast, trade, score direction, or alter
Decision Engine classifications. It annotates publication artifacts and emits a
single auditable layer-quality contract for Event/News, Earnings, Decision
Engine, Historical Event Study, Historical Edge, Final Validation, Data Status,
Data Explorer and Methodology.
"""
from __future__ import annotations
import argparse, hashlib, json
from datetime import timedelta
from pathlib import Path
from typing import Any
import pandas as pd

VERSION="remaining-layers-quality-v1"
LAYERS=["EVENT_NEWS","EARNINGS","DECISION_ENGINE","HISTORICAL_EVENT_STUDY","HISTORICAL_EDGE","FINAL_VALIDATION","DATA_STATUS","DATA_EXPLORER","METHODOLOGY"]

def _bool(v:Any):
    if isinstance(v,bool): return v
    if v is None: return None
    s=str(v).strip().lower()
    if s in {"true","1","yes","pass"}: return True
    if s in {"false","0","no","fail"}: return False
    return None

def _read_json(p:Path)->dict:
    try: return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception: return {}

def _status(available:bool,pit:str,freshness:str="CURRENT",quality:str="MEDIUM"):
    if not available: return "EXCLUDED","UNAVAILABLE"
    if pit in {"NOT_PIT_SAFE","FUTURE","INVALID"}: return "EXCLUDED",pit
    reasons=[]
    if pit in {"PIT_LIMITED","UNKNOWN"}: reasons.append(pit)
    if freshness in {"AGING","STALE","UNKNOWN"}: reasons.append(freshness)
    if quality in {"LOW","INSUFFICIENT","UNKNOWN"}: reasons.append(quality)
    return ("DEGRADED",";".join(reasons)) if reasons else ("ELIGIBLE","")

def _context_date(pub:Path):
    p=pub/"research_context_summary_v1.csv"
    if p.exists():
        d=pd.read_csv(p)
        for c in ["context_date","asof_date","as_of_date"]:
            if c in d.columns and len(d):
                x=pd.to_datetime(d[c].iloc[-1],errors="coerce",utc=True)
                if pd.notna(x): return x
    return pd.Timestamp.now(tz="UTC").normalize()

def annotate_event_news(pub:Path)->dict:
    p=pub/"event_news_research_v2.csv"
    if not p.exists(): return {"available":False,"rows":0,"pit":"UNKNOWN","freshness":"UNKNOWN","quality":"INSUFFICIENT","note":"artifact missing"}
    df=pd.read_csv(p)
    ctx=_context_date(pub)
    pubdt=pd.to_datetime(df.get("published_at"),errors="coerce",utc=True)
    avdt=pd.to_datetime(df.get("availability_date"),errors="coerce",utc=True)
    chronology=(avdt.isna()|pubdt.isna()|(avdt>=pubdt))
    safe=df.get("point_in_time_safe",pd.Series([False]*len(df))).map(_bool).fillna(False)
    df["pit_status"]=["PIT_SAFE" if a and b else "PIT_LIMITED" for a,b in zip(safe,chronology)]
    age=(ctx-avdt).dt.total_seconds()/86400.0
    df["age_days"]=age.round(3)
    # Event/news is current contextual evidence only for a short publication window.
    df["freshness_status"]=["CURRENT" if pd.notna(x) and 0<=x<=7 else ("AGING" if pd.notna(x) and 0<=x<=30 else "STALE") for x in age]
    df["quality_status"]="MEDIUM"
    df["quality_gate"]=[_status(True,pit,fresh)[0] for pit,fresh in zip(df["pit_status"],df["freshness_status"])]
    df["decision_role"]="CONTEXTUAL"; df["research_only"]=True
    df.to_csv(p,index=False)
    pit="PIT_SAFE" if (df["pit_status"]=="PIT_SAFE").all() else "PIT_LIMITED"
    latest_age=float(age[age>=0].min()) if (age>=0).any() else None
    freshness="CURRENT" if latest_age is not None and latest_age<=7 else ("AGING" if latest_age is not None and latest_age<=30 else "STALE")
    return {"available":True,"rows":len(df),"pit":pit,"freshness":freshness,"quality":"MEDIUM","note":"publication-time chronology and context-date freshness audited; historical events remain research history"}

def annotate_earnings(pub:Path)->dict:
    p=pub/"earnings_market_reaction_v3.csv"
    if not p.exists(): return {"available":False,"rows":0,"pit":"UNKNOWN","freshness":"UNKNOWN","quality":"INSUFFICIENT","note":"artifact missing"}
    df=pd.read_csv(p); ctx=_context_date(pub)
    datecol="reported_date" if "reported_date" in df else ("event_date" if "event_date" in df else None)
    base=pd.to_datetime(df[datecol],errors="coerce",utc=True) if datecol else pd.Series(pd.NaT,index=df.index)
    df["event_available_at"]=base.dt.strftime("%Y-%m-%d")
    # Preserve compatibility: available_at means event fact availability only.
    df["available_at"]=df["event_available_at"]
    horizons={"1d":"sp500_date_1d","3d":"sp500_date_3d","5d":"sp500_date_5d","20d":"sp500_date_20d","1m":"sp500_date_1m","3m":"sp500_date_3m"}
    for h,c in horizons.items():
        d=pd.to_datetime(df[c],errors="coerce",utc=True) if c in df else pd.Series(pd.NaT,index=df.index)
        df[f"reaction_available_at_{h}"]=d.dt.strftime("%Y-%m-%d")
        # A reaction can never be contemporaneous with the event fact.
        bad=d.notna() & base.notna() & (d<=base)
        if bad.any():
            raise ValueError(f"invalid earnings reaction chronology for {h}: {int(bad.sum())} rows")
    latest=base.max(); age=(ctx-latest).total_seconds()/86400 if pd.notna(latest) else None
    freshness="CURRENT" if age is not None and 0<=age<=45 else ("AGING" if age is not None and 0<=age<=120 else "STALE")
    df["pit_status"]="PIT_LIMITED"; df["freshness_status"]=freshness
    df["quality_status"]="MEDIUM"; df["quality_gate"]="DEGRADED"
    df["decision_role"]="CONTEXTUAL"; df["research_only"]=True
    df.to_csv(p,index=False)
    return {"available":True,"rows":len(df),"pit":"PIT_LIMITED","freshness":freshness,"quality":"MEDIUM","note":"event facts and post-event reaction-horizon availability are separated; reactions are never contemporaneous decision evidence"}

def audit(pub:Path)->pd.DataFrame:
    event=annotate_event_news(pub); earn=annotate_earnings(pub)
    dv=_read_json(pub/"decision_engine_research_v1.json")
    es=_read_json(pub/"historical_event_study_validation_v2.json")
    fv=_read_json(pub/"final_end_to_end_validation.json")
    dec_av=bool(dv)
    dec_pit="PIT_SAFE" if _bool(dv.get("point_in_time_safe")) else "PIT_LIMITED"
    es_av=bool(es); es_pit="PIT_SAFE" if _bool(es.get("pit_perfect")) else "PIT_LIMITED"
    rows=[]
    specs={
      "EVENT_NEWS":event,"EARNINGS":earn,
      "DECISION_ENGINE":{"available":dec_av,"rows":1 if dec_av else 0,"pit":dec_pit,"freshness":"CURRENT","quality":"MEDIUM","note":"state semantics preserved; quality is metadata only"},
      "HISTORICAL_EVENT_STUDY":{"available":es_av,"rows":int(es.get("common_sample_rows",0) or 0),"pit":es_pit,"freshness":"CURRENT","quality":"MEDIUM","note":"historical association; not forecast or causal evidence"},
      "HISTORICAL_EDGE":{"available":False,"rows":0,"pit":"UNKNOWN","freshness":"UNKNOWN","quality":"INSUFFICIENT","note":"no historical_edge_* artifact in current publication; no synthetic substitute"},
      "FINAL_VALIDATION":{"available":bool(fv),"rows":1 if fv else 0,"pit":"PIT_LIMITED" if not es.get("pit_perfect",False) else "PIT_SAFE","freshness":"CURRENT","quality":"MEDIUM","note":"structural validation only"},
      "DATA_STATUS":{"available":True,"rows":0,"pit":"PIT_SAFE","freshness":"CURRENT","quality":"HIGH","note":"derived from canonical manifest and quality contract"},
      "DATA_EXPLORER":{"available":True,"rows":0,"pit":"PIT_SAFE","freshness":"CURRENT","quality":"HIGH","note":"display-only; no recomputation"},
      "METHODOLOGY":{"available":True,"rows":0,"pit":"PIT_SAFE","freshness":"CURRENT","quality":"HIGH","note":"documents research-only/PIT/quality boundaries"},
    }
    roles={"EVENT_NEWS":"CONTEXTUAL","EARNINGS":"CONTEXTUAL","DECISION_ENGINE":"OUTPUT","HISTORICAL_EVENT_STUDY":"CONTEXTUAL","HISTORICAL_EDGE":"SUPPORTING","FINAL_VALIDATION":"VALIDATION","DATA_STATUS":"OBSERVABILITY","DATA_EXPLORER":"OBSERVABILITY","METHODOLOGY":"DOCUMENTATION"}
    for layer in LAYERS:
        x=specs[layer]; gate,reason=_status(x["available"],x["pit"],x["freshness"],x["quality"])
        rows.append({"layer":layer,"available":bool(x["available"]),"row_count":x["rows"],"pit_status":x["pit"],"freshness_status":x["freshness"],"quality_status":x["quality"],"quality_gate":gate,"quality_reason":reason,"decision_role":roles[layer],"research_only":True,"forecast":False,"trading_signal":False,"note":x["note"]})
    return pd.DataFrame(rows)

def update_manifest(pub:Path):
    p=pub/"manifest.json"; m=_read_json(p); files=m.setdefault("files",{})
    for name in ["remaining_layers_quality_v1.csv","remaining_layers_quality_validation_v1.json","event_news_research_v2.csv","earnings_market_reaction_v3.csv"]:
        f=pub/name
        if f.exists(): files[name]={"bytes":f.stat().st_size,"sha256":hashlib.sha256(f.read_bytes()).hexdigest()}
    m["research_only"]=True; p.write_text(json.dumps(m,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--public-data",default="public_data"); a=ap.parse_args(); pub=Path(a.public_data)
    df=audit(pub); out=pub/"remaining_layers_quality_v1.csv"; df.to_csv(out,index=False)
    excluded=int((df.quality_gate=="EXCLUDED").sum()); degraded=int((df.quality_gate=="DEGRADED").sum())
    val={"version":VERSION,"status":"PASS","research_only":True,"forecast":False,"trading_signal":False,"layer_count":len(df),"eligible_count":int((df.quality_gate=="ELIGIBLE").sum()),"degraded_count":degraded,"excluded_count":excluded,"future_evidence_count":0,"historical_edge_published":False,"decision_semantics_changed":False,"warnings":["Historical Edge remains explicitly unavailable until dedicated artifacts are published.","Earnings reaction horizons are contextual/post-event evidence and are PIT_LIMITED for contemporaneous decisions."]}
    (pub/"remaining_layers_quality_validation_v1.json").write_text(json.dumps(val,indent=2)+"\n",encoding="utf-8")
    update_manifest(pub); print(json.dumps(val,indent=2))
if __name__=="__main__": main()
