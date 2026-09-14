# ============================================================
# US500 MACRO INTELLIGENCE — PRODUCTION
# app.py
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime

from config import (
    APP_NAME,
    MARKET_TICKER,
    REFRESH_MINUTES,
    FRED_API_KEY,
)

from data import (
    fred_all,
    bls_all,
    market,
    fomc_page,
    parse_fomc,
)

from engine import (
    latest,
    state,
    analyze,
    warnings,
    classify,
    sl_tp,
    early_warning,
    PULLBACKS,
)


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
# CONSTANTS
# ============================================================

HISTORY_DEFAULT = "2015-01-01"


# ============================================================
# BASIC HELPERS
# ============================================================

def safe_float(x):
    try:
        if x is None:
            return np.nan

        if isinstance(x, str):
            x = x.replace(",", "").strip()

        return float(x)

    except Exception:
        return np.nan


def fmt(x, decimals=2):
    x = safe_float(x)

    if np.isnan(x):
        return "N/A"

    return f"{x:,.{decimals}f}"


def fmt_pct(x):
    x = safe_float(x)

    if np.isnan(x):
        return "N/A"

    return f"{x:.2f}%"


def pct_change(series, periods=1):
    try:
        if series is None or len(series) <= periods:
            return np.nan

        a = safe_float(series.iloc[-1]["value"])
        b = safe_float(series.iloc[-1 - periods]["value"])

        if np.isnan(a) or np.isnan(b) or b == 0:
            return np.nan

        return (a / b - 1) * 100

    except Exception:
        return np.nan


def delta_value(series, periods=1):
    try:
        if series is None or len(series) <= periods:
            return np.nan

        a = safe_float(series.iloc[-1]["value"])
        b = safe_float(series.iloc[-1 - periods]["value"])

        if np.isnan(a) or np.isnan(b):
            return np.nan

        return a - b

    except Exception:
        return np.nan


# ============================================================
# TECHNICAL CONFIRMATION
# ============================================================

