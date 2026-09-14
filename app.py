import os
import streamlit as st
import pandas as pd
import numpy as np

from datetime import date, datetime

from config import MARKET_TICKER, FRED_API_KEY, REFRESH_MINUTES
from data import fred_all, bls_all, market, fomc_page, parse_fomc

from engine import (
    latest,
    state,
    analyze,
    warnings,
    classify,
    sl_tp,
    PULLBACKS,
)

from db import init, save_snapshot, save_alert, history, alerts


# ============================================================
# PAGE
# ============================================================

st.set_page_config(
    page_title="US500 Macro Intelligence PRODUCTION",
    layout="wide"
)

init()

st.title("US500 Macro Intelligence — PRODUCTION")

st.caption(
    "Macro → Early Warning → Regime → Pullback → Risk/Reward | Decision support only"
)


# ============================================================
# SAFE DATA HELPERS
# ============================================================

def safe_value(x):

    try:

        if x is None or len(x) == 0:
            return np.nan

        value = float(x.iloc[-1]["value"])

        if np.isnan(value):
            return np.nan

        return value

    except Exception:

        return np.nan


def safe_delta(x, n=1):

    try:

        if x is None or len(x) <= n:
            return np.nan

        a = float(x.iloc[-1]["value"])
        b = float(x.iloc[-1-n]["value"])

        if np.isnan(a) or np.isnan(b):
            return np.nan

        return a - b

    except Exception:

        return np.nan


def safe_pct_change(x, n=1):

    try:

        if x is None or len(x) <= n:
            return np.nan

        a = float(x.iloc[-1]["value"])
        b = float(x.iloc[-1-n]["value"])

        if np.isnan(a) or np.isnan(b) or b == 0:
            return np.nan

        return (a / b - 1) * 100

    except Exception:

        return np.nan


# ============================================================
# EARLY WARNING ENGINE
# ============================================================

