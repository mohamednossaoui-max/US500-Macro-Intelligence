import json
from pathlib import Path
import pandas as pd
P=Path(__file__).resolve().parents[1]/'public_data'

def test_contextual_layers_visible_but_not_scored():
    r=pd.read_csv(P/'decision_engine_evidence_registry_v2.csv')
    c=r[r['decision_role'].eq('CONTEXTUAL')]
    assert {'Event / News','Corporate Earnings'} <= set(c['source'])
    assert not c['included_in_state'].astype(bool).any()

def test_event_news_structured_and_contextual():
    d=pd.read_csv(P/'event_news_research_v2.csv')
    assert {'event_class','research_relevance','is_duplicate'} <= set(d.columns)
    assert d['decision_role'].str.upper().eq('CONTEXTUAL').all()

def test_event_study_reliability_is_explicit():
    d=pd.read_csv(P/'historical_event_study_sample_adequacy_v2.csv')
    assert {'reliability_tier','eligible_for_descriptive_summary','eligible_for_inference'} <= set(d.columns)
    assert not d['eligible_for_inference'].astype(bool).any()

def test_earnings_quality_boundary():
    q=json.loads((P/'earnings_quality_summary_v3.json').read_text())
    assert q['decision_role']=='CONTEXTUAL'
    assert q['included_in_decision_state'] is False

def test_hardening_validation_passes():
    q=json.loads((P/'final_remaining_layers_hardening_v1.json').read_text())
    assert q['status']=='PASS'
    assert q['decision_semantics_changed'] is False

def test_recurring_fomc_statements_are_not_false_duplicates():
    d=pd.read_csv(P/'event_news_research_v2.csv')
    x=d[d['title'].str.lower().eq('federal reserve issues fomc statement')]
    assert len(x) >= 2
    assert not x['is_duplicate'].astype(bool).any()
    assert x['dedup_key'].nunique()==len(x)