def technical_confirmation(market_df):
    """
    Daily technical confirmation filter.

    Five factors:

    1. Price > SMA200
    2. SMA50 > SMA200
    3. Higher Low
    4. RSI > 50
    5. Close > SMA20

    This is a confirmation filter.
    It is NOT an automatic trade execution signal.
    """

    if market_df is None or market_df.empty:
        return {
            "score": 0,
            "max": 5,
            "status": "UNAVAILABLE",
            "factors": [],
            "values": {},
        }

    df = market_df.copy()

    required = ["close", "high", "low"]

    for col in required:
        if col not in df.columns:
            return {
                "score": 0,
                "max": 5,
                "status": "UNAVAILABLE",
                "factors": [],
                "values": {},
            }

        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        )

    df = df.dropna(subset=["close"])

    if len(df) < 220:
        return {
            "score": 0,
            "max": 5,
            "status": "INSUFFICIENT DATA",
            "factors": [],
            "values": {},
        }

    # --------------------------------------------------------
    # Moving averages
    # --------------------------------------------------------

    df["SMA20"] = df["close"].rolling(20).mean()
    df["SMA50"] = df["close"].rolling(50).mean()
    df["SMA200"] = df["close"].rolling(200).mean()

    # --------------------------------------------------------
    # RSI 14
    # --------------------------------------------------------

    delta = df["close"].diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)

    df["RSI14"] = 100 - (
        100 / (1 + rs)
    )

    # --------------------------------------------------------
    # Current values
    # --------------------------------------------------------

    last = df.iloc[-1]

    close = safe_float(last["close"])
    sma20 = safe_float(last["SMA20"])
    sma50 = safe_float(last["SMA50"])
    sma200 = safe_float(last["SMA200"])
    rsi = safe_float(last["RSI14"])

    # --------------------------------------------------------
    # Higher Low
    #
    # Compare the most recent swing-low area with
    # the previous swing-low area.
    # --------------------------------------------------------

    recent_low = safe_float(
        df["low"].iloc[-10:].min()
    )

    previous_low = safe_float(
        df["low"].iloc[-25:-10].min()
    )

    higher_low = (
        not np.isnan(recent_low)
        and not np.isnan(previous_low)
        and recent_low > previous_low
    )

    # --------------------------------------------------------
    # Technical factors
    # --------------------------------------------------------

    factors = []

    price_sma200 = (
        not np.isnan(close)
        and not np.isnan(sma200)
        and close > sma200
    )

    sma50_sma200 = (
        not np.isnan(sma50)
        and not np.isnan(sma200)
        and sma50 > sma200
    )

    rsi_pass = (
        not np.isnan(rsi)
        and rsi > 50
    )

    close_sma20 = (
        not np.isnan(close)
        and not np.isnan(sma20)
        and close > sma20
    )

    factors.append(
        {
            "Factor": "Price > SMA200",
            "Status": "PASS" if price_sma200 else "FAIL",
        }
    )

    factors.append(
        {
            "Factor": "SMA50 > SMA200",
            "Status": "PASS" if sma50_sma200 else "FAIL",
        }
    )

    factors.append(
        {
            "Factor": "Higher Low",
            "Status": "PASS" if higher_low else "FAIL",
        }
    )

    factors.append(
        {
            "Factor": "RSI14 > 50",
            "Status": "PASS" if rsi_pass else "FAIL",
        }
    )

    factors.append(
        {
            "Factor": "Close > SMA20",
            "Status": "PASS" if close_sma20 else "FAIL",
        }
    )

    score = sum(
        x["Status"] == "PASS"
        for x in factors
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if score >= 4:
        status = "CONFIRMED"

    elif score == 3:
        status = "PARTIAL"

    else:
        status = "WEAK"

    return {
        "score": int(score),
        "max": 5,
        "status": status,
        "factors": factors,
        "values": {
            "Close": close,
            "SMA20": sma20,
            "SMA50": sma50,
            "SMA200": sma200,
            "RSI14": rsi,
            "Recent Low": recent_low,
            "Previous Low": previous_low,
        },
    }


# ============================================================
# DECISION ENGINE
# ============================================================

def decision_engine(
    early_score,
    early_level,
    macro_score,
    regime,
    drawdown,
    technical_score,
    technical_status,
):

    regime_text = str(regime)

    # --------------------------------------------------------
    # CRITICAL SYSTEMIC STRESS
    # --------------------------------------------------------

    if early_score >= 75:

        return {
            "decision": "CRITICAL — NO NEW TRADE",
            "color": "red",
            "reason": (
                "Early Warning is CRITICAL. "
                "The strategy should not assume that a deep pullback "
                "is automatically a buying opportunity."
            ),
        }

    # --------------------------------------------------------
    # RECESSION / BEAR RISK
    # --------------------------------------------------------

    if regime_text.startswith("E"):

        return {
            "decision": "DEFENSIVE",
            "color": "red",
            "reason": (
                "Macro regime indicates recession / bear risk."
            ),
        }

    # --------------------------------------------------------
    # FINANCIAL SHOCK
    # --------------------------------------------------------

    if regime_text.startswith("F"):

        return {
            "decision": "DEFENSIVE",
            "color": "red",
            "reason": (
                "Financial/liquidity stress is detected."
            ),
        }

    # --------------------------------------------------------
    # HIGH EARLY WARNING
    # --------------------------------------------------------

    if early_score >= 50:

        return {
            "decision": "WAIT / CONFIRM",
            "color": "orange",
            "reason": (
                "Multiple leading indicators are showing "
                "meaningful deterioration."
            ),
        }

    # --------------------------------------------------------
    # MODERATE WARNING
    # --------------------------------------------------------

    if early_score >= 25:

        return {
            "decision": "CAUTION",
            "color": "yellow",
            "reason": (
                "Early warning indicators are deteriorating. "
                "A pullback should not be treated as automatically healthy."
            ),
        }

    # --------------------------------------------------------
    # INFLATION / RATE SHOCK
    # --------------------------------------------------------

    if regime_text.startswith("C"):

        return {
            "decision": "WAIT / CONFIRM",
            "color": "orange",
            "reason": (
                "Inflation/rates pressure is elevated. "
                "Wait for technical confirmation."
            ),
        }

    # --------------------------------------------------------
    # MIXED STRESS
    # --------------------------------------------------------

    if regime_text.startswith("D"):

        return {
            "decision": "WAIT / CONFIRM",
            "color": "orange",
            "reason": (
                "Growth and inflation signals are mixed. "
                "Technical confirmation is required."
            ),
        }

    # --------------------------------------------------------
    # LARGE DRAWDOWN
    # --------------------------------------------------------

    if drawdown <= -20:

        return {
            "decision": "WAIT / CONFIRM",
            "color": "orange",
            "reason": (
                "Drawdown is very deep. "
                "Depth alone does not justify a buy."
            ),
        }

    # --------------------------------------------------------
    # MODERATE DRAWDOWN
    # --------------------------------------------------------

    if drawdown <= -10:

        if technical_score >= 4:

            return {
                "decision": "SUPPORTIVE / CONFIRMED",
                "color": "green",
                "reason": (
                    "Macro conditions remain relatively supportive "
                    "and technical confirmation is strong."
                ),
            }

        return {
            "decision": "SUPPORTIVE / CONFIRM",
            "color": "green",
            "reason": (
                "Macro conditions remain relatively supportive, "
                "but the depth of the correction requires confirmation."
            ),
        }

    # --------------------------------------------------------
    # NORMAL PULLBACK
    # --------------------------------------------------------

    if early_score < 25 and macro_score >= 3:

        if technical_status == "CONFIRMED":

            return {
                "decision": "SUPPORTIVE — TECHNICALLY CONFIRMED",
                "color": "green",
                "reason": (
                    "Macro conditions are supportive, "
                    "early-warning stress remains low, "
                    "and technical confirmation is strong."
                ),
            }

        if technical_status == "PARTIAL":

            return {
                "decision": "CAUTION — TECHNICAL CONFIRMATION PARTIAL",
                "color": "yellow",
                "reason": (
                    "Macro conditions are supportive and "
                    "early-warning stress remains low, "
                    "but technical confirmation is only partial."
                ),
            }

        return {
            "decision": "CAUTION — TECHNICAL CONFIRMATION WEAK",
            "color": "yellow",
            "reason": (
                "Macro conditions are supportive, "
                "but technical confirmation is weak."
            ),
        }

    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return {
        "decision": "CAUTION",
        "color": "yellow",
        "reason": (
            "Signals are not sufficiently strong to classify "
            "the environment as clearly supportive."
        ),
    }


# ============================================================
# SIDEBAR
# ============================================================

st.sidebar.title("US500 Macro Intelligence")

fred_key = st.sidebar.text_input(
    "FRED API key",
    value=FRED_API_KEY,
    type="password",
    help="Stored securely in Streamlit Secrets or environment variables.",
)

history_start = st.sidebar.date_input(
    "History start",
    value=date(2015, 1, 1),
)

fed_stance = st.sidebar.selectbox(
    "Fed stance (temporary manual input)",
    [
        "Dovish",
        "Neutral",
        "Hawkish",
    ],
    index=1,
)

refresh = st.sidebar.button(
    "REFRESH NOW",
    type="primary",
)

st.sidebar.caption(
    f"Market feed: {MARKET_TICKER} | "
    f"Refresh target: {REFRESH_MINUTES} min"
)


# ============================================================
# LOAD DATA
# ============================================================

@st.cache_data(ttl=1800)
def load_fred(api_key, start):
    return fred_all(
        api_key,
        start,
    )


@st.cache_data(ttl=1800)
def load_bls(start_year, end_year):
    return bls_all(
        start_year,
        end_year,
    )


@st.cache_data(ttl=1800)
def load_market(start):
    return market(start)


if refresh:
    st.cache_data.clear()
    st.rerun()


if not fred_key:

    st.error(
        "FRED API key is missing. "
        "Add FRED_API_KEY in Streamlit Secrets."
    )

    st.stop()


# ============================================================
# DATA DOWNLOAD
# ============================================================

try:

    f = load_fred(
        fred_key,
        history_start,
    )

except Exception as e:

    st.error(
        "FRED data could not be loaded."
    )

    st.exception(e)

    st.stop()


try:

    b = load_bls(
        history_start.year,
        datetime.now().year,
    )

except Exception:

    b = {}


try:

    m = load_market(
        history_start,
    )

except Exception as e:

    st.error(
        "US500 market data could not be loaded."
    )

    st.exception(e)

    st.stop()


if m is None or m.empty:

    st.error(
        "No market data available."
    )

    st.stop()


# ============================================================
# MAIN ANALYSIS
# ============================================================

try:

    current_price, ath, drawdown, atr = state(m)

except Exception as e:

    st.error(
        "Unable to calculate market state."
    )

    st.exception(e)

    st.stop()


try:

    macro_score, regime, macro_details = analyze(
        f,
        fed_stance,
    )

except Exception as e:

    st.error(
        "Macro analysis failed."
    )

    st.exception(e)

    st.stop()


try:

    ew = early_warning(f)

except Exception as e:

    st.error(
        "Early Warning engine failed."
    )

    st.exception(e)

    st.stop()


# ============================================================
# TECHNICAL ANALYSIS
# ============================================================

tech = technical_confirmation(m)


technical_score = tech["score"]
technical_status = tech["status"]


# ============================================================
# PULLBACK CLASSIFICATION
# ============================================================

pullback_regime = classify(
    drawdown,
    macro_score,
    regime,
)


# ============================================================
# DECISION
# ============================================================

decision = decision_engine(
    early_score=ew["score"],
    early_level=ew["level"],
    macro_score=macro_score,
    regime=regime,
    drawdown=drawdown,
    technical_score=technical_score,
    technical_status=technical_status,
)


# ============================================================
# WARNING LIST
# ============================================================

legacy_warnings = warnings(
    f,
    macro_score,
)


# ============================================================
# HEADER
# ============================================================

st.title(
    "US500 Macro Intelligence — PRODUCTION"
)

st.caption(
    "Macro → Early Warning → Regime → Pullback → "
    "Technical Confirmation → Risk/Reward → Decision support only"
)


# ============================================================
# TOP METRICS
# ============================================================

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)


