"""Financial Stress producer and Decision Engine classification contract."""
import importlib.util
from pathlib import Path
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location('decision_stress_contract', ROOT / 'tests/decision_engine/decision_engine_v1.py')
engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(engine)


@pytest.mark.parametrize('score,regime,stance', [
    (-.5, 'LOW_RESEARCH_STRESS', 'SUPPORTIVE'),
    (0., 'ELEVATED_RESEARCH_STRESS', 'MIXED'),
    (.02, 'ELEVATED_RESEARCH_STRESS', 'MIXED'),
    (.999, 'ELEVATED_RESEARCH_STRESS', 'MIXED'),
    (1., 'HIGH_RESEARCH_STRESS', 'CONTRADICTORY'),
    (2., 'EXTREME_RESEARCH_STRESS', 'CONTRADICTORY'),
])
def test_every_producer_regime_is_visible(score, regime, stance):
    from financial_stress_analyzer_v1 import classify
    assert classify(score) == regime
    assert engine.classify_regime(regime) == stance
    evidence = []
    engine.collect_macro_evidence(pd.Series({'financial_stress_regime': regime}), evidence)
    stress = [x.to_dict() for x in evidence if x.category == 'financial_stress']
    assert len(stress) == 1
    assert stress[0]['source'] == 'Financial Stress'
    assert stress[0]['stance'] == stance and stress[0]['value'] == regime
    assert regime in stress[0]['reason']


@pytest.mark.parametrize('regime', [None, 'INSUFFICIENT_DATA', 'UNKNOWN', 'UNAVAILABLE'])
def test_missing_or_unknown_stress_is_not_neutral_evidence(regime):
    assert engine.classify_regime(regime) is None
    evidence = []
    engine.collect_macro_evidence(pd.Series({'financial_stress_regime': regime}), evidence)
    assert not any(x.category == 'financial_stress' for x in evidence)


def test_elevated_stress_rejoins_evidence_without_changing_aggregation_rule():
    row = pd.Series({'macro_available': True, 'sentiment_available': True,
        'technical_available': True, 'economic_regime': 'MIXED',
        'financial_stress_regime': 'ELEVATED_RESEARCH_STRESS',
        'sentiment_regime': 'NEUTRAL', 'technical_regime': 'STRONG_BULLISH'})
    evidence = engine.collect_evidence(row)
    assert len(evidence) == 4
    assert sum(x.stance == 'MIXED' for x in evidence) == 3
    assert engine.classify_evidence(evidence)['state'] == 'SUPPORTIVE'
