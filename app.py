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
    <div class="main-title">
        📊 {APP_NAME}
    </div>

    <div class="subtitle">
        Daily Swing-Trading Decision Support System
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    st.header("⚙️ Settings")

    st.write(
        f"**Market:** `{MARKET_TICKER}`"
    )

    st.write(
        f"**Refresh:** {REFRESH_MINUTES} min"
    )

    st.divider()

    st.subheader(
        "Federal Reserve Stance"
    )

    fed_stance = st.selectbox(
        "Current Fed stance",
        [
            "Neutral",
            "Dovish",
            "Hawkish",
        ],
        index=0,
    )

    st.caption(
        "Fed stance is currently a manual input for the "
        "main macro engine. Fed Intelligence is analyzed "
        "separately and does not automatically modify the "
        "final decision."
    )

    st.divider()

    st.subheader(
        "Strategy"
    )

    st.write(
        "Timeframe: Daily"
    )

    st.write(
        "Style: Swing / Pullback"
    )

    st.write(
        "Risk/Reward: 1 : 4"
    )

    st.write(
        "Execution: Manual"
    )

    st.divider()

    st.caption(
        "This application provides analysis and decision support. "
        "It does not execute trades."
    )


# ============================================================
# LOAD MARKET DATA
# ============================================================

@st.cache_data(
    ttl=REFRESH_MINUTES * 60
)
def load_market():

    return get_market_data(
        MARKET_TICKER,
        period="5y",
    )


# ============================================================
# LOAD MACRO DATA
# ============================================================

@st.cache_data(
    ttl=REFRESH_MINUTES * 60
)
def load_macro():

    return load_all_macro_data()


# ============================================================
# LOAD FED INTELLIGENCE
# ============================================================

@st.cache_data(
    ttl=REFRESH_MINUTES * 60
)
def load_fed_intelligence():

    try:

        result = build_fed_intelligence()

        if result is None:

            return {
                "available": False,
                "error": "Fed Intelligence returned no data.",
            }

        return result

    except Exception as e:

        return {
            "available": False,
            "error": str(e),
        }


# ============================================================
# GET DATA
# ============================================================

market = load_market()

macro_data = load_macro()

fed_intelligence = load_fed_intelligence()


# ============================================================
# DATA VALIDATION
# ============================================================

if market is None or market.empty:

    st.error(
        "Unable to load US500 market data."
    )

    st.stop()


# ============================================================
# COMPLETE ANALYSIS
# ============================================================

analysis = build_analysis(
    market,
    macro_data,
    fed=fed_stance,
)


# ============================================================
# EXTRACT VALUES
# ============================================================

market_info = analysis["market"]

macro_info = analysis["macro"]

ew_info = analysis["early_warning"]

technical_info = analysis["technical"]

decision_info = analysis["decision"]

price = market_info["price"]

ath = market_info["ath"]

drawdown = market_info["drawdown"]

atr = market_info["atr14"]

macro_score = macro_info["score"]

regime = macro_info["regime"]

ew_score = ew_info["score"]

ew_level = ew_info["level"]

technical_score = technical_info["score"]

technical_status = technical_info["status"]

final_decision = decision_info["decision"]


# ============================================================
# FED INTELLIGENCE HELPERS
# ============================================================

def fed_get(key, default=None):

    if not isinstance(fed_intelligence, dict):

        return default

    return fed_intelligence.get(
        key,
        default,
    )


def safe_number(value):

    try:

        if value is None:
            return None

        if isinstance(value, float) and np.isnan(value):
            return None

        return float(value)

    except Exception:

        return None


def format_number(value, decimals=1):

    number = safe_number(value)

    if number is None:

        return "N/A"

    return f"{number:.{decimals}f}"


def format_date(value):

    if value is None:

        return "N/A"

    return str(value)


def display_reason(reason):

    if reason is None:

        return "NEUTRAL"

    text = str(reason).strip()

    if text == "" or text.lower() == "none":

        return "NEUTRAL"

    return text


# ============================================================
# TOP METRICS
# ============================================================

st.subheader(
    "Live Market Dashboard"
)

c1, c2, c3, c4 = st.columns(4)

with c1:

    st.metric(
        "US500",
        f"{price:.2f}",
    )

