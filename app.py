import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from config import (
    APP_NAME,
    MARKET_TICKER,
    REFRESH_MINUTES,
    FED_URL,
)
from data import (
    get_market_data,
    load_all_macro_data,
    latest_value,
)
from engine import (
    latest,
    state,
    analyze,
    warnings,
    classify,
    decision_engine,
    technical_confirmation,
    early_warning,
    sl_tp,
    pullback_levels,
    position_size,
    build_analysis,
    PULLBACKS,
)
# ============================================================
# FED INTELLIGENCE
# ============================================================
from fed_intelligence import build_fed_intelligence
# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title=APP_NAME,
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)
# ============================================================
# GLOBAL STYLE
# ============================================================
st.markdown(
    """
    <style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        margin-bottom: 0.2rem;
    }
    .subtitle {
        color: #777;
        margin-bottom: 1.5rem;
    }
    .decision-box {
        padding: 18px;
        border-radius: 10px;
        margin: 10px 0 20px 0;
    }
    .small-note {
        color: #777;
        font-size: 0.85rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
# ============================================================
# HEADER
# ============================================================
st.markdown(
    f"""
