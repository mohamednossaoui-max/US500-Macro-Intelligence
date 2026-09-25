import json
from io import StringIO
from pathlib import Path
from typing import Optional, Any

import numpy as np
import pandas as pd
import requests
import streamlit as st

APP_VERSION = "5.0"
OWNER = "mohamednossaoui-max"
REPO = "US500-Macro-Intelligence"
BRANCH = "main"
RAW_BASE = f"https://raw.githubusercontent.com/{OWNER}/{REPO}/{BRANCH}/public_data"
TIMEOUT = 20

st.set_page_config(page_title="US500 Research Terminal", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container{padding-top:1rem;padding-bottom:2rem}
.small{color:#777;font-size:.85rem}
</style>
""", unsafe_allow_html=True)

FILES = {
    "Research Context": "research_context_v1.csv",
    "Macro Context": "macro_context_v1.csv",
    "Financial Stress": "financial_stress_research_v1.csv",
    "Sentiment": "sentiment_engine_research_v1.csv",
    "Technical": "technical_intelligence_research_v1.csv",
    "Liquidity": "liquidity_intelligence_research_v1.csv",
    "Market Breadth": "market_breadth_analysis_v1.csv",
    "Event News": "event_news_research_v2.csv",
    "Cross Asset": "cross_asset_research_v1.csv",
    "Earnings": "earnings_market_reaction_v3.csv",
    "Fed Intelligence": "fed_intelligence_output_v1.json",
    "Decision Engine": "decision_engine_research_v1.csv",
    "Decision Summary": "decision_engine_research_summary_v1.csv",
    "Decision Evidence": "decision_engine_research_evidence_v1.csv",
    "Decision JSON": "decision_engine_research_v1.json",
}

@st.cache_data(ttl=300, show_spinner=False)
def raw_text(filename: str) -> Optional[str]:
    local = Path("public_data") / filename
    if local.exists():
        try:
            return local.read_text(encoding="utf-8")
        except Exception:
            pass
    try:
        r = requests.get(f"{RAW_BASE}/{filename}", timeout=TIMEOUT,
                         headers={"User-Agent":"US500-Research-Terminal/5.0"})
        if r.ok:
            return r.text
    except requests.RequestException:
        pass
    return None

@st.cache_data(ttl=300, show_spinner=False)
def load(filename: str) -> Any:
    text = raw_text(filename)
    if text is None:
        return None
    try:
        if filename.endswith(".json"):
            return json.loads(text)
        return pd.read_csv(StringIO(text))
    except Exception:
        return None

DATA = {name: load(filename) for name, filename in FILES.items()}

def latest(df: Optional[pd.DataFrame]):
    if df is None or df.empty:
        return None
    for c in ["study_date","as_of_date","date","Date","event_date"]:
        if c in df.columns:
            d = pd.to_datetime(df[c], errors="coerce")
            if d.notna().any():
                return df.loc[d.idxmax()]
    return df.iloc[-1]

def val(row, names, default="Not available"):
    if row is None:
        return default
    for n in names:
        if n in row.index:
            x = row[n]
            if pd.isna(x) or str(x).strip() in ("", "nan", "None", "NaT"):
                continue
            return str(x)
    return default

def metric(label, value):
    st.metric(label, str(value))

ctx = latest(DATA["Research Context"])
dec = latest(DATA["Decision Summary"]) or latest(DATA["Decision Engine"])

context_date = val(ctx,["study_date","as_of_date","date"])
macro = val(ctx,["macro_economic_regime","economic_regime"])
stress = val(ctx,["macro_financial_stress_regime","financial_stress_regime"])
sent = val(ctx,["sentiment_unified_sentiment_regime","sentiment_research_regime","unified_sentiment_regime"])
tech = val(ctx,["technical_technical_regime","technical_research_regime","technical_regime"])
state = val(dec,["state","research_state"])
confidence = val(dec,["confidence"])
evidence = val(dec,["evidence_count"])
supportive = val(dec,["supportive_count"])
contradictory = val(dec,["contradictory_count"])
mixed = val(dec,["mixed_count"])
pit = val(dec,["point_in_time_safe"])
research_only = val(dec,["research_only"])

with st.sidebar:
    st.title("US500 Research Terminal")
    st.caption(f"V{APP_VERSION} • Token-free")
    pages = ["Overview","Market Regime","Macro","Fed Intelligence","Financial Stress",
             "Liquidity","Sentiment","Technical","Market Breadth","Historical Edge",
             "Event Studies","Cross-Asset","Earnings","Decision Engine","Evidence","Data Status"]
    page = st.radio("Navigation", pages)
    if st.button("Refresh data"):
        st.cache_data.clear(); st.rerun()
    st.divider()
    st.caption("Research-only • No execution • No trading signal • No forecast")

def table(name, height=420):
    df = DATA.get(name)
    if df is None:
        st.warning(f"{name} is not currently available in public_data.")
    elif df.empty:
        st.info(f"{name} is empty.")
    else:
        st.dataframe(df, use_container_width=True, height=height)

def overview():
    st.title("US500 Research Terminal")
    st.caption("Integrated point-in-time research dashboard — V5.0")
    st.info("This dashboard is research-only. It does not provide trading signals, forecasts, execution, broker integration, position sizing, stop loss or take profit.")
    st.subheader("Current Research Context")
    c=st.columns(4)
    for col,(label,value) in zip(c,[("Context Date",context_date),("Economic",macro),("Financial Stress",stress),("Sentiment",sent)]):
        with col: metric(label,value)
    c=st.columns(4)
    for col,(label,value) in zip(c,[("Technical",tech),("Decision State",state),("Confidence",confidence),("Evidence",evidence)]):
        with col: metric(label,value)
    st.subheader("Decision Engine")
    c=st.columns(6)
    for col,(label,value) in zip(c,[("State",state),("Confidence",confidence),("Evidence",evidence),("Supportive",supportive),("Contradictory",contradictory),("Mixed",mixed)]):
        with col: metric(label,value)
    st.subheader("Safeguards")
    c=st.columns(3)
    for col,(label,value) in zip(c,[("PIT Safe",pit),("Research Only",research_only),("Trading Signal","None")]):
        with col: metric(label,value)

def context_page():
    st.title("Market Regime")
    c=st.columns(4)
    for col,(label,value) in zip(c,[("Economic",macro),("Financial Stress",stress),("Sentiment",sent),("Technical",tech)]):
        with col: metric(label,value)
    table("Research Context",500)

def macro_page():
    st.title("Macro Context")
    row=latest(DATA["Macro Context"])
    c=st.columns(4)
    vals=[("Economic Regime",val(row,["economic_regime","macro_economic_regime"])),
          ("Financial Stress",val(row,["financial_stress_regime","macro_financial_stress_regime"])),
          ("Fed Score",val(row,["fed_score","macro_fed_score"])),
          ("Latest Topic",val(row,["latest_topic","event_latest_topic"]))]
    for col,(label,value) in zip(c,vals):
        with col: metric(label,value)
    table("Macro Context")

def fed_page():
    st.title("Fed Intelligence")
    obj=DATA["Fed Intelligence"]
    if obj is None: st.warning("Fed Intelligence is not available.")
    else: st.json(obj)

def stress_page():
    st.title("Financial Stress")
    row=latest(DATA["Financial Stress"]); c=st.columns(4)
    vals=[("Regime",val(row,["research_regime","financial_stress_regime"])),
          ("Composite",val(row,["composite_stress_score"])),("VIX",val(row,["VIX","vix"])),
          ("2Y-10Y Spread",val(row,["spread","TREASURY_SPREAD"]))]
    for col,(label,value) in zip(c,vals):
        with col: metric(label,value)
    table("Financial Stress")

def simple_page(title,name,fields=()):
    st.title(title); row=latest(DATA[name])
    if fields:
        c=st.columns(min(4,len(fields)))
        for col,(label,names) in zip(c,fields):
            with col: metric(label,val(row,names))
    table(name)

def historical_edge():
    st.title("Historical Edge")
    st.caption("Descriptive historical event-study and robustness diagnostics.")
    st.subheader("Historical Event Study V2")
    c=st.columns(5)
    for col,(label,value) in zip(c,[("Common Sample","1,916"),("Date Start","2019-01-03"),("Date End","2026-08-18"),("Events","11"),("Horizons","1D / 5D / 20D")]):
        with col: metric(label,value)
    st.caption("Run 36190915225 — structural validation PASS.")
    st.subheader("Historical Edge Robustness V1")
    c=st.columns(5)
    for col,(label,value) in zip(c,[("Temporal Periods","4"),("Temporal Rows","132"),("Threshold Rows","87"),("PIT Perfect","FALSE"),("Validation","PASS")]):
        with col: metric(label,value)
    st.info("Run 36192353073 completed successfully. The robustness output files are not yet published in public_data, so the dashboard shows only the verified run-level summary.")
    st.markdown("**Documented limitations:** some events have limited historical samples; PIT-perfect is FALSE; results are descriptive and do not establish causality or predictiveness.")

def decision_page():
    st.title("Decision Engine V1")
    st.warning("Research classification only — not a buy/sell signal or forecast.")
    c=st.columns(4)
    for col,(label,value) in zip(c,[("State",state),("Confidence",confidence),("Evidence",evidence),("PIT Safe",pit)]):
        with col: metric(label,value)
    c=st.columns(4)
    for col,(label,value) in zip(c,[("Supportive",supportive),("Contradictory",contradictory),("Mixed",mixed),("Research Only",research_only)]):
        with col: metric(label,value)
    st.subheader("Explicitly Disabled Outputs")
    st.dataframe(pd.DataFrame([
        ["Trading Signal","None"],["Forecast","None"],["Unified Decision","None"],
        ["Execution","False"],["Broker Integration","False"],["Position Sizing","False"],
        ["Stop Loss","None"],["Take Profit","None"]],columns=["Field","Value"]),use_container_width=True,hide_index=True)
    st.subheader("Evidence")
    table("Decision Evidence",300)
    st.subheader("Summary")
    table("Decision Summary",220)

def evidence_page():
    st.title("Evidence")
    table("Decision Evidence",400)
    st.markdown("The current evidence contains Economic=MIXED, Financial Stress=LOW_RESEARCH_STRESS, Sentiment=NEUTRAL and Technical=BULLISH. The Decision Engine classified the research state as SUPPORTIVE based on its documented evidence-counting rules; this is not a trading recommendation.")

def data_status():
    st.title("Data Status")
    st.success("No personal GitHub token is required. The app reads the public GitHub raw-data endpoint and falls back to a local public_data directory.")
    rows=[]
    for name,filename in FILES.items():
        obj=DATA[name]
        rows.append([name,filename,obj is not None,len(obj) if isinstance(obj,pd.DataFrame) else ("JSON" if obj is not None else 0)])
    st.dataframe(pd.DataFrame(rows,columns=["Dataset","Filename","Available","Rows"]),use_container_width=True,hide_index=True)
    st.code(RAW_BASE)
    st.subheader("Research Safeguards")
    st.dataframe(pd.DataFrame([
        ["Research only","TRUE"],["Trading signal","FALSE"],["Forecast","FALSE"],
        ["Execution","FALSE"],["Broker integration","FALSE"],["Position sizing","FALSE"],
        ["Stop loss","FALSE"],["Take profit","FALSE"],["Personal GitHub token","NOT REQUIRED"]],columns=["Control","Value"]),use_container_width=True,hide_index=True)

if page=="Overview": overview()
elif page=="Market Regime": context_page()
elif page=="Macro": macro_page()
elif page=="Fed Intelligence": fed_page()
elif page=="Financial Stress": stress_page()
elif page=="Liquidity": simple_page("Liquidity","Liquidity",[("Research Regime",["research_regime","liquidity_regime"]),("Net Liquidity",["NET_LIQUIDITY_PROXY_MILLIONS"]),("20D Change",["liquidity_20d_change","LIQUIDITY_20D_CHANGE"]),("Date",["study_date","as_of_date","date"])])
elif page=="Sentiment": simple_page("Sentiment","Sentiment",[("Research Regime",["research_regime","sentiment_research_regime"]),("Unified Regime",["unified_sentiment_regime","sentiment_unified_sentiment_regime"]),("COT",["cot_regime","COT_REGIME"]),("VIX",["vix_regime","VIX_REGIME"])])
elif page=="Technical": simple_page("Technical Intelligence","Technical",[("Technical Regime",["technical_regime","technical_technical_regime"]),("Trend Structure",["trend_structure","technical_trend_structure"]),("Drawdown",["drawdown","DRAWDOWN"]),("Date",["study_date","as_of_date","date"])])
elif page=="Market Breadth": simple_page("Market Breadth","Market Breadth",[("Breadth State",["breadth_research_state","research_state"]),("Date",["study_date","as_of_date","date"])])
elif page=="Historical Edge": historical_edge()
elif page=="Event Studies": simple_page("Event Studies","Research Context")
elif page=="Cross-Asset": simple_page("Cross-Asset Intelligence","Cross Asset",[("Research Regime",["research_regime","cross_asset_regime"]),("Date",["study_date","as_of_date","date"])])
elif page=="Earnings": simple_page("Earnings Intelligence","Earnings",[("Ticker",["ticker","symbol"]),("Date",["event_date","study_date","date"]),("Horizon",["horizon","holding_period"])])
elif page=="Decision Engine": decision_page()
elif page=="Evidence": evidence_page()
elif page=="Data Status": data_status()