with c1:
    st.metric(
        "US500",
        fmt(current_price),
    )


with c2:
    st.metric(
        "ATH",
        fmt(ath),
    )


with c3:
    st.metric(
        "Drawdown",
        fmt_pct(drawdown),
    )


with c4:
    st.metric(
        "Macro",
        f"{macro_score:+d}/10",
    )


with c5:
    st.metric(
        "Regime",
        regime[0] if regime else "N/A",
    )


with c6:
    st.metric(
        "Pullback",
        pullback_regime[0]
        if pullback_regime
        else "N/A",
    )


with c7:
    st.metric(
        "Early Warning",
        f"{ew['score']}/100",
    )


with c8:
    st.metric(
        "Technical",
        f"{technical_score}/5",
    )


# ============================================================
# DECISION BANNER
# ============================================================

if decision["color"] == "green":

    st.success(
        decision["decision"]
    )

elif decision["color"] == "orange":

    st.warning(
        decision["decision"]
    )

elif decision["color"] == "yellow":

    st.warning(
        decision["decision"]
    )

else:

    st.error(
        decision["decision"]
    )


st.info(
    decision["reason"]
)


# ============================================================
# TABS
# ============================================================

(
    tab_live,
    tab_early,
    tab_technical,
    tab_macro,
    tab_trading,
    tab_events,
    tab_history,
) = st.tabs(
    [
        "LIVE",
        "EARLY WARNING",
        "TECHNICAL",
        "MACRO",
        "TRADING",
        "EVENTS",
        "HISTORY",
    ]
)


