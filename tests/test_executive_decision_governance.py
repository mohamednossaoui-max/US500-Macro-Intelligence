from pathlib import Path
import json
import subprocess
import sys
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def test_current_fed_is_contextual_and_excluded_from_state():
    subprocess.run([sys.executable, str(ROOT / 'final_remaining_layers_hardening_v1.py')], cwd=ROOT, check=True)
    reg = pd.read_csv(ROOT / 'public_data' / 'decision_engine_evidence_registry_v2.csv')
    fed = reg.loc[reg['source'] == 'Fed Intelligence (current)']
    assert len(fed) == 1
    row = fed.iloc[0]
    assert row['decision_role'] == 'CONTEXTUAL'
    assert str(row['included_in_state']).lower() == 'false'
    assert row['category'] == 'fed'


def test_decision_state_semantics_unchanged():
    summary = pd.read_csv(ROOT / 'public_data' / 'decision_engine_research_summary_v1.csv').iloc[-1]
    assert int(summary['evidence_count']) == 4
    assert summary['state'] == 'SUPPORTIVE'


def test_executive_labels_confidence_as_evidence_coverage_and_checks_freshness():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'Evidence Coverage' in source
    assert 'Freshness mismatch: Fed Intelligence is as of' in source
    assert 'not silently' in source
    assert 'latest_date_from_json' in source


def test_fed_artifact_remains_research_only_contextual():
    fed = json.loads((ROOT / 'public_data' / 'fed_intelligence_output_v1.json').read_text())
    q = fed['quality']
    assert q['research_only'] is True
    assert q['decision_role'] == 'CONTEXTUAL'
    assert q['pit_status'] == 'PIT_SAFE'


def test_decision_summary_separates_core_and_overall_pit_semantics(tmp_path):
    input_file = ROOT / 'public_data' / 'research_context_summary_v1.csv'
    subprocess.run([
        sys.executable, str(ROOT / 'tests' / 'decision_engine' / 'decision_engine_v1.py'),
        '--input', str(input_file), '--output-dir', str(tmp_path)
    ], cwd=ROOT, check=True)
    summary = pd.read_csv(tmp_path / 'decision_engine_research_summary_v1.csv').iloc[-1]
    assert str(summary['core_point_in_time_safe']).lower() == 'true'
    assert summary['overall_evidence_pit_status'] == 'PIT_LIMITED'
    context = pd.read_csv(input_file).iloc[-1]
    assert float(summary['overall_evidence_pit_safe_pct']) == float(context['evidence_pit_safe_pct'])
    assert summary['overall_evidence_quality'] == context['evidence_quality_status']
    assert float(summary['overall_evidence_coverage_pct']) == float(context['evidence_coverage_pct'])
    assert summary['overall_evidence_freshness'] == context['evidence_freshness_status']
    assert float(summary['overall_evidence_freshness_current_pct']) == float(context['evidence_freshness_current_pct'])


def test_decision_quality_propagation_does_not_change_state(tmp_path):
    input_file = ROOT / 'public_data' / 'research_context_summary_v1.csv'
    subprocess.run([
        sys.executable, str(ROOT / 'tests' / 'decision_engine' / 'decision_engine_v1.py'),
        '--input', str(input_file), '--output-dir', str(tmp_path)
    ], cwd=ROOT, check=True)
    summary = pd.read_csv(tmp_path / 'decision_engine_research_summary_v1.csv').iloc[-1]
    assert summary['state'] == 'SUPPORTIVE'
    assert int(summary['evidence_count']) == 4
    assert bool(summary['research_only']) is True
