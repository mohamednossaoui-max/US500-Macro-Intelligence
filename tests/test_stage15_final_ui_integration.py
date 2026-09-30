from pathlib import Path

APP = Path('app.py').read_text(encoding='utf-8')


def test_executive_integrates_health_and_decision_intelligence():
    block = APP[APP.index('def executive()'):APP.index('def research_context()')]
    assert 'System Health Summary' in block
    assert 'Decision Intelligence V2' in block
    assert 'Closest Analog' in block


def test_decision_is_command_center_and_preserves_research_only_boundary():
    block = APP[APP.index('def decision()'):APP.index('def system_health()')]
    assert 'Decision Command Center' in block
    assert 'Historical US500 Reaction' in block
    assert 'Observed conditional outcomes' in block
    assert 'No trading signal, forecast, expected return' in block


def test_decision_uses_published_stage12_values_not_recomputed_analogs():
    block = APP[APP.index('def decision()'):APP.index('def system_health()')]
    assert 'di.get("historical_analogs"' in block
    assert 'di.get("historical_market_reaction"' in block
    assert 'historical_analog_engine' not in block
    assert 'historical_market_reaction_v1' not in block


def test_system_health_has_attention_and_pipeline_views():
    block = APP[APP.index('def system_health()'):APP.index('def event_study()')]
    assert 'System Health Command Center' in block
    assert 'Needs Attention' in block
    assert 'Pipeline Map' in block
    assert 'Last Known Good' in block


def test_stage15_keeps_raw_detail_on_demand_not_primary_white_tables():
    decision = APP[APP.index('def decision()'):APP.index('def system_health()')]
    assert 'st.tabs(["Evidence Matrix","Published Decision","Governance JSON"])' in decision
    assert "reaction-row" in APP


def test_mobile_css_exists_for_command_and_reaction_components():
    assert '@media(max-width:900px)' in APP
    assert '@media(max-width:560px)' in APP
    assert '.command-strip' in APP and '.reaction-row' in APP