def early_warning(f):

    scores = {
        "Credit": 0,
        "Labor": 0,
        "Yield Curve": 0,
        "Financial Conditions": 0,
        "Market Risk": 0,
        "Macro Momentum": 0,
    }

    reasons = []


    # --------------------------------------------------------
    # CREDIT
    # --------------------------------------------------------

    hy = safe_value(f.get("HY_SPREAD"))

    if not np.isnan(hy):

        if hy >= 6:
            scores["Credit"] += 12
            reasons.append(
                "HY credit spread is at a severe stress level."
            )

        elif hy >= 5:
            scores["Credit"] += 9
            reasons.append(
                "HY credit spread is significantly elevated."
            )

        elif hy >= 4:
            scores["Credit"] += 5
            reasons.append(
                "HY credit spread is elevated."
            )


    hy_change = safe_pct_change(
        f.get("HY_SPREAD"),
        60
    )

    if not np.isnan(hy_change):

        if hy_change >= 30:
            scores["Credit"] += 8
            reasons.append(
                "HY spread has widened sharply."
            )

        elif hy_change >= 15:
            scores["Credit"] += 5
            reasons.append(
                "HY spread is widening."
            )

        elif hy_change >= 8:
            scores["Credit"] += 3
            reasons.append(
                "HY spread shows increasing stress."
            )


    corp = safe_value(
        f.get("CORP_OAS")
    )

    if not np.isnan(corp):

        if corp >= 3:
            scores["Credit"] += 5
            reasons.append(
                "Corporate OAS is highly elevated."
            )

        elif corp >= 2.5:
            scores["Credit"] += 3
            reasons.append(
                "Corporate OAS is elevated."
            )


    scores["Credit"] = min(
        scores["Credit"],
        20
    )


    # --------------------------------------------------------
    # LABOR
    # --------------------------------------------------------

    claims = safe_pct_change(
        f.get("INITIAL_CLAIMS_4W"),
        12
    )

    if not np.isnan(claims):

        if claims >= 8:
            scores["Labor"] += 12
            reasons.append(
                "Initial claims trend is deteriorating materially."
            )

        elif claims >= 5:
            scores["Labor"] += 8
            reasons.append(
                "Initial claims trend is weakening."
            )

        elif claims >= 3:
            scores["Labor"] += 4
            reasons.append(
                "Initial claims show early deterioration."
            )


    unemployment = safe_delta(
        f.get("UNRATE"),
        3
    )

    if not np.isnan(unemployment):

        if unemployment >= 0.2:
            scores["Labor"] += 8
            reasons.append(
                "Unemployment has risen materially."
            )

        elif unemployment >= 0.1:
            scores["Labor"] += 4
            reasons.append(
                "Unemployment is trending higher."
            )


    scores["Labor"] = min(
        scores["Labor"],
        20
    )


    # --------------------------------------------------------
    # YIELD CURVE
    # --------------------------------------------------------

    curve = safe_value(
        f.get("T10Y2Y")
    )

    if not np.isnan(curve):

        if curve < -0.50:
            scores["Yield Curve"] += 10
            reasons.append(
                "Yield curve is deeply inverted."
            )

        elif curve < 0:
            scores["Yield Curve"] += 7
            reasons.append(
                "Yield curve remains inverted."
            )


    curve_change = safe_delta(
        f.get("T10Y2Y"),
        60
    )

    if not np.isnan(curve_change):

        if curve_change <= -0.50:
            scores["Yield Curve"] += 5
            reasons.append(
                "Yield curve has deteriorated significantly."
            )

        elif curve_change <= -0.25:
            scores["Yield Curve"] += 3
            reasons.append(
                "Yield curve is becoming less supportive."
            )


    scores["Yield Curve"] = min(
        scores["Yield Curve"],
        15
    )


    # --------------------------------------------------------
    # FINANCIAL CONDITIONS
    # --------------------------------------------------------

    nfci = safe_value(
        f.get("NFCI")
    )

    if not np.isnan(nfci):

        if nfci >= 1:
            scores["Financial Conditions"] += 12
            reasons.append(
                "Financial conditions are severely tight."
            )

        elif nfci >= 0.5:
            scores["Financial Conditions"] += 8
            reasons.append(
                "Financial conditions are materially tight."
            )

        elif nfci > 0:
            scores["Financial Conditions"] += 4
            reasons.append(
                "Financial conditions are tighter than average."
            )


    nfci_change = safe_delta(
        f.get("NFCI"),
        4
    )

    if not np.isnan(nfci_change):

        if nfci_change >= 0.30:
            scores["Financial Conditions"] += 8
            reasons.append(
                "Financial conditions are tightening rapidly."
            )

        elif nfci_change >= 0.15:
            scores["Financial Conditions"] += 5
            reasons.append(
                "Financial conditions are tightening."
            )

        elif nfci_change >= 0.08:
            scores["Financial Conditions"] += 2
            reasons.append(
                "Financial conditions show early tightening."
            )


    scores["Financial Conditions"] = min(
        scores["Financial Conditions"],
        20
    )


    # --------------------------------------------------------
    # MARKET RISK
    # --------------------------------------------------------

    vix = safe_value(
        f.get("VIX")
    )

    if not np.isnan(vix):

        if vix >= 35:
            scores["Market Risk"] += 15
            reasons.append(
                "VIX is at a severe risk level."
            )

        elif vix >= 30:
            scores["Market Risk"] += 10
            reasons.append(
                "VIX is highly elevated."
            )

        elif vix >= 25:
            scores["Market Risk"] += 6
            reasons.append(
                "VIX is elevated."
            )

        elif vix >= 20:
            scores["Market Risk"] += 3
            reasons.append(
                "VIX is above the normal low-risk zone."
            )


    vix_change = safe_pct_change(
        f.get("VIX"),
        20
    )

    if not np.isnan(vix_change):

        if vix_change >= 50:
            scores["Market Risk"] += 5
            reasons.append(
                "VIX has risen sharply."
            )

        elif vix_change >= 25:
            scores["Market Risk"] += 3
            reasons.append(
                "VIX is rising significantly."
            )


    dxy_change = safe_pct_change(
        f.get("DXY"),
        60
    )

    if not np.isnan(dxy_change):

        if dxy_change >= 8:
            scores["Market Risk"] += 3
            reasons.append(
                "DXY has strengthened materially."
            )

        elif dxy_change >= 5:
            scores["Market Risk"] += 2
            reasons.append(
                "DXY is showing a strong upward trend."
            )


    scores["Market Risk"] = min(
        scores["Market Risk"],
        15
    )


    # --------------------------------------------------------
    # MACRO MOMENTUM
    # --------------------------------------------------------

    indpro = safe_pct_change(
        f.get("INDPRO"),
        3
    )

    if not np.isnan(indpro) and indpro < 0:

        scores["Macro Momentum"] += 3

        reasons.append(
            "Industrial production momentum is weakening."
        )


    retail = safe_pct_change(
        f.get("RETAIL"),
        3
    )

    if not np.isnan(retail) and retail < 0:

        scores["Macro Momentum"] += 3

        reasons.append(
            "Retail sales momentum is weakening."
        )


    pce = safe_pct_change(
        f.get("PCE"),
        3
    )

    if not np.isnan(pce) and pce > 0:

        scores["Macro Momentum"] += 4

        reasons.append(
            "PCE trend is accelerating."
        )


    scores["Macro Momentum"] = min(
        scores["Macro Momentum"],
        10
    )


    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total = int(
        sum(scores.values())
    )


    if total <= 24:

        level = "LOW"

    elif total <= 49:

        level = "MODERATE"

    elif total <= 74:

        level = "HIGH"

    else:

        level = "CRITICAL"


    return {
        "score": total,
        "level": level,
        "reasons": reasons,
        "details": scores,
    }