with c2:

    st.metric(
        "ATH",
        f"{ath:.2f}",
    )

with c3:

    st.metric(
        "Drawdown",
        f"{drawdown:.2f}%",
    )

with c4:

    st.metric(
        "ATR(14)",
        f"{atr:.2f}"
        if not np.isnan(atr)
        else "N/A",
    )


c5, c6, c7, c8 = st.columns(4)

with c5:

    st.metric(
        "Macro",
        f"{macro_score:+d}/10",
    )

with c6:

    st.metric(
        "Regime",
        regime.split("—")[0].strip(),
    )

with c7:

    st.metric(
        "Early Warning",
        f"{ew_score}/100",
    )

with c8:

    st.metric(
        "Technical",
        f"{technical_score}/5",
    )


# ============================================================
# FINAL DECISION BANNER
# ============================================================

st.divider()

if decision_info["color"] == "red":

    st.error(
        f"🔴 {final_decision}"
    )

elif decision_info["color"] == "orange":

    st.warning(
        f"🟠 {final_decision}"
    )

elif decision_info["color"] == "yellow":

    st.warning(
        f"🟡 {final_decision}"
    )

else:

    st.success(
        f"🟢 {final_decision}"
    )

st.info(
    f"**Reason:** {decision_info['reason']}"
)


# ============================================================
# CURRENT PULLBACK
# ============================================================

current_pullback = None

if not np.isnan(drawdown):

    if drawdown <= -30:
        current_pullback = "−30%"

    elif drawdown <= -20:
        current_pullback = "−20%"

    elif drawdown <= -10:
        current_pullback = "−10%"

    elif drawdown <= -5:
        current_pullback = "−5%"

    elif drawdown <= -3:
        current_pullback = "−3%"

    else:
        current_pullback = "Normal"


st.write(
    f"**Current Pullback Zone:** {current_pullback}"
)


# ============================================================
# TABS
# ============================================================

(
    tab_live,
    tab_early,
    tab_technical,
    tab_macro,
    tab_fed,
    tab_trading,
    tab_events,
    tab_history,
) = st.tabs(
    [
        "LIVE",
        "EARLY WARNING",
        "TECHNICAL",
        "MACRO",
        "FED INTELLIGENCE",
        "TRADING",
        "EVENTS",
        "HISTORY",
    ]
)


# ============================================================
# LIVE TAB
# ============================================================

