#!/usr/bin/env python3
"""US500 Macro Intelligence — Financial Stress Data Foundation v1.
Research-only. No trading signals and no Decision Engine integration.
"""
import csv, hashlib, math, sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path

INPUT=Path("financial_stress_records_input_v1.csv")
EVENTS=Path("financial_stress_events_v1.csv")
QUALITY=Path("financial_stress_data_quality_v1.csv")

REQ=["indicator","observation_date","availability_date","actual","unit","frequency",
     "source","source_url","vintage","revision_flag","point_in_time_safe",
     "availability_semantics"]
RULES={
 "VIX":({"DAILY"},{"INDEX_LEVEL"},"Cboe","cboe.com"),
 "NFCI":({"WEEKLY"},{"INDEX_LEVEL"},"Chicago Fed","chicagofed.org"),
 "ANFCI":({"WEEKLY"},{"INDEX_LEVEL"},"Chicago Fed","chicagofed.org"),
 "TREASURY_2Y":({"DAILY"},{"PERCENT"},"Federal Reserve H.15","federalreserve.gov"),
 "TREASURY_10Y":({"DAILY"},{"PERCENT"},"Federal Reserve H.15","federalreserve.gov"),
 "CURVE_10Y_2Y":({"DAILY"},{"PERCENTAGE_POINTS"},"Federal Reserve H.15","federalreserve.gov"),
}

@dataclass
class Q:
    record_id:str; indicator:str; observation_date:str; availability_date:str
    point_in_time_safe:bool; quality_status:str; quality_issues:str

def rid(r):
    s="|".join([r["indicator"],r["observation_date"],r["availability_date"],
                r["actual"],r["unit"],r["source"],r["vintage"]])
    return hashlib.sha256(s.encode()).hexdigest()

def boolean(v):
    v=v.strip().lower()
    if v in ("true","1","yes"): return True
    if v in ("false","0","no"): return False
    raise ValueError(v)

def finite(v):
    try: return math.isfinite(float(v))
    except: return False

def validate(r):
    issues=[]
    ind=r["indicator"].strip()
    try: od=date.fromisoformat(r["observation_date"].strip())
    except: od=None; issues.append("INVALID_OBSERVATION_DATE")
    try: ad=date.fromisoformat(r["availability_date"].strip())
    except: ad=None; issues.append("INVALID_AVAILABILITY_DATE")
    if ind not in RULES: issues.append("UNSUPPORTED_INDICATOR")
    else:
        freq,unit,src,domain=RULES[ind]
        if r["frequency"].strip() not in freq: issues.append("INVALID_FREQUENCY")
        if r["unit"].strip() not in unit: issues.append("INVALID_UNIT")
        if src not in r["source"]: issues.append("SOURCE_NAME_MISMATCH")
        if domain not in r["source_url"]: issues.append("SOURCE_DOMAIN_MISMATCH")
    if not finite(r["actual"]): issues.append("INVALID_ACTUAL")
    if not r["source_url"].startswith("https://"): issues.append("INVALID_SOURCE_URL")
    try: pit=boolean(r["point_in_time_safe"])
    except: pit=False; issues.append("INVALID_POINT_IN_TIME_FLAG")
    try: boolean(r["revision_flag"])
    except: issues.append("INVALID_REVISION_FLAG")
    if od and ad and ad<od: issues.append("AVAILABILITY_BEFORE_OBSERVATION")
    if r["availability_semantics"].strip() not in {"EOD_CLOSE","OFFICIAL_RELEASE","ARCHIVED_VINTAGE"}:
        issues.append("INVALID_AVAILABILITY_SEMANTICS")
    pit_ok=pit and bool(r["vintage"].strip()) and ad is not None and not any(
        x in issues for x in ["INVALID_OBSERVATION_DATE","INVALID_AVAILABILITY_DATE",
        "AVAILABILITY_BEFORE_OBSERVATION","INVALID_POINT_IN_TIME_FLAG",
        "INVALID_AVAILABILITY_SEMANTICS"])
    if not pit_ok and not issues: issues.append("PIT_DECLARATION_NOT_SATISFIED")
    return Q(rid(r),ind,r["observation_date"].strip(),r["availability_date"].strip(),
             pit_ok,"PASS" if not issues and pit_ok else "FAIL",";".join(issues))

def write(path, rows):
    rows=list(rows)
    if not rows: path.write_text("",encoding="utf-8"); return
    with path.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

def main():
    if not INPUT.exists(): raise FileNotFoundError(INPUT)
    with INPUT.open(encoding="utf-8-sig",newline="") as f:
        rd=csv.DictReader(f)
        missing=[x for x in REQ if x not in (rd.fieldnames or [])]
        if missing: raise ValueError("Missing columns: "+str(missing))
        rows=list(rd)
    ids=[rid(r) for r in rows]
    if len(ids)!=len(set(ids)): raise ValueError("Duplicate logical observations")
    qs=[validate(r) for r in rows]
    out=[]
    for r,q in zip(rows,qs):
        x=dict(r); x["record_id"]=q.record_id
        x["point_in_time_safe"]=str(q.point_in_time_safe).lower(); out.append(x)
    write(EVENTS,out); write(QUALITY,[asdict(q) for q in qs])
    print("Financial Stress Data Foundation v1")
    print("Research-only: TRUE")
    print("Decision Engine integration: FALSE")
    print(f"Input records: {len(rows)}")
    print(f"Valid records: {sum(q.quality_status=='PASS' for q in qs)}")
    print(f"PIT safe: {sum(q.point_in_time_safe for q in qs)}/{len(qs)}")
    if not rows:
        print("SCHEMA GATE: PASS")
        print("DATA GATE: DEFERRED — no observations ingested yet.")
        return 0
    if any(q.quality_status!="PASS" for q in qs):
        print("DATA QUALITY GATE: FAIL"); return 1
    print("DATA QUALITY GATE: PASS"); return 0

if __name__=="__main__": sys.exit(main())
