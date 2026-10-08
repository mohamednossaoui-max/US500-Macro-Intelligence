from pathlib import Path
import ast
import xml.etree.ElementTree as ET

from sidebar_navigation_v1 import ICONS, navigation_css


def test_every_page_has_a_valid_local_icon():
    tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text())
    pages = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                 and any(isinstance(t, ast.Name) and t.id == 'PAGES' for t in node.targets))
    names = [ast.literal_eval(key) for key in pages.keys]
    assert names == list(ICONS)
    assert len(set(ICONS.values())) == len(names)
    for paths in ICONS.values():
        ET.fromstring('<svg>' + paths + '</svg>')
    css = navigation_css(names)
    assert css.count('data:image/svg+xml,') == len(names)
    assert 'prefers-reduced-motion' in css and 'input:focus-visible' in css


def test_navigation_selection_survives_reruns():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_string(
        'import streamlit as st\n'
        'from sidebar_navigation_v1 import render_navigation, ICONS\n'
        'with st.sidebar:\n'
        '    selected = render_navigation(list(ICONS))\n'
        'st.write(selected)'
    ).run()
    assert not app.exception
    assert app.radio[0].value == 'Executive Dashboard'
    for page in ICONS:
        app.radio[0].set_value(page).run()
        assert not app.exception and app.radio[0].value == page
        assert any(item.value == page for item in app.markdown)
    app.run()
    assert app.radio[0].value == 'Methodology'
