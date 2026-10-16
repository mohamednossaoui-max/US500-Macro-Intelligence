from __future__ import annotations
import hashlib

def row(module, dimension, indicator, *, state="", direction="", value="", unit="", observation_date="", release_date="", available_at="", as_of_date="", source_name="", source_type="PUBLISHED_ARTIFACT", source_artifact="", pit_status="UNKNOWN", availability_status="AVAILABLE", expected_frequency="", research_only=True, limitations=""):
    key="|".join(map(str,[module,dimension,indicator,observation_date,available_at,as_of_date]))
    return {"evidence_id": hashlib.sha256(key.encode()).hexdigest()[:24], "module":module,"dimension":dimension,"indicator":indicator,"state":state,"direction":direction,"value":value,"unit":unit,"observation_date":observation_date,"release_date":release_date,"available_at":available_at,"as_of_date":as_of_date,"source_name":source_name,"source_type":source_type,"source_artifact":source_artifact,"pit_status":pit_status,"freshness_status":"UNKNOWN","quality_status":"INSUFFICIENT","availability_status":availability_status,"age_days":"","expected_frequency":expected_frequency,"expected_next_release":"","included_in_synthesis":False,"decision_engine_eligible":False,"exclusion_reason":"","research_only":as_bool(research_only),"limitations":limitations}


def evaluation_date(public, fallback=""):
    """Use the consumer snapshot clock; never let an old source date itself."""
    import json
    import pandas as pd
    dates = []
    for name, column in [("research_context_summary_v1.csv", "context_date"), ("macro_context_v1.csv", "context_date")]:
        path = public / name
        if path.exists():
            d = pd.read_csv(path)
            if column in d: dates.extend(pd.to_datetime(d[column], errors="coerce").dropna().tolist())
    if dates: return max(dates).date().isoformat()
    return fallback


def as_bool(value):
    """Unknown/NaN and the string False never count as verified evidence."""
    return str(value).strip().lower() in {'true','1','1.0'}
