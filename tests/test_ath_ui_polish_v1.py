from pathlib import Path
import json
from streamlit.testing.v1 import AppTest
from ath_ui_components_v1 import cards_html,CSS

ROOT=Path(__file__).resolve().parents[1]


def test_cards_escape_source_content():
    s=cards_html([('<script>','<img onerror="bad">','<b>source</b>')])
    assert '<script>' not in s and '<img' not in s and '<b>' not in s
    assert '&lt;script&gt;' in s and '&lt;img' in s


def test_layout_wraps_and_collapses_on_small_screens():
    assert 'text-overflow:ellipsis' not in CSS
    assert 'white-space:normal' in CSS and 'overflow-wrap:anywhere' in CSS
    assert '@media(max-width:700px)' in CSS and 'grid-template-columns:1fr' in CSS
    assert 'st-key-ath_page' in CSS
    assert '--ath-cols:1' in cards_html([('Risk','A long signal name','Context signal')])


def luminance(color):
    components=[int(color[i:i+2],16)/255 for i in (1,3,5)]
    linear=[x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in components]
    return sum(x*w for x,w in zip(linear,[.2126,.7152,.0722]))


def test_card_text_contrast():
    for text in ['#f3f7fb','#becfe0','#d8e5f2']:
        contrast=(luminance(text)+.05)/(luminance('#10243a')+.05)
        assert contrast>=4.5


def test_all_research_and_debug_panels_start_closed():
    app=AppTest.from_string('from ath_pullback_context_ui_v1 import render_ath_pullback_context\nrender_ath_pullback_context()').run(timeout=30)
    assert not app.exception and not app.error
    assert app.expander and all(not x.proto.expanded for x in app.expander)
    assert any(x.label=='Research archive and model comparisons' for x in app.expander)
    assert len(app.get('file_uploader'))==2
    assert not any(x.value=='Estimate unavailable' for x in app.metric)
    assert any('Observed drawdown' in x.value for x in app.markdown)


def test_saved_archive_mismatch_is_visible_in_details(tmp_path,monkeypatch):
    import ath_cause_context_ui_v1 as ui
    from ath_cause_context_v1 import assess
    report=assess(ROOT/'public_data')
    monkeypatch.setattr(ui,'assess',lambda root:report)
    monkeypatch.setattr(ui,'load',lambda archive:[{'snapshot_id':'old','payload':{'source_sha256':{}}},{'snapshot_id':'new','payload':{}}])
    archive=tmp_path/'research_history/ath_cause_v1';archive.mkdir(parents=True)
    (archive/'ath_cause_depth_audit_v1.json').write_text(json.dumps({'snapshot_count':1,'events_with_full_context':0,
        'capture':{'snapshot_id':'old'},'status':'INSUFFICIENT_HISTORICAL_CAUSE_VINTAGES'}))
    app=AppTest.from_string('from ath_cause_context_ui_v1 import render_cause_context\nrender_cause_context('+repr(str(tmp_path/'public_data'))+')').run(timeout=30)
    assert not app.exception
    assert any('older inputs or archive coverage' in x.value for x in app.info)
    assert any('2 snapshots' in x.value for x in app.markdown)



def test_archival_tables_use_dark_escaped_html():
    from ath_ui_components_v1 import table_html
    html=table_html([{'Horizon':'<script>alert(1)</script>','Brier':.3138}])
    assert '<script>' not in html and '&lt;script&gt;' in html
    assert 'ath-v1-tablewrap' in html and '0.3138' in html
    assert 'overflow-x:auto' in CSS and 'background:#142d46' in CSS
    page=(ROOT/'ath_pullback_context_ui_v1.py').read_text()
    assert 'st.dataframe(' not in page and 'research_table(' in page
