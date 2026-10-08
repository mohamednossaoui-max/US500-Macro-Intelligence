"""Shared presentation tokens and explicit dark charts; no data calculations."""
import altair as alt
import streamlit as st

BACKGROUND = '#06101b'
SURFACE = '#10243a'
SURFACE_HEADER = '#142d46'
TEXT = '#f3f7fb'
MUTED = '#becfe0'
BORDER = '#45607b'
ACCENT = '#35a7ff'
CHART_HEIGHT = 320

CSS = '''<style>
.v3-title{font-size:1.9rem!important}.v3-section b{font-size:1.1rem!important}
:root{--bg:#06101b;--panel:#10243a;--panel2:#142d46;--line:#45607b;--text:#f3f7fb;--muted:#becfe0;--blue:#35a7ff}
[data-testid="stAppViewContainer"]{color:var(--text)}
[data-testid="stMarkdownContainer"] h1{font-size:1.9rem!important;line-height:1.25!important;color:var(--text)!important}
[data-testid="stMarkdownContainer"] h2{font-size:1.45rem!important;line-height:1.3!important;color:var(--text)!important}
[data-testid="stMarkdownContainer"] h3{font-size:1.1rem!important;line-height:1.4!important;color:var(--text)!important}
.card,.v3-card,.ath-v1-card,.signal-card,.econ-dim,.econ-group,.command-cell,.research-panel,.fed-brief-cell,.comm-shift,.v3-rank,.v3-alert,.fed-strip,.econ-bottom,.bottom-line,[data-testid="stMetric"]{background:var(--panel)!important;border-color:var(--line)!important;border-radius:14px!important;padding:14px 16px!important;min-width:0}
.card,.v3-card{overflow:visible!important}
.fed-scale,.fed-strip .kicker,.bottom-line .title,.comm-shift-flow small,.label,.v3-label,.ath-v1-label,.econ-group-title,.signal-title,.command-cell .k,.research-panel .rp-title,.fed-brief-cell span{font-size:.78rem!important;line-height:1.45!important;color:var(--muted)!important;letter-spacing:.05em!important}
.value,.v3-value,.ath-v1-value,.econ-dim .score,.signal-main,.econ-regime,.command-cell .v,.fed-brief-cell b,[data-testid="stMetricValue"]{font-size:1.4rem!important;line-height:1.3!important;color:var(--text)!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;overflow-wrap:anywhere}
.small,.v3-note,.ath-v1-note,.econ-sub,.econ-context,.econ-release .meta,.signal-why,.comm-note,.comm-shift-date,.command-cell .n,.fed-strip .detail,.bottom-line .body,.pulse-note{font-size:.88rem!important;line-height:1.5!important;color:var(--muted)!important;overflow-wrap:anywhere}
[data-testid="stCaptionContainer"] p{font-size:.88rem!important;line-height:1.5!important;color:var(--muted)!important}
[data-testid="stMetricLabel"] p{font-size:.78rem!important;color:var(--muted)!important}
[data-testid="stExpander"]{background:var(--panel)!important;border-color:var(--line)!important;border-radius:14px!important}
[data-testid="stExpander"] summary{color:var(--text)!important}
#vg-tooltip-element{background:#142d46!important;color:#f3f7fb!important;border-color:#45607b!important;font-size:14px!important}
@media(max-width:700px){[data-testid="stMarkdownContainer"] h1{font-size:1.5rem!important}.value,.v3-value,.ath-v1-value,[data-testid="stMetricValue"]{font-size:1.2rem!important}.card,.v3-card,.ath-v1-card{padding:12px!important}.v3-rank{flex-wrap:wrap}.v3-rankname{min-width:0;overflow-wrap:anywhere}}
</style>'''


def apply_theme():
    st.markdown(CSS, unsafe_allow_html=True)


def dark_line_chart(frame, series):
    # Explicit chart background is necessary even when the browser prefers light.
    records = [{'Date': d.isoformat() if hasattr(d, 'isoformat') else str(d),
                series: float(value)} for d, value in zip(frame['Date'], frame[series])]
    return (alt.Chart(alt.InlineData(values=records)).mark_line(color=ACCENT, strokeWidth=2)
        .encode(x=alt.X('Date:T', title='Date'),
                y=alt.Y(series + ':Q', title=series.replace('_', ' '), scale=alt.Scale(zero=False)),
                tooltip=[alt.Tooltip('Date:T', title='Date'), alt.Tooltip(series + ':Q', title=series, format='.4f')])
        .properties(height=CHART_HEIGHT, background=SURFACE)
        .configure_view(stroke=BORDER)
        .configure_axis(labelColor=MUTED, titleColor=TEXT, gridColor='#304c67',
                        domainColor=BORDER, tickColor=BORDER, labelFontSize=12, titleFontSize=13)
        .configure_legend(labelColor=TEXT, titleColor=TEXT)
        .interactive(bind_y=False))


def render_line_chart(frame, series):
    st.altair_chart(dark_line_chart(frame, series), width='stretch', theme=None)
