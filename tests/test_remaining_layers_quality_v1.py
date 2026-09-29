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

def test_event_news_freshness_is_context_relative_not_hardcoded_current():
    df=pd.read_csv(PUB/'event_news_research_v2.csv')
    assert 'age_days' in df.columns
    assert (df['freshness_status']=='STALE').any()
    assert not df['freshness_status'].eq('CURRENT').all()

def test_earnings_reaction_horizons_have_separate_availability():
    df=pd.read_csv(PUB/'earnings_market_reaction_v3.csv')
    assert 'event_available_at' in df.columns
    for h in ['1d','3d','5d','20d','1m','3m']:
        c=f'reaction_available_at_{h}'
        assert c in df.columns
        event=pd.to_datetime(df['event_available_at'],errors='coerce')
        reaction=pd.to_datetime(df[c],errors='coerce')
        m=event.notna() & reaction.notna()
        assert (reaction[m] > event[m]).all()

def test_contextual_layers_never_promoted_to_core():
    r=pd.read_csv(PUB/'decision_engine_evidence_registry_v2.csv')
    x=r[r['source'].isin(['Event / News','Corporate Earnings'])]
    assert set(x['decision_role'])=={'CONTEXTUAL'}
    assert not x['included_in_state'].astype(bool).any()
