"""Scoped ATH presentation components; no data mutation or forecast calculations."""
from html import escape
import streamlit as st
import pandas as pd

CSS='''<style>
.st-key-ath_page {color:#f3f7fb}
.st-key-ath_page [data-testid="stCaptionContainer"] p {color:#becfe0!important;font-size:.92rem!important;line-height:1.55!important}
.st-key-ath_page [data-testid="stMarkdownContainer"] {color:#f3f7fb!important}
.st-key-ath_page [data-testid="stMarkdownContainer"] h1,.st-key-ath_page [data-testid="stMarkdownContainer"] h2,.st-key-ath_page [data-testid="stMarkdownContainer"] h3 {color:#f3f7fb!important}
.st-key-ath_page [data-testid="stMarkdownContainer"] p {line-height:1.55}
.st-key-ath_page [data-testid="stMetricValue"] {font-size:1.4rem!important;white-space:normal!important;overflow:visible!important;text-overflow:clip!important;overflow-wrap:anywhere}
.st-key-ath_page [data-testid="stMetricLabel"] p {color:#d8e5f2!important;white-space:normal!important}
.st-key-ath_page [data-testid="stExpander"] {border-color:#45607b!important;background:#10243a!important;border-radius:12px}
.st-key-ath_page [data-testid="stExpander"] summary {color:#f3f7fb!important;font-weight:600}
.st-key-ath_page [data-testid="stAlert"] {background:#142d46!important;color:#f3f7fb!important;border:1px solid #45607b!important}
.st-key-ath_page [data-testid="stAlert"] p {color:#f3f7fb!important}
.ath-v1-grid {display:grid;grid-template-columns:repeat(var(--ath-cols,3),minmax(0,1fr));gap:12px;margin:14px 0 18px}
.ath-v1-card {min-width:0;padding:18px;border:1px solid #45607b;border-radius:14px;background:#10243a;color:#f3f7fb}
.ath-v1-label {font-size:.88rem;line-height:1.45;color:#becfe0;margin-bottom:8px;overflow-wrap:anywhere}
.ath-v1-value {font-size:clamp(1.3rem,2.1vw,1.9rem);font-weight:750;line-height:1.25;color:#f3f7fb;white-space:normal;overflow-wrap:anywhere}
.ath-v1-note {font-size:.9rem;line-height:1.5;color:#becfe0;margin-top:9px;overflow-wrap:anywhere}
.ath-v1-notice {padding:17px 19px;border:1px solid #45607b;border-left:4px solid #71b7ff;border-radius:12px;background:#10243a;margin:12px 0;color:#f3f7fb}
.ath-v1-notice.warning {border-left-color:#ffc56d}
.ath-v1-notice strong {font-size:1.02rem;line-height:1.5;color:#f3f7fb}
.ath-v1-notice p {font-size:.95rem;line-height:1.6;color:#d8e5f2;margin:7px 0 0;overflow-wrap:anywhere}
.ath-v1-tablewrap {max-width:100%;overflow-x:auto;margin:12px 0;border:1px solid #45607b;border-radius:12px}
.ath-v1-table {width:100%;min-width:560px;border-collapse:collapse;background:#10243a;color:#f3f7fb;font-size:.9rem}
.ath-v1-table th {background:#142d46;color:#f3f7fb;text-align:left;padding:12px;border-bottom:1px solid #45607b;line-height:1.5}
.ath-v1-table td {background:#10243a;color:#d8e5f2;padding:11px 12px;border-bottom:1px solid #304c67;line-height:1.5;font-variant-numeric:tabular-nums}
.ath-v1-table tr:last-child td {border-bottom:0}
@media(max-width:700px){.ath-v1-grid{grid-template-columns:1fr}.ath-v1-card{padding:16px}.ath-v1-value{font-size:1.5rem}}
</style>'''


def styles():st.markdown(CSS,unsafe_allow_html=True)


def cards_html(items):
    return '<div class="ath-v1-grid" style="--ath-cols:'+str(min(3,max(1,len(items))))+'">'+''.join(
        '<div class="ath-v1-card"><div class="ath-v1-label">'+escape(str(label))+
        '</div><div class="ath-v1-value">'+escape(str(value))+
        '</div><div class="ath-v1-note">'+escape(str(note))+'</div></div>'
        for label,value,note in items)+'</div>'


def cards(items):st.markdown(cards_html(items),unsafe_allow_html=True)


def notice(title,body,warning=False):
    kind=' warning' if warning else ''
    st.markdown('<div class="ath-v1-notice'+kind+'"><strong>'+escape(str(title))+
                '</strong><p>'+escape(str(body))+'</p></div>',unsafe_allow_html=True)



def table_html(data):
    frame=pd.DataFrame(data).rename(columns={'NO_MEANINGFUL_PULLBACK':'Minor','LIMITED':'Limited','MEDIUM':'Medium','CRASH':'Crash'})
    if 'Horizon' in frame:
        frame['Horizon']=frame['Horizon'].replace({'UNTIL_RECOVERY':'Peak recovery','1M':'1 month','3M':'3 months'})
    return '<div class="ath-v1-tablewrap">'+frame.to_html(index=False,border=0,escape=True,
        classes='ath-v1-table',na_rep='—',float_format=lambda x:f'{x:.4f}')+'</div>'


def research_table(data,**_display_options):
    st.markdown(table_html(data),unsafe_allow_html=True)
