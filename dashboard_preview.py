import streamlit as st
from ui.terminal_theme import apply_terminal_theme, status_badge, metric_card, section_header

st.set_page_config(page_title="US500 Macro Intelligence", layout="wide")
apply_terminal_theme()

st.caption("US500 MACRO INTELLIGENCE · RESEARCH · EVIDENCE · MACRO · MARKETS")
st.title("Executive Dashboard")
st.caption("Institutional research terminal · research-only · no forecast · no execution")

a,b,c,d = st.columns(4)
with a: status_badge("US500 Regime","SUPPORTIVE","positive","Current research state")
with b: status_badge("Research Readiness","NOT READY","warning","Research-only")
with c: status_badge("Data Freshness","CURRENT","info","Published evidence")
with d: status_badge("PIT Integrity","LIMITED","warning","Point-in-time constraints")

section_header("Macro Regime Map","CURRENT STATE")
cols = st.columns(6)
cards = [
 ("Growth","-0.24","Weakening","negative"),
 ("Inflation","0.76","Disinflation","positive"),
 ("Labor","0.03","Stable","info"),
 ("Fed","55.70","Neutral","purple"),
 ("Liquidity","0.42","Supportive","positive"),
 ("Stress","-0.25","Low","positive"),
]
for col, item in zip(cols,cards):
    with col: metric_card(*item)

section_header("Research Workspace","EVIDENCE")
left,mid,right = st.columns([1.25,1,1])
with left:
    st.subheader("US500 Price · Reference")
    st.info("Connect this panel to the existing published price/reference dataset. No new forecasting logic is introduced.")
with mid:
    st.subheader("Evidence Coverage")
    st.metric("Core evidence", "4 / 4")
    st.progress(1.0)
with right:
    st.subheader("Key Takeaways")
    st.markdown("**Macro:** mixed  \n**Inflation:** improving  \n**Labor:** stable  \n**Fed:** neutral  \n**Stress:** low")

section_header("Evidence Matrix","QUALITY · FRESHNESS · PIT")
st.caption("Keep the existing Evidence Contract / Research Gate as the source of truth.")
