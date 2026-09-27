from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ui_v3_is_loaded_after_page_config():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'from ui_v3 import apply_ui_v3' in source
    assert source.index('st.set_page_config(') < source.index('apply_ui_v3()')


def test_ui_v3_keeps_governance_language_visible():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'Decision Ready' in source
    assert 'Evidence Coverage' in source
    assert 'Research-only · no forecast · no execution' in source
    assert 'does not change CORE eligibility, weights or state' in source


def test_ui_v3_dark_tables_are_presentation_only():
    source = (ROOT / 'ui_v3.py').read_text(encoding='utf-8')
    assert '[data-testid="stDataFrame"]' in source
    assert '--gdg-bg-cell:#081522' in source
    assert 'dynamic_card' in source


def test_executive_has_interactive_workspace_and_alert_center():
    source = (ROOT / 'app.py').read_text(encoding='utf-8')
    assert 'Alert Center' in source
    assert 'Interactive Trends' in source
    assert 'Evidence Attention Order' in source
    assert 'Sources & Governance' in source
