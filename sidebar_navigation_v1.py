"""Accessible native navigation with local vector icons and subtle motion."""
from urllib.parse import quote

import streamlit as st

# Local SVG paths: no external icon font, network request, or page-name changes.
ICONS = {
    'Executive Dashboard': '<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>',
    'Research Context': '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6M7 10h6M10 7v6"/>',
    'Macro Context': '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
    'Economic Intelligence': '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    'Fed Intelligence': '<path d="m3 8 9-5 9 5ZM5 10v8M10 10v8M15 10v8M20 10v8M3 21h18"/>',
    'Financial Stress': '<path d="M2 12h5l3-8 4 16 3-8h5"/>',
    'Liquidity': '<path d="M12 3s-7 8-7 12a7 7 0 0 0 14 0c0-4-7-12-7-12ZM9 16a3 3 0 0 0 3 3"/>',
    'Sentiment': '<circle cx="12" cy="12" r="9"/><path d="M8 9h.01M16 9h.01M8 15q4 4 8 0"/>',
    'Technical Intelligence': '<path d="M5 3v18M2 8h6v7H2M13 3v18M10 5h6v5h-6M21 3v18M18 12h5v6h-5"/>',
    'ATH Pullback Context': '<path d="m2 18 7-12 5 7 8-8M17 5h5v5"/>',
    'Market Breadth': '<path d="M12 3v7M5 10h14M5 10v6M12 10v6M19 10v6"/><rect x="2" y="16" width="6" height="5" rx="1"/><rect x="9" y="16" width="6" height="5" rx="1"/><rect x="16" y="16" width="6" height="5" rx="1"/>',
    'Cross-Asset': '<path d="m3 6 5 5 5-5 8 8M17 14h4v-4M3 18l5-5 5 5 8-8"/>',
    'Event / News': '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 8h10M7 12h4M7 16h4M15 12h2M15 16h2"/>',
    'Earnings': '<circle cx="12" cy="12" r="9"/><path d="M12 5v14M16 8h-6a2 2 0 0 0 0 4h4a2 2 0 0 1 0 4H8"/>',
    'Decision Engine': '<path d="M8 3h8v5H8ZM12 8v5M5 13h14M5 13v3M19 13v3M2 16h6v5H2ZM16 16h6v5h-6Z"/>',
    'System Health': '<path d="m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6ZM7 12h3l2-4 2 8 2-4h2"/>',
    'Historical Event Study': '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 3v4M17 3v4M3 10h18M7 14h3M14 14h3M7 17h3"/>',
    'Historical Edge': '<path d="M3 20V4M3 20h18M6 16l5-5 4 2 6-8M17 5h4v4"/>',
    'Final Validation': '<circle cx="12" cy="12" r="9"/><path d="m7 12 3 3 7-7"/>',
    'Data Status': '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 4 16 4 16 0V5M4 12c0 4 16 4 16 0"/>',
    'Data Explorer': '<path d="M3 5h7l2 3h9v12H3Z"/><circle cx="12" cy="14" r="3"/><path d="m14 16 3 3"/>',
    'Methodology': '<path d="M12 5C9 2 3 3 3 3v17s6-1 9 2c3-3 9-2 9-2V3s-6-1-9 2ZM12 5v17M6 7h3M15 7h3M6 11h3M15 11h3"/>',
}

BASE_CSS = '''
.st-key-us500_navigation [role="radiogroup"]{gap:5px!important}
.st-key-us500_navigation label[data-baseweb="radio"]{
 display:flex!important;align-items:center!important;gap:12px!important;
 margin:0!important;padding:9px 12px!important;border:1px solid transparent;
 border-radius:11px;background:transparent;min-height:42px;cursor:pointer;
 transition:background .18s ease,border-color .18s ease,transform .18s ease;
}
.st-key-us500_navigation label[data-baseweb="radio"]>div:first-of-type{width:0!important;height:0!important;flex:0 0 0!important;opacity:0!important;margin:0!important;padding:0!important;border:0!important}
.st-key-us500_navigation label[data-baseweb="radio"]>div:last-of-type{margin:0!important;min-width:0}
.st-key-us500_navigation label[data-baseweb="radio"] p{
 font-size:.88rem!important;font-weight:500!important;line-height:1.35!important;
 color:#becfe0!important;white-space:normal!important;
}
.st-key-us500_navigation label[data-baseweb="radio"]::before{
 content:"";width:21px;height:21px;flex:0 0 21px;
 background-position:center;background-size:contain;background-repeat:no-repeat;
 opacity:.8;transition:opacity .18s ease,transform .18s ease;pointer-events:none;
}
.st-key-us500_navigation label[data-baseweb="radio"]:hover{
 background:#142d46;border-color:#45607b;transform:translateX(2px);
}
.st-key-us500_navigation label[data-baseweb="radio"]:hover::before{opacity:1;transform:scale(1.08)}
.st-key-us500_navigation label[data-baseweb="radio"]:has(input:checked){
 background:#123450;border-color:#35a7ff;box-shadow:inset 3px 0 #35a7ff;
}
.st-key-us500_navigation label[data-baseweb="radio"]:has(input:checked) p{color:#f3f7fb!important;font-weight:650!important}
.st-key-us500_navigation label[data-baseweb="radio"]:has(input:checked)::before{opacity:1}
.st-key-us500_navigation label[data-baseweb="radio"]:has(input:focus-visible){outline:2px solid #35a7ff;outline-offset:2px}
@media(prefers-reduced-motion:reduce){
 .st-key-us500_navigation label[data-baseweb="radio"],
 .st-key-us500_navigation label[data-baseweb="radio"]::before{transition:none!important;transform:none!important}
}
'''


def navigation_css(pages):
    rules = [BASE_CSS]
    for index, name in enumerate(pages, 1):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
               'fill="none" stroke="#73c5ff" stroke-width="1.7" '
               'stroke-linecap="round" stroke-linejoin="round">'
               + ICONS.get(name, ICONS['Executive Dashboard']) + '</svg>')
        rules.append('.st-key-us500_navigation label[data-baseweb="radio"]'
                     f':nth-of-type({index})::before'
                     '{background-image:url("data:image/svg+xml,' + quote(svg, safe='') + '")}')
    return '<style>' + '\n'.join(rules) + '</style>'


def render_navigation(pages):
    st.markdown(navigation_css(pages), unsafe_allow_html=True)
    with st.container(key='us500_navigation'):
        return st.radio('Navigation', pages, index=0, key='us500_page')