# ============================================================
# DECISION ENGINE
# ============================================================

def decision_engine(
    early_score,
    early_level,
    macro_score,
    regime,
    drawdown
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
            )
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
            )
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
            )
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
            )
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
            )
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
            )
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
            )
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
            )
        }


    # --------------------------------------------------------
    # MODERATE DRAWDOWN
    # --------------------------------------------------------

    if drawdown <= -10:

        return {
            "decision": "SUPPORTIVE / CONFIRM",
            "color": "green",
            "reason": (
                "Macro conditions remain relatively supportive, "
                "but the depth of the correction requires confirmation."
            )
        }


    # --------------------------------------------------------
    # NORMAL PULLBACK
    # --------------------------------------------------------

    if early_score < 25 and macro_score >= 3:

        return {
            "decision": "SUPPORTIVE",
            "color": "green",
            "reason": (
                "Macro conditions are supportive and "
                "early-warning stress remains low."
            )
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
        )
    }


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:

    key = st.text_input(
        "FRED API key",
        value=FRED_API_KEY,
        type="password",
        help="يمكن حفظه في Streamlit Secrets باسم FRED_API_KEY."
    )

    start = st.date_input(
        "History start",
        date(2015, 1, 1)
    )

    fed = st.selectbox(
        "Fed stance (temporary manual input)",
        [
            "Neutral",
            "Dovish",
            "Hawkish"
        ]
    )

    if st.button(
        "REFRESH NOW",
        type="primary"
    ):

        st.session_state.force = True

    st.caption(
        f"Market feed: {MARKET_TICKER} | Refresh target: {REFRESH_MINUTES} min"
    )


# ============================================================
# DATA
# ============================================================

if (
    "force" in st.session_state
    or "f" not in st.session_state
):

    if not key:

        st.info(
            "ضع FRED_API_KEY في Secrets/Environment أو أدخل المفتاح هنا ثم REFRESH NOW."
        )

        st.stop()


    try:

        with st.spinner(
            "Updating official macro + market data..."
        ):

            st.session_state.f = fred_all(
                key,
                start
            )

            st.session_state.b = bls_all(
                start.year,
                date.today().year
            )

            st.session_state.m = market(
                start
            )

            st.session_state.ts = datetime.now()

            st.session_state.fomc = parse_fomc(
                fomc_page()
            )


        st.session_state.pop(
            "force",
            None
        )


    except Exception as e:

        st.error(
            f"Update failed: {e}"
        )

        st.stop()


# ============================================================
# ENGINE
# ============================================================

f = st.session_state.f

m = st.session_state.m


price, ath, dd, atr = state(m)


score, reg, meta = analyze(
    f,
    fed
)


w = warnings(
    f,
    score
)


pb = classify(
    dd,
    score,
    reg
)


# EARLY WARNING

ew = early_warning(
    f
)


ew_score = ew["score"]

ew_level = ew["level"]


# DECISION ENGINE

final_decision = decision_engine(
    ew_score,
    ew_level,
    score,
    reg,
    dd
)


dec = final_decision["decision"]


# ============================================================
# DATABASE
# ============================================================

save_snapshot(
    (
        st.session_state.ts.isoformat(),
        price,
        ath,
        dd,
        score,
        reg,
        dec,
        str(meta)
    )
)


if score <= -3:

    save_alert(
        "MACRO",
        f"Macro score {score}: {reg}"
    )


if dd <= -10:

    save_alert(
        "DRAWDOWN",
        f"US500 drawdown {dd:.2f}%"
    )


if ew_score >= 50:

    save_alert(
        "EARLY_WARNING",
        f"Early Warning {ew_score}/100 — {ew_level}"
    )


# ============================================================
# DASHBOARD
# ============================================================

cols = st.columns(8)