with tab_live:

    st.subheader(
        "📊 Live Overview"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.write(
            "**Macro Regime**"
        )

        st.info(
            regime
        )

        st.write(
            "**Early Warning**"
        )

        st.progress(
            ew_score / 100
        )

        st.write(
            f"{ew_score}/100 — {ew_level}"
        )

    with col2:

        st.write(
            "**Technical Confirmation**"
        )

        st.progress(
            technical_score / 5
        )

        st.write(
            f"{technical_score}/5 — {technical_status}"
        )

        st.write(
            "**Final Decision**"
        )

        st.info(
            final_decision
        )

    st.divider()

    st.subheader(
        "Pullback Levels"
    )

    pullbacks = pullback_levels(
        price,
        ath,
    )

    if pullbacks:

        rows = []

        for pb in pullbacks:

            rows.append(
                [
                    f"−{pb['level']}%",
                    pb["price"],
                    price - pb["price"],
                ]
            )

        st.dataframe(
            pd.DataFrame(
                rows,
                columns=[
                    "Pullback",
                    "Target Price",
                    "Distance From Current",
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader(
        "System Interpretation"
    )

    st.write(
        "The system evaluates the market through five analytical layers:"
    )

    st.markdown(
        """
        1. **Macro Regime**
        2. **Early Warning**
        3. **Technical Confirmation**
        4. **Drawdown / Pullback**
        5. **Fed Intelligence**
        """
    )

    st.caption(
        "Fed Intelligence is currently an independent analytical layer "
        "and does not automatically modify the final decision."
    )

    st.caption(
        "Drawdown depth alone never creates a buy signal."
    )


# ============================================================
# EARLY WARNING TAB
# ============================================================

with tab_early:

    st.subheader(
        "⚠️ Early Warning System"
    )

    col1, col2 = st.columns(2)

    with col1:

        st.metric(
            "Early Warning Score",
            f"{ew_score}/100",
        )

    with col2:

        st.metric(
            "Risk Level",
            ew_level,
        )

    st.progress(
        ew_score / 100
    )

    st.divider()

    st.subheader(
        "Component Breakdown"
    )

    component_rows = []

    for name, value in ew_info[
        "components"
    ].items():

        maximum = ew_info[
            "max_components"
        ][name]

        component_rows.append(
            [
                name,
                value,
                maximum,
                f"{value}/{maximum}",
            ]
        )

    st.dataframe(
        pd.DataFrame(
            component_rows,
            columns=[
                "Component",
                "Score",
                "Maximum",
                "Score / Maximum",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Current Warning Indicators"
    )

    indicator_rows = []

    for name, value in ew_info[
        "indicators"
    ].items():

        if value is None:

            display_value = "N/A"

        elif isinstance(value, float) and np.isnan(value):

            display_value = "N/A"

        elif isinstance(value, (int, float)):

            display_value = f"{value:.3f}"

        else:

            display_value = str(value)

        indicator_rows.append(
            [
                name,
                display_value,
            ]
        )

    st.dataframe(
        pd.DataFrame(
            indicator_rows,
            columns=[
                "Indicator",
                "Current Value",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Why is Early Warning at this level?"
    )

    for reason in ew_info[
        "reasons"
    ]:

        st.write(
            f"• {reason}"
        )

    st.divider()

    st.subheader(
        "Risk Interpretation"
    )

    interpretation = pd.DataFrame(
        [
            [
                "0–24",
                "LOW",
                "No significant systemic warning.",
            ],
            [
                "25–49",
                "MODERATE",
                "Leading indicators require caution.",
            ],
            [
                "50–74",
                "HIGH",
                "Meaningful deterioration is present.",
            ],
            [
                "75–100",
                "CRITICAL",
                "Systemic stress. No new trade.",
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
# TECHNICAL TAB
# ============================================================

with tab_technical:

    st.subheader(
        "📈 Technical Confirmation"
    )

    st.caption(
        "Daily technical structure is used as a confirmation filter, "
        "not as an automatic execution signal."
    )

    c1, c2 = st.columns(2)

    with c1:

        st.metric(
            "Technical Score",
            f"{technical_score}/5",
        )

    with c2:

        st.metric(
            "Technical Status",
            technical_status,
        )

    st.progress(
        technical_score / 5
    )

    st.divider()

    st.subheader(
        "Technical Factors"
    )

    technical_rows = []

    for factor in technical_info[
        "factors"
    ]:

        technical_rows.append(
            [
                factor["factor"],
                factor["status"],
                factor["value"],
            ]
        )

    if technical_rows:

        st.dataframe(
            pd.DataFrame(
                technical_rows,
                columns=[
                    "Factor",
                    "Status",
                    "Value",
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    st.subheader(
        "Daily Technical Values"
    )

    values = technical_info.get(
        "values",
        {}
    )

    if values:

        technical_values = pd.DataFrame(
            [
                [
                    "Close",
                    values.get(
                        "close",
                        np.nan
                    ),
                ],
                [
                    "SMA20",
                    values.get(
                        "sma20",
                        np.nan
                    ),
                ],
                [
                    "SMA50",
                    values.get(
                        "sma50",
                        np.nan
                    ),
                ],
                [
                    "SMA200",
                    values.get(
                        "sma200",
                        np.nan
                    ),
                ],
                [
                    "RSI(14)",
                    values.get(
                        "rsi14",
                        np.nan
                    ),
                ],
                [
                    "Recent Swing Low",
                    values.get(
                        "recent_low",
                        np.nan
                    ),
                ],
                [
                    "Previous Swing Low",
                    values.get(
                        "previous_low",
                        np.nan
                    ),
                ],
            ],
            columns=[
                "Indicator",
                "Value",
            ],
        )

        st.dataframe(
            technical_values,
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    if technical_status == "STRONG":

        st.success(
            "🟢 Technical confirmation is STRONG."
        )

    elif technical_status == "PARTIAL":

        st.warning(
            "🟡 Technical confirmation is PARTIAL."
        )

    elif technical_status == "WEAK":

        st.warning(
            "🟠 Technical confirmation is WEAK."
        )

    else:

        st.error(
            "Technical data is unavailable."
        )

    st.info(
        f"**Impact on final decision:** "
        f"{decision_info['reason']}"
    )


# ============================================================
# MACRO TAB
# ============================================================

with tab_macro:

    st.subheader(
        "🌐 Macro Intelligence"
    )

    st.write(
        f"**Macro Score:** {macro_score:+d}/10"
    )

    st.write(
        f"**Regime:** {regime}"
    )

    macro_rows = []

    macro_display = [
        (
            "US10Y",
            "10-Year Treasury"
        ),
        (
            "US2Y",
            "2-Year Treasury"
        ),
        (
            "T10Y2Y",
            "10Y − 2Y Yield Curve"
        ),
        (
            "VIX",
            "VIX"
        ),
        (
            "DXY",
            "Dollar Index"
        ),
        (
            "HY_SPREAD",
            "High Yield Spread"
        ),
        (
            "CORP_OAS",
            "Corporate OAS"
        ),
        (
            "NFCI",
            "Chicago Fed NFCI"
        ),
        (
            "INITIAL_CLAIMS_4W",
            "Initial Claims 4W"
        ),
        (
            "INDPRO",
            "Industrial Production"
        ),
        (
            "RETAIL",
            "Retail Sales"
        ),
        (
            "PCE",
            "PCE"
        ),
        (
            "CORE_PCE",
            "Core PCE"
        ),
        (
            "CPI",
            "CPI"
        ),
        (
            "UNRATE",
            "Unemployment Rate"
        ),
        (
            "FEDFUNDS",
            "Federal Funds Rate"
        ),
    ]

    for key, label in macro_display:

        value = latest(
            macro_data.get(key)
        )

        if np.isnan(value):

            display = "DATA UNAVAILABLE"

        else:

            display = f"{value:.4f}"

        macro_rows.append(
            [
                label,
                display,
            ]
        )

    st.dataframe(
        pd.DataFrame(
            macro_rows,
            columns=[
                "Indicator",
                "Latest",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    st.subheader(
        "Federal Reserve"
    )

    st.write(
        f"**Manual Fed Stance:** {fed_stance}"
    )

    st.write(
        "Official FOMC calendar:"
    )

    st.link_button(
        "Open Federal Reserve FOMC Calendar",
        FED_URL,
    )


# ============================================================
# FED INTELLIGENCE TAB
# ============================================================

with tab_fed:

    st.subheader(
        "🏛️ Fed Intelligence"
    )

    st.caption(
        "Automated analysis of FOMC communication, Minutes, "
        "Chair communication, SEP and Beige Book."
    )

    # --------------------------------------------------------
    # AVAILABILITY
    # --------------------------------------------------------

    fed_available = fed_get(
        "available",
        True,
    )

    if fed_available is False:

        st.error(
            "Fed Intelligence is currently unavailable."
        )

        st.code(
            str(
                fed_get(
                    "error",
                    "Unknown error."
                )
            )
        )

        st.stop()

    # --------------------------------------------------------
    # TOP FED INFORMATION
    # --------------------------------------------------------

    latest_fomc = fed_get(
        "latest_fomc",
        fed_get(
            "fomc_date",
            "N/A",
        ),
    )

    fed_chair = fed_get(
        "fed_chair",
        fed_get(
            "chair",
            "N/A",
        ),
    )

    statement_tone = fed_get(
        "statement_tone",
        "N/A",
    )

    minutes_tone = fed_get(
        "minutes_tone",
        "N/A",
    )

    press_tone = fed_get(
        "press_conference_tone",
        fed_get(
            "chair_tone",
            "N/A",
        ),
    )

    latest_sep = fed_get(
        "latest_sep",
        "N/A",
    )

    previous_sep = fed_get(
        "previous_sep",
        "N/A",
    )

    sep_shift = fed_get(
        "sep_shift",
        "N/A",
    )

    fed_score = fed_get(
        "fed_score",
        fed_get(
            "score",
            None,
        ),
    )

    fed_classification = fed_get(
        "overall_tone",
        fed_get(
            "classification",
            "N/A",
        ),
    )

    # --------------------------------------------------------
    # MAIN FED METRICS
    # --------------------------------------------------------

    fc1, fc2, fc3, fc4 = st.columns(4)

    with fc1:

        st.metric(
            "Fed Intelligence Score",
            (
                f"{safe_number(fed_score):.1f}/100"
                if safe_number(fed_score) is not None
                else "N/A"
            ),
        )

    with fc2:

        st.metric(
            "Overall Tone",
            str(
                fed_classification
            ),
        )

    with fc3:

        st.metric(
            "Latest FOMC",
            format_date(
                latest_fomc
            ),
        )

    with fc4:

        st.metric(
            "Fed Chair",
            str(
                fed_chair
            ),
        )

    st.divider()

    # --------------------------------------------------------
    # FOMC COMMUNICATION
    # --------------------------------------------------------

    st.subheader(
        "FOMC Communication"
    )

    communication_rows = [
        [
            "Statement",
            str(statement_tone),
        ],
        [
            "Minutes",
            str(minutes_tone),
        ],
        [
            "Chair / Press Conference",
            str(press_tone),
        ],
    ]

    st.dataframe(
        pd.DataFrame(
            communication_rows,
            columns=[
                "Source",
                "Tone",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.divider()

    # --------------------------------------------------------
    # POLICY DIMENSIONS
    # --------------------------------------------------------

    st.subheader(
        "Fed Policy Dimensions"
    )

    dimensions = fed_get(
        "dimensions",
        {},
    )

    if not isinstance(
        dimensions,
        dict
    ):

        dimensions = {}

    dimension_rows = []

    dimension_order = [
        (
            "inflation",
            "Inflation",
        ),
        (
            "labor",
            "Labor",
        ),
        (
            "growth",
            "Growth",
        ),
        (
            "financial",
            "Financial Conditions",
        ),
        (
            "policy",
            "Monetary Policy",
        ),
    ]

    for key, label in dimension_order:

        dimension = dimensions.get(
            key,
            {},
        )

        if not isinstance(
            dimension,
            dict
        ):

            dimension = {}

        score = dimension.get(
            "score_100",
            dimension.get(
                "score",
                None,
            ),
        )

        classification = dimension.get(
            "classification",
            dimension.get(
                "tone",
                None,
            ),
        )

        if classification is None:

            numeric_score = safe_number(
                score
            )

            if numeric_score is None:

                classification = "N/A"

            elif numeric_score >= 70:

                classification = "POSITIVE"

            elif numeric_score >= 55:

                classification = "SLIGHTLY POSITIVE"

            elif numeric_score >= 45:

                classification = "NEUTRAL"

            elif numeric_score >= 30:

                classification = "SLIGHTLY NEGATIVE"

            else:

                classification = "NEGATIVE"

        dimension_rows.append(
            [
                label,
                (
                    f"{safe_number(score):.1f}/100"
                    if safe_number(score) is not None
                    else "N/A"
                ),
                str(
                    classification
                ),
            ]
        )

    if dimension_rows:

        st.dataframe(
            pd.DataFrame(
                dimension_rows,
                columns=[
                    "Dimension",
                    "Score",
                    "Classification",
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

    else:

        st.info(
            "No policy-dimension data available."
        )

    st.divider()

    # --------------------------------------------------------
    # SEP
    # --------------------------------------------------------

    st.subheader(
        "📊 Summary of Economic Projections"
    )

    sep_col1, sep_col2 = st.columns(2)

    with sep_col1:

        st.write(
            f"**Latest SEP:** {latest_sep}"
        )

    with sep_col2:

        st.write(
            f"**Previous SEP:** {previous_sep}"
        )

    st.write(
        f"**SEP Shift:** {sep_shift}"
    )

    sep_data = fed_get(
        "sep",
        {},
    )

    if not isinstance(
        sep_data,
        dict
    ):

        sep_data = {}

    previous_sep_data = fed_get(
        "previous_sep_data",
        fed_get(
            "sep_previous",
            {},
        ),
    )

    if not isinstance(
        previous_sep_data,
        dict
    ):

        previous_sep_data = {}

    sep_rows = []

    sep_keys = [
        (
            "gdp",
            "GDP Growth",
        ),
        (
            "unemployment",
            "Unemployment",
        ),
        (
            "pce",
            "PCE Inflation",
        ),
        (
            "core_pce",
            "Core PCE",
        ),
        (
            "fed_funds",
            "Federal Funds Rate",
        ),
    ]

    for key, label in sep_keys:

        current_value = sep_data.get(
            key,
            None,
        )

        previous_value = previous_sep_data.get(
            key,
            None,
        )

        current_number = safe_number(
            current_value
        )

        previous_number = safe_number(
            previous_value
        )

        if (
            current_number is not None
            and previous_number is not None
        ):

            change = (
                current_number
                - previous_number
            )

        else:

            change = None

        sep_rows.append(
            [
                label,
                (
                    f"{current_number:.1f}"
                    if current_number is not None
                    else "N/A"
                ),
                (
                    f"{previous_number:.1f}"
                    if previous_number is not None
                    else "N/A"
                ),
                (
                    f"{change:+.1f}"
                    if change is not None
                    else "N/A"
                ),
            ]
        )

    if sep_rows:

        st.dataframe(
            pd.DataFrame(
                sep_rows,
                columns=[
                    "Indicator",
                    "Latest SEP",
                    "Previous SEP",
                    "Change",
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

    st.divider()

    # --------------------------------------------------------
    # BEIGE BOOK
    # --------------------------------------------------------

    st.subheader(
        "📕 Beige Book"

    )

    beige = fed_get(
        "beige_book",
        fed_get(
            "beige",
            {},
        ),
    )

    if not isinstance(
        beige,
        dict
    ):

        beige = {}

    beige_title = beige.get(
        "title",
        beige.get(
            "name",
            "N/A",
        ),
    )

    beige_issue = beige.get(
        "issue",
        beige.get(
            "issue_date",
            "N/A",
        ),
    )

    beige_publication = beige.get(
        "publication",
        beige.get(
            "publication_date",
            "N/A",
        ),
    )

    beige_score = beige.get(
        "score",
        beige.get(
            "score_100",
            None,
        ),
    )

    beige_tone = beige.get(
        "tone",
        beige.get(
            "classification",
            "N/A",
        ),
    )

    bc1, bc2, bc3, bc4 = st.columns(4)

    with bc1:

        st.write(
            "**Beige Book**"
        )

        st.write(
            str(
                beige_title
            )
        )

    with bc2:

        st.write(
            "**Issue**"
        )

        st.write(
            str(
                beige_issue
            )
        )

    with bc3:

        st.write(
            "**Publication**"
        )

        st.write(
            str(
                beige_publication
            )
        )

    with bc4:

        st.write(
            "**Score / Tone**"
        )

        if safe_number(
            beige_score
        ) is not None:

            st.write(
                f"{safe_number(beige_score):.1f}/100"
            )

        else:

            st.write(
                "N/A"
            )

        st.write(
            str(
                beige_tone
            )
        )

    beige_dimensions = beige.get(
        "dimensions",
        {},
    )

    if not isinstance(
        beige_dimensions,
        dict
    ):

        beige_dimensions = {}

    beige_rows = []

    beige_order = [
        (
            "growth",
            "Growth",
        ),
        (
            "labor",
            "Labor",
        ),
        (
            "inflation",
            "Inflation",
        ),
        (
            "consumer",
            "Consumer Spending",
        ),
        (
            "manufacturing",
            "Manufacturing",
        ),
        (
            "financial",
            "Financial Conditions",
        ),
        (
            "housing",
            "Housing",
        ),
    ]

    for key, label in beige_order:

        item = beige_dimensions.get(
            key,
            {},
        )

        if not isinstance(
            item,
            dict
        ):

            item = {}

        score = item.get(
            "score_100",
            item.get(
                "score",
                None,
            ),
        )

        classification = item.get(
            "classification",
            item.get(
                "tone",
                None,
            ),
        )

        if classification is None:

            numeric_score = safe_number(
                score
            )

            if numeric_score is None:

                classification = "N/A"

            elif numeric_score >= 70:

                classification = "POSITIVE"

            elif numeric_score >= 55:

                classification = "SLIGHTLY POSITIVE"

            elif numeric_score >= 45:

                classification = "NEUTRAL"

            elif numeric_score >= 30:

                classification = "SLIGHTLY NEGATIVE"

            else:

                classification = "NEGATIVE"

        beige_rows.append(
            [
                label,
                (
                    f"{safe_number(score):.1f}/100"
                    if safe_number(score) is not None
                    else "N/A"
                ),
                str(
                    classification
                ),
            ]
        )

    if beige_rows:

        st.dataframe(
            pd.DataFrame(
                beige_rows,
                columns=[
                    "Dimension",
                    "Score",
                    "Classification",
                ],
            ),
            use_container_width=True,
            hide_index=True,
        )

    # --------------------------------------------------------
    # FED REASONS
    # --------------------------------------------------------

    st.divider()

    st.subheader(
        "🧠 Fed Intelligence Reasons"
    )

    reasons = fed_get(
        "reasons",
        [],
    )

    if reasons is None:

        reasons = []

    if isinstance(
        reasons,
        dict
    ):

        for key, value in reasons.items():

            st.write(
                f"• **{key}:** {display_reason(value)}"
            )

    elif isinstance(
        reasons,
        list
    ):

        if reasons:

            for reason in reasons:

                if isinstance(
                    reason,
                    dict
                ):

                    dimension = reason.get(
                        "dimension",
                        "",
                    )

                    text = reason.get(
                        "reason",
                        reason.get(
                            "text",
                            "",
                        ),
                    )

                    st.write(
                        f"• **{dimension}:** "
                        f"{display_reason(text)}"
                    )

                else:

                    st.write(
                        f"• {display_reason(reason)}"
                    )

        else:

            st.info(
                "No additional reasons returned."
            )

    else:

        st.write(
            f"• {display_reason(reasons)}"
        )

    # --------------------------------------------------------
    # IMPORTANT ARCHITECTURE NOTE
    # --------------------------------------------------------

    st.divider()

    st.warning(
        """
        **Important architecture rule**

        Fed Intelligence is currently an independent analytical layer.

        It does **not** automatically modify:

        - Final Decision
        - Early Warning Score
        - Technical Confirmation
        - Position Size
        - SL / TP

        This is intentional. We should first validate the Fed Intelligence
        model through historical event studies and backtesting before
        allowing it to influence the trading engine.
        """
    )


# ============================================================
# TRADING TAB
# ============================================================

with tab_trading:

    st.subheader(
        "🎯 Trading Framework"
    )

    st.caption(
        "This section calculates hypothetical levels only. "
        "No order is sent to a broker."
    )

    st.write(
        "**Strategy:** Daily US500 pullback swing"
    )

    st.write(
        "**Risk/Reward:** 1 : 4"
    )

    st.write(
        "**Stop:** Lowest Low of previous 5 completed Daily candles "
        "− 0.5 × ATR(14)"
    )

    st.write(
        "**TP:** Entry + 4 × Risk"
    )

    st.divider()

    st.subheader(
        "Entry / SL / TP Calculator"
    )

    entry = st.number_input(
        "Entry",
        min_value=0.0,
        value=float(price),
        step=1.0,
    )

    risk_dollars = st.number_input(
        "Risk in USD",
        min_value=1.0,
        value=250.0,
        step=50.0,
    )

    point_value = st.number_input(
        "Point Value",
        min_value=0.0001,
        value=1.0,
        step=0.1,
        help=(
            "Set according to your broker/instrument specification."
        ),
    )

    sl, tp, risk_points = sl_tp(
        market,
        entry,
    )

    if (
        not np.isnan(sl)
        and not np.isnan(tp)
        and risk_points > 0
    ):

        c1, c2, c3 = st.columns(3)

        with c1:

            st.metric(
                "Entry",
                f"{entry:.2f}",
            )

        with c2:

            st.metric(
                "Stop Loss",
                f"{sl:.2f}",
            )

        with c3:

            st.metric(
                "Take Profit 1:4",
                f"{tp:.2f}",
            )

        st.write(
            f"**Price Risk:** {risk_points:.2f} points"
        )

        quantity = position_size(
            risk_dollars,
            entry,
            sl,
            point_value,
        )

        if not np.isnan(quantity):

            st.metric(
                "Calculated Position Size",
                f"{quantity:.4f}",
            )

            st.caption(
                "Position size is generic. "
                "For futures/CFDs, verify the broker's contract "
                "size and point value before using it."
            )

    else:

        st.warning(
            "Unable to calculate SL/TP from the available data."
        )

    st.divider()

    st.subheader(
        "Pullback Decision"
    )

    if ew_score >= 75:

        st.error(
            "CRITICAL: No new trade."
        )

    elif regime.startswith("E"):

        st.error(
            "DEFENSIVE: Recession / bear risk."
        )

    elif regime.startswith("F"):

        st.error(
            "DEFENSIVE: Financial/liquidity shock."
        )

    elif technical_score <= 2:

        st.warning(
            "CAUTION: Technical confirmation is weak."
        )

    elif technical_score == 3:

        st.warning(
            "SUPPORTIVE / CONFIRM: Technical structure is partial."
        )

    else:

        st.success(
            "Technical confirmation is strong."
        )


# ============================================================
# EVENTS TAB
# ============================================================

with tab_events:

    st.subheader(
        "📅 Macro Events"
    )

    st.info(
        "The current version uses the latest available macro "
        "observations. A dedicated economic-calendar parser can "
        "be added later without changing the decision framework."
    )

    event_rows = [

        [
            "Federal Reserve",
            "FOMC",
            "See official calendar",
        ],

        [
            "Inflation",
            "CPI / Core CPI",
            "BLS release",
        ],

        [
            "Inflation",
            "PCE / Core PCE",
            "BEA release",
        ],

        [
            "Labor",
            "NFP",
            "BLS release",
        ],

        [
            "Labor",
            "Initial Claims",
            "Weekly",
        ],

        [
            "Growth",
            "GDP",
            "BEA release",
        ],

        [
            "Growth",
            "ISM",
            "ISM release",
        ],
    ]

    st.dataframe(
        pd.DataFrame(
            event_rows,
            columns=[
                "Category",
                "Event",
                "Status",
            ],
        ),
        use_container_width=True,
        hide_index=True,
    )

    st.caption(
        "Actual / Forecast / Previous should only be displayed "
        "when a verified economic-calendar source is connected."
    )


# ============================================================
# HISTORY TAB
# ============================================================

with tab_history:

    st.subheader(
        "📚 Historical Framework"
    )

    st.write(
        "The historical event-study module is intentionally "
        "kept separate from the live decision engine."
    )

    st.write(
        "Target historical analysis:"
    )

    st.markdown(
        """
        - Pullback date
        - Reference high
        - Drawdown
        - Trough
        - Recovery date
        - Recovery duration
        - Macro regime
        - Early Warning score
        - VIX
        - 10Y / 2Y
        - Credit spreads
        - ISM
        - Initial Claims
        - Inflation
        - Fed stance
        - Fed Intelligence
        - FOMC Statement
        - FOMC Minutes
        - SEP Shift
        - Beige Book
        - 1:4 TP result
        - Stop result
        - R multiple
        - Maximum drawdown
        - Recovery time
        """
    )

    st.divider()

    st.subheader(
        "Current Snapshot"
    )

    history_snapshot = pd.DataFrame(
        [
            [
                datetime.utcnow().strftime(
                    "%Y-%m-%d %H:%M UTC"
                ),
                price,
                ath,
                drawdown,
                macro_score,
                regime,
                ew_score,
                ew_level,
                technical_score,
                technical_status,
                final_decision,
            ]
        ],
        columns=[
            "Timestamp",
            "US500",
            "ATH",
            "Drawdown %",
            "Macro Score",
            "Regime",
            "Early Warning",
            "EW Level",
            "Technical",
            "Technical Status",
            "Decision",
        ],
    )

    st.dataframe(
        history_snapshot,
        use_container_width=True,
        hide_index=True,
    )

    st.info(
        "Historical probabilities and win rates should not be "
        "assumed until the event-study/backtest is completed."
    )


# ============================================================
# FOOTER
# ============================================================

st.divider()

st.caption(
    f"{APP_NAME} | Daily Macro + Early Warning + Technical "
    f"+ Fed Intelligence Decision Support | "
    f"Data refresh: {REFRESH_MINUTES} min"
)

st.caption(
    "Market proxy: Yahoo Finance S&P 500 (^GSPC). "
    "It may differ from a broker's US500 CFD or futures feed."
)
