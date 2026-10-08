from pathlib import Path
import tomllib
import pandas as pd
from ui_theme_v1 import dark_line_chart, SURFACE, TEXT, MUTED, CSS, CHART_HEIGHT

ROOT = Path(__file__).resolve().parents[1]


def test_stress_chart_has_explicit_dark_surface_and_all_original_values():
    frame = pd.DataFrame({'Date': pd.to_datetime(['2024-01-01', '2024-01-02', '2024-01-03'], utc=True),
                          'composite_stress_score': [-.3, .02, 1.5]})
    before = frame.copy(deep=True)
    spec = dark_line_chart(frame, 'composite_stress_score').to_dict()
    assert spec['background'] == SURFACE and spec['height'] == CHART_HEIGHT
    assert spec['config']['axis']['labelColor'] == MUTED
    assert spec['config']['axis']['titleColor'] == TEXT
    assert spec['mark']['color'] == '#35a7ff'
    assert spec['encoding']['y']['scale']['zero'] is False
    data = spec.get('datasets', {}).get(spec['data'].get('name'), spec['data'].get('values'))
    assert [x['composite_stress_score'] for x in data] == [-.3, .02, 1.5]
    pd.testing.assert_frame_equal(frame, before)


def test_large_histories_do_not_require_downsampling():
    frame = pd.DataFrame({'Date': pd.date_range('2000-01-01', periods=6000, tz='UTC'), 'score': range(6000)})
    spec = dark_line_chart(frame, 'score').to_dict()
    data = spec.get('datasets', {}).get(spec['data'].get('name'), spec['data'].get('values'))
    assert len(data) == 6000 and data[-1]['score'] == 5999


def test_streamlit_widgets_share_dark_theme():
    config = tomllib.loads((ROOT / '.streamlit/config.toml').read_text())['theme']
    assert config['base'] == 'dark' and config['secondaryBackgroundColor'] == SURFACE
    assert config['textColor'] == TEXT
    assert 'white-space:normal!important' in CSS and 'overflow-wrap:anywhere' in CSS
    assert '@media(max-width:700px)' in CSS


def test_component_renders_without_white_chart_theme():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string('''
import pandas as pd
from ui_theme_v1 import apply_theme, render_line_chart
apply_theme()
render_line_chart(pd.DataFrame({'Date': pd.date_range('2024-01-01',periods=3), 'score': [0.,1.,2.]}), 'score')
''').run(timeout=30)
    assert not app.exception
    charts = app.get('vega_lite_chart') + app.get('arrow_vega_lite_chart')
    assert len(charts) == 1
    import json
    assert json.loads(charts[0].proto.spec)['background'] == SURFACE


def test_actual_financial_stress_page_uses_shared_dark_chart():
    import json
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(ROOT / 'app.py')).run(timeout=30)
    assert not app.exception
    app.radio[0].set_value('Financial Stress').run(timeout=30)
    assert not app.exception
    charts = app.get('vega_lite_chart') + app.get('arrow_vega_lite_chart')
    assert len(charts) == 1
    spec = json.loads(charts[0].proto.spec)
    assert spec['background'] == SURFACE and spec['height'] == CHART_HEIGHT
    assert spec['encoding']['y']['field'] == 'composite_stress_score'