dashboard = [

    (
        "US500",
        f"{price:.2f}"
    ),

    (
        "ATH",
        f"{ath:.2f}"
    ),

    (
        "Drawdown",
        f"{dd:.2f}%"
    ),

    (
        "Macro",
        f"{score:+d}/10"
    ),

    (
        "Regime",
        reg.split("—")[0].strip()
    ),

    (
        "Pullback",
        pb.split("—")[0].strip()
    ),

    (
        "Early Warning",
        f"{ew_score}/100"
    ),

    (
        "Decision",
        dec
    ),
]


for c, (label, value) in zip(
    cols,
    dashboard
):

    c.metric(
        label,
        value
    )


# ============================================================
# DECISION BANNER
# ============================================================

if (
    dec == "CRITICAL — NO NEW TRADE"
):

    st.error(
        "🚨 CRITICAL — NO NEW TRADE"
    )

    st.write(
        final_decision["reason"]
    )


elif (
    dec == "DEFENSIVE"
):

    st.error(
        "🔴 DEFENSIVE — لا نفترض أن الهبوط فرصة شراء."
    )

    st.write(
        final_decision["reason"]
    )


elif (
    dec == "WAIT / CONFIRM"
    or dec == "SUPPORTIVE / CONFIRM"
):

    st.warning(
        f"🟡 {dec}"
    )

    st.write(
        final_decision["reason"]
    )


elif (
    dec == "CAUTION"
):

    st.warning(
        "🟠 CAUTION"
    )

    st.write(
        final_decision["reason"]
    )


else:

    st.success(
        "🟢 SUPPORTIVE"
    )

    st.write(
        final_decision["reason"]
    )


# ============================================================
# TABS
# ============================================================

t1, t2, t3, t4, t5, t6 = st.tabs(
    [
        "LIVE",
        "EARLY WARNING",
        "MACRO",
        "TRADING",
        "EVENTS",
        "HISTORY",
    ]
)


# ============================================================
# LIVE
# ============================================================

with t1:

    st.subheader(
        "الخلاصة التنفيذية"
    )

    st.write(
        f"**Macro Regime:** {reg}"
    )

    st.write(
        f"**Pullback:** {pb}"
    )

    st.write(
        f"**Early Warning:** {ew_score}/100 — {ew_level}"
    )

    st.write(
        f"**Final Decision:** {dec}"
    )

    st.write(
        f"**Why:** "
        f"Macro score={score:+d}, "
        f"Drawdown={dd:.2f}%, "
        f"VIX={meta['vix']:.2f}, "
        f"HY spread={meta['credit']:.2f}"
    )

    st.divider()

    st.subheader(
        "لماذا اتخذ النظام هذا القرار؟"
    )

    st.write(
        final_decision["reason"]
    )

    st.divider()

    st.write(
        "**الفلسفة:**"
    )

    st.write(
        "Drawdown + Macro Regime + Early Warning + Technical Structure = Trading Decision"
    )


# ============================================================
# EARLY WARNING
# ============================================================