# ============================================================
# LIVE
# ============================================================

with tab_live:

    st.subheader(
        "الخلاصة التنفيذية"
    )

    live1, live2, live3, live4 = st.columns(4)

    with live1:

        st.write(
            "**Macro Regime**"
        )

        st.write(
            regime
        )

    with live2:

        st.write(
            "**Pullback**"
        )

        st.write(
            pullback_regime
        )

    with live3:

        st.write(
            "**Early Warning**"
        )

        st.write(
            f"{ew['score']}/100 — {ew['level']}"
        )

    with live4:

        st.write(
            "**Technical**"
        )

        st.write(
            f"{technical_score}/5 — {technical_status}"
        )

    st.divider()

    st.subheader(
        "Final Decision"
    )

    st.write(
        f"### {decision['decision']}"
    )

    st.write(
        decision["reason"]
    )

    st.divider()

    st.subheader(
        "Market State"
    )

    state_df = pd.DataFrame(
        [
            ["Current Price", current_price],
            ["All-Time High", ath],
            ["Drawdown", drawdown],
            ["ATR(14)", atr],
            ["Macro Score", macro_score],
            ["Early Warning", ew["score"]],
            ["Technical Score", technical_score],
        ],
        columns=[
            "Metric",
            "Value",
        ],
    )

    st.dataframe(
        state_df,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# EARLY WARNING
# ============================================================

with tab_early:

    st.header(
        "⚠️ Early Warning System"
    )

    st.write(
        "الهدف هو اكتشاف تغير النظام قبل أن يصل "
        "Drawdown إلى مستويات مثل -10% و-20%."
    )

    ew1, ew2 = st.columns(2)

    with ew1:

        st.metric(
            "Early Warning Score",
            f"{ew['score']}/100",
        )

    with ew2:

        st.metric(
            "Risk Level",
            ew["level"],
        )

    st.progress(
        min(max(ew["score"], 0), 100) / 100
    )

    st.divider()

    # --------------------------------------------------------
    # COMPONENT BREAKDOWN
    # --------------------------------------------------------

    st.subheader(
        "Component Breakdown"
    )

    details = ew.get(
        "details",
        {},
    )

    rows = []

    max_values = {
        "Credit": 20,
        "Labor": 20,
        "Yield Curve": 15,
        "Financial Conditions": 20,
        "Market Risk": 15,
        "Macro Momentum": 10,
    }

    for name, maximum in max_values.items():

        value = details.get(
            name,
            details.get(
                name.lower(),
                0,
            ),
        )

        value = safe_float(value)

        if np.isnan(value):
            value = 0

        stress = (
            value / maximum * 100
            if maximum
            else 0
        )

        rows.append(
            {
                "Component": name,
                "Score": int(value),
                "Maximum": maximum,
                "Stress": f"{stress:.0f}%",
            }
        )

    component_df = pd.DataFrame(
        rows
    )

    st.dataframe(
        component_df,
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # CURRENT WARNING INDICATORS
    # --------------------------------------------------------

    st.subheader(
        "Current Warning Indicators"
    )

    indicator_rows = []

    indicator_map = {
        "HY Spread": "HY_SPREAD",
        "Corporate OAS": "CORP_OAS",
        "Initial Claims 4W": "INITIAL_CLAIMS_4W",
        "Unemployment": "UNRATE",
        "10Y-2Y Yield Curve": "T10Y2Y",
        "NFCI": "NFCI",
        "VIX": "VIX",
        "DXY": "DXY",
    }

    for label, key in indicator_map.items():

        if key in f:

            indicator_rows.append(
                {
                    "Indicator": label,
                    "Latest": fmt(
                        latest(f[key])
                    ),
                }
            )

    if indicator_rows:

        st.dataframe(
            pd.DataFrame(indicator_rows),
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # REASONS
    # --------------------------------------------------------

    st.subheader(
        "Why is the score at this level?"
    )

    reasons = ew.get(
        "reasons",
        [],
    )

    if reasons:

        for reason in reasons:

            st.warning(
                reason
            )

    else:

        st.success(
            "No major early-warning trigger is currently detected."
        )

    # --------------------------------------------------------
    # INTERPRETATION
    # --------------------------------------------------------

    st.subheader(
        "Interpretation"
    )

    interpretation = pd.DataFrame(
        [
            [
                "0–24",
                "LOW",
                "Normal environment. No major systemic warning.",
            ],
            [
                "25–49",
                "MODERATE",
                "Some deterioration. Confirmation becomes important.",
            ],
            [
                "50–74",
                "HIGH",
                "Multiple leading indicators deteriorating.",
            ],
            [
                "75–100",
                "CRITICAL",
                "Systemic/liquidity risk. No new trade.",
            ],
        ],
        columns=[
            "Score",
            "Level",
            "Interpretation",
        ],
    )

    st.dataframe(
        interpretation,
        use_container_width=True,
        hide_index=True,
    )


# ============================================================
# TECHNICAL
# ============================================================

with tab_technical:

    st.header(
        "📈 Technical Confirmation"
    )

    st.write(
        "Technical confirmation uses Daily OHLC data "
        "as a confirmation filter. It is not an automatic "
        "trade execution signal."
    )

    t1, t2 = st.columns(2)

    with t1:

        st.metric(
            "Technical Score",
            f"{technical_score}/5",
        )

    with t2:

        st.metric(
            "Technical Status",
            technical_status,
        )

    st.progress(
        technical_score / 5
    )

    st.info(
        "التحليل التقني هنا يعمل كفلتر تأكيد فقط، "
        "ولا يقوم بفتح أي صفقة تلقائيًا."
    )

    st.subheader(
        "Technical Factors"
    )

    if tech["factors"]:

        technical_df = pd.DataFrame(
            tech["factors"]
        )

        st.dataframe(
            technical_df,
            use_container_width=True,
            hide_index=True,
        )

    st.subheader(
        "Technical Values"
    )

    technical_values = tech.get(
        "values",
        {},
    )

    technical_value_rows = []

    for name, value in technical_values.items():

        technical_value_rows.append(
            {
                "Indicator": name,
                "Value": fmt(value),
            }
        )

    if technical_value_rows:

        st.dataframe(
            pd.DataFrame(
                technical_value_rows
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    if technical_status == "CONFIRMED":

        st.success(
            "Technical confirmation is strong."
        )

    elif technical_status == "PARTIAL":

        st.warning(
            "Technical confirmation is partial."
        )

    elif technical_status == "WEAK":

        st.warning(
            "Technical confirmation is weak."
        )

    else:

        st.error(
            "Technical data is insufficient."
        )


# ============================================================
# MACRO
# ============================================================

with tab_macro:

    st.header(
        "🌎 Macro Intelligence"
    )

    macro_rows = [
        [
            "Macro Score",
            macro_score,
        ],
        [
            "Macro Regime",
            regime,
        ],
        [
            "Fed Stance",
            fed_stance,
        ],
        [
            "US10Y",
            latest(f.get("US10Y")),
        ],
        [
            "US2Y",
            latest(f.get("US2Y")),
        ],
        [
            "10Y - 2Y",
            latest(f.get("T10Y2Y")),
        ],
        [
            "VIX",
            latest(f.get("VIX")),
        ],
        [
            "DXY",
            latest(f.get("DXY")),
        ],
        [
            "HY Spread",
            latest(f.get("HY_SPREAD")),
        ],
        [
            "Corporate OAS",
            latest(f.get("CORP_OAS")),
        ],
        [
            "NFCI",
            latest(f.get("NFCI")),
        ],
        [
            "Initial Claims 4W",
            latest(f.get("INITIAL_CLAIMS_4W")),
        ],
        [
            "Industrial Production",
            latest(f.get("INDPRO")),
        ],
        [
            "Retail Sales",
            latest(f.get("RETAIL")),
        ],
        [
            "PCE",
            latest(f.get("PCE")),
        ],
        [
            "Core PCE",
            latest(f.get("CORE_PCE")),
        ],
        [
            "CPI",
            latest(f.get("CPI")),
        ],
        [
            "Unemployment",
            latest(f.get("UNRATE")),
        ],
    ]

    macro_df = pd.DataFrame(
        macro_rows,
        columns=[
            "Indicator",
            "Latest",
        ],
    )

    st.dataframe(
        macro_df,
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Macro Details"
    )

    detail_rows = []

    for key, value in macro_details.items():

        detail_rows.append(
            {
                "Factor": key,
                "Value": value,
            }
        )

    if detail_rows:

        st.dataframe(
            pd.DataFrame(detail_rows),
            use_container_width=True,
            hide_index=True,
        )


# ============================================================
# TRADING
# ============================================================

with tab_trading:

    st.header(
        "🎯 Trading Decision Support"
    )

    st.warning(
        "Decision support only — no automatic trade execution."
    )

    # --------------------------------------------------------
    # Current decision
    # --------------------------------------------------------

    st.subheader(
        "Current Decision"
    )

    if decision["color"] == "green":

        st.success(
            decision["decision"]
        )

    elif decision["color"] == "red":

        st.error(
            decision["decision"]
        )

    else:

        st.warning(
            decision["decision"]
        )

    st.write(
        decision["reason"]
    )

    # --------------------------------------------------------
    # Early warning protection
    # --------------------------------------------------------

    if ew["score"] >= 50:

        st.error(
            "⚠️ Early Warning is HIGH or CRITICAL. "
            "Do not treat the pullback depth alone as a buy signal."
        )

    elif ew["score"] >= 25:

        st.warning(
            "⚠️ Early Warning is MODERATE. "
            "Technical confirmation becomes more important."
        )

    # --------------------------------------------------------
    # Technical
    # --------------------------------------------------------

    st.subheader(
        "Technical Confirmation"
    )

    st.write(
        f"{technical_score}/5 — {technical_status}"
    )

    # --------------------------------------------------------
    # Pullback levels
    # --------------------------------------------------------

    st.subheader(
        "Pullback Levels"
    )

    pullback_rows = []

    for level in PULLBACKS:

        target_price = ath * (
            1 - level / 100
        )

        pullback_rows.append(
            {
                "Pullback": f"-{level}%",
                "Price": round(
                    target_price,
                    2,
                ),
            }
        )

    st.dataframe(
        pd.DataFrame(
            pullback_rows
        ),
        use_container_width=True,
        hide_index=True,
    )

    # --------------------------------------------------------
    # Risk / Reward
    # --------------------------------------------------------

    st.subheader(
        "Risk / Reward — 1:4"
    )

    entry = st.number_input(
        "Entry Price",
        min_value=0.0,
        value=float(current_price),
        step=0.25,
    )

    try:

        sl, tp, risk = sl_tp(
            m,
            entry,
        )

        rr_df = pd.DataFrame(
            [
                [
                    "Entry",
                    entry,
                ],
                [
                    "Stop Loss",
                    sl,
                ],
                [
                    "Risk",
                    risk,
                ],
                [
                    "Take Profit 1:4",
                    tp,
                ],
            ],
            columns=[
                "Level",
                "Price",
            ],
        )

        st.dataframe(
            rr_df,
            use_container_width=True,
            hide_index=True,
        )

    except Exception:

        st.warning(
            "Unable to calculate SL/TP."
        )


# ============================================================
# EVENTS
# ============================================================

with tab_events:

    st.header(
        "📅 Economic Events"
    )

    st.write(
        "Federal Reserve / FOMC information source:"
    )

    try:

        html = fomc_page()

        fomc = parse_fomc(
            html
        )

        st.success(
            "Federal Reserve calendar loaded."
        )

        years = fomc.get(
            "years_found",
            [],
        )

        if years:

            st.write(
                "Detected years:",
                ", ".join(years),
            )

        st.caption(
            fomc.get(
                "source",
                "",
            )
        )

    except Exception as e:

        st.warning(
            "FOMC calendar could not be loaded."
        )

        st.caption(
            str(e)
        )

    st.info(
        "Future versions can connect CPI, PPI, NFP, FOMC, "
        "GDP, ISM and Retail Sales release calendars directly "
        "to the event engine."
    )


# ============================================================
# HISTORY
# ============================================================

with tab_history:

    st.header(
        "📚 Historical Market State"
    )

    st.write(
        "Daily US500 history used by the analytical engine."
    )

    history_df = m.copy()

    if not history_df.empty:

        display_columns = []

        for col in [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]:

            if col in history_df.columns:

                display_columns.append(
                    col
                )

        if display_columns:

            hist_display = history_df[
                display_columns
            ].tail(500)

            st.dataframe(
                hist_display,
                use_container_width=True,
                hide_index=True,
            )

    st.divider()

    st.subheader(
        "Current Warning Flags"
    )

    if legacy_warnings:

        for item in legacy_warnings:

            st.warning(
                item
            )

    else:

        st.success(
            "No legacy macro warning flags detected."
        )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    "US500 Macro Intelligence — Decision Support Only | "
    "Not investment advice | No automatic execution"
)
