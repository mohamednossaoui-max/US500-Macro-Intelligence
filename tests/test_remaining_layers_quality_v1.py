import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PUB=ROOT/"public_data"

def test_quality_contract_exists_and_covers_all_layers():
    p=PUB/"remaining_layers_quality_v1.csv"; assert p.exists()
    df=pd.read_csv(p)
    expected={"EVENT_NEWS","EARNINGS","DECISION_ENGINE","HISTORICAL_EVENT_STUDY","HISTORICAL_EDGE","FINAL_VALIDATION","DATA_STATUS","DATA_EXPLORER","METHODOLOGY"}
    assert set(df.layer)==expected
    assert set(df.quality_gate)<= {"ELIGIBLE","DEGRADED","EXCLUDED"}
    assert df.research_only.astype(str).str.lower().eq("true").all()
    assert df.forecast.astype(str).str.lower().eq("false").all()
    assert df.trading_signal.astype(str).str.lower().eq("false").all()

def test_historical_edge_not_synthesized():
    df=pd.read_csv(PUB/"remaining_layers_quality_v1.csv")
    r=df[df.layer.eq("HISTORICAL_EDGE")].iloc[0]
    assert r.quality_gate=="EXCLUDED"
    assert not bool(r.available)

def test_event_news_quality_columns():
    df=pd.read_csv(PUB/"event_news_research_v2.csv")
    for c in ["pit_status","freshness_status","quality_status","quality_gate","decision_role","research_only"]: assert c in df
    assert set(df.quality_gate)<= {"ELIGIBLE","DEGRADED","EXCLUDED"}
    assert set(df.decision_role)=={"CONTEXTUAL"}

def test_earnings_reactions_are_contextual_pit_limited():
    df=pd.read_csv(PUB/"earnings_market_reaction_v3.csv")
    assert set(df.pit_status)=={"PIT_LIMITED"}
    assert set(df.quality_gate)=={"DEGRADED"}
    assert set(df.decision_role)=={"CONTEXTUAL"}

def test_validation_boundary():
    v=json.loads((PUB/"remaining_layers_quality_validation_v1.json").read_text())
    assert v["status"]=="PASS" and v["research_only"] is True
    assert v["forecast"] is False and v["trading_signal"] is False
    assert v["decision_semantics_changed"] is False