with t2:

    st.subheader(
        "🚨 Early Warning Score"
    )

    c1, c2 = st.columns(2)

    c1.metric(
        "Score",
        f"{ew_score}/100"
    )

    c2.metric(
        "Risk Level",
        ew_level
    )

    st.progress(
        min(
            ew_score,
            100
        ) / 100
    )

    st.divider()

    st.subheader(
        "Component Breakdown"
    )

    maximums = {
        "Credit": 20,
        "Labor": 20,
        "Yield Curve": 15,
        "Financial Conditions": 20,
        "Market Risk": 15,
        "Macro Momentum": 10,
    }

    rows = []

    for name, value in ew["details"].items():

        maximum = maximums[name]

        rows.append(
            [
                name,
                value,
                maximum,
                f"{value / maximum * 100:.0f}%"
            ]
        )


    st.dataframe(
        pd.DataFrame(
            rows,
            columns=[
                "Component",
                "Score",
                "Maximum",
                "Stress"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )


    st.divider()

    st.subheader(
        "Current Warning Indicators"
    )

    indicators = [

        (
            "HY Spread",
            "HY_SPREAD"
        ),

        (
            "Corporate OAS",
            "CORP_OAS"
        ),

        (
            "Initial Claims 4W",
            "INITIAL_CLAIMS_4W"
        ),

        (
            "Unemployment",
            "UNRATE"
        ),

        (
            "10Y-2Y Yield Curve",
            "T10Y2Y"
        ),

        (
            "NFCI",
            "NFCI"
        ),

        (
            "VIX",
            "VIX"
        ),

        (
            "DXY",
            "DXY"
        ),

        (
            "Industrial Production",
            "INDPRO"
        ),

        (
            "Retail Sales",
            "RETAIL"
        ),

        (
            "PCE",
            "PCE"
        ),
    ]


    indicator_rows = []


    for name, key_name in indicators:

        indicator_rows.append(
            [
                name,
                safe_value(
                    f.get(key_name)
                )
            ]
        )


    st.dataframe(
        pd.DataFrame(
            indicator_rows,
            columns=[
                "Indicator",
                "Latest"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )


    st.divider()

    st.subheader(
        "Why is the warning score rising?"
    )


    if ew["reasons"]:

        for reason in ew["reasons"]:

            st.warning(
                f"⚠️ {reason}"
            )

    else:

        st.success(
            "No significant early-warning cluster detected."
        )


    st.divider()

    st.subheader(
        "Interpretation"
    )


    st.dataframe(
        pd.DataFrame(
            [
                [
                    "0–24",
                    "LOW",
                    "Normal monitoring."
                ],

                [
                    "25–49",
                    "MODERATE",
                    "Early deterioration."
                ],

                [
                    "50–74",
                    "HIGH",
                    "Multiple risk indicators align."
                ],

                [
                    "75–100",
                    "CRITICAL",
                    "Potential systemic/regime stress."
                ],
            ],
            columns=[
                "Score",
                "Level",
                "Meaning"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# MACRO
# ============================================================

with t3:

    rows = []


    for n, k in [

        ("10Y", "US10Y"),

        ("2Y", "US2Y"),

        ("10Y-2Y", "T10Y2Y"),

        ("VIX", "VIX"),

        ("DXY", "DXY"),

        ("PCE", "PCE"),

        ("Core PCE", "CORE_PCE"),

        ("Unemployment", "UNRATE"),

        ("Initial Claims 4W", "INITIAL_CLAIMS_4W"),

        ("HY Spread", "HY_SPREAD"),

        ("Corporate OAS", "CORP_OAS"),

        ("NFCI", "NFCI"),

        ("Industrial Production", "INDPRO"),

        ("Retail Sales", "RETAIL"),

    ]:

        rows.append(
            [
                n,
                safe_value(
                    f.get(k)
                )
            ]
        )


    st.dataframe(
        pd.DataFrame(
            rows,
            columns=[
                "Indicator",
                "Latest"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# TRADING
# ============================================================

with t4:

    st.subheader(
        "Trading Decision Support"
    )

    st.metric(
        "Final Decision",
        dec
    )

    st.write(
        final_decision["reason"]
    )


    if ew_score >= 50:

        st.error(
            "⚠️ Early Warning ≥ 50 — الحذر مرتفع."
        )


    entry = st.number_input(
        "Entry price",
        value=float(price),
        step=1.0
    )


    sl, tp, risk = sl_tp(
        m,
        entry
    )


    c1, c2, c3 = st.columns(3)


    c1.metric(
        "Entry",
        f"{entry:.2f}"
    )

    c2.metric(
        "SL",
        f"{sl:.2f}"
    )

    c3.metric(
        "TP 1:4",
        f"{tp:.2f}"
    )


    st.write(
        f"Risk points: **{risk:.2f}**"
    )


    st.code(
        "SL = Lowest Low of previous 5 completed Daily candles − 0.5 × ATR(14)\n"
        "TP = Entry + 4R"
    )


    st.subheader(
        "Pullback Levels"
    )


    st.dataframe(
        pd.DataFrame(
            {
                "Pullback": [
                    f"-{x}%"
                    for x in PULLBACKS
                ],

                "Price": [
                    ath * (1 - x / 100)
                    for x in PULLBACKS
                ],
            }
        ),
        use_container_width=True,
        hide_index=True
    )


# ============================================================
# EVENTS
# ============================================================

with t5:

    st.subheader(
        "FOMC / Events"
    )

    st.write(
        "Official Fed source fetched:",
        st.session_state.fomc.get(
            "source"
        )
    )

    st.write(
        "Years detected:",
        st.session_state.fomc.get(
            "years_found"
        )
    )

    st.warning(
        "Actual / Forecast / Previous consensus is not fabricated. "
        "It requires a reliable consensus provider."
    )


# ============================================================
# HISTORY
# ============================================================

with t6:

    st.subheader(
        "Saved engine history"
    )

    st.dataframe(
        pd.DataFrame(
            history(),
            columns=[
                "Time",
                "Price",
                "Drawdown",
                "Score",
                "Regime",
                "Decision"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )


    st.subheader(
        "Alerts"
    )


    st.dataframe(
        pd.DataFrame(
            alerts(),
            columns=[
                "Time",
                "Type",
                "Message"
            ]
        ),
        use_container_width=True,
        hide_index=True
    )
