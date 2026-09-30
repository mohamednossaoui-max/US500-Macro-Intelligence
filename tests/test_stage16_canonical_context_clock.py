from pathlib import Path
import json
import pandas as pd

from evidence_adapters import technical
import research_evidence_contract_v1 as contract

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / 'public_data'


def _context_date():
    d = pd.read_csv(PUBLIC / 'research_context_summary_v1.csv', low_memory=False)
    return pd.to_datetime(d.iloc[-1]['context_date']).normalize()


def test_technical_never_selects_evidence_after_canonical_context_clock():
    ctx = _context_date()
    rows = technical(PUBLIC)
    assert rows, 'Technical evidence should exist for the current context'
    for row in rows:
        assert pd.to_datetime(row['as_of_date']).normalize() == ctx
        assert pd.to_datetime(row['available_at']).normalize() <= ctx


def test_contract_has_zero_future_evidence_at_current_snapshot():
    rows = contract.build_rows(PUBLIC)
    df = pd.DataFrame(rows)
    future = df.loc[df['pit_status'] == 'NOT_PIT_SAFE']
    assert future.empty, future[['module','indicator','available_at','as_of_date','source_artifact']].to_dict('records')


def test_published_chronology_gate_remains_strict():
    validation = json.loads((PUBLIC / 'research_evidence_validation_v1.json').read_text(encoding='utf-8'))
    assert validation['chronology_valid'] is True
    assert int(validation['future_evidence_count']) == 0
