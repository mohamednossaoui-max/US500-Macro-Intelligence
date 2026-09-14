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
# PAGE CONFIG
# ============================================================

st.set_page_config(
    page_title="US500 Macro Intelligence — PRODUCTION",
    layout="wide"
)

init()


# ============================================================
# TITLE
# ============================================================

st.title("US500 Macro Intelligence — PRODUCTION")

st.caption(
    "Macro → Early Warning → Regime → Technical → "
    "Pullback → Risk/Reward | Decision support only"
)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def safe_value(x):

    try:

        if x is None or x.empty:
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

        current = float(x.iloc[-1]["value"])
        previous = float(x.iloc[-1-n]["value"])

        if np.isnan(current) or np.isnan(previous):
            return np.nan

        return current - previous

    except Exception:

        return np.nan


def safe_pct_change(x, n=1):

    try:

        if x is None or len(x) <= n:
            return np.nan

        current = float(x.iloc[-1]["value"])
        previous = float(x.iloc[-1-n]["value"])

        if np.isnan(current) or np.isnan(previous):
            return np.nan

        if previous == 0:
            return np.nan

        return (current / previous - 1) * 100

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
# TECHNICAL CONFIRMATION
# ============================================================

def technical_confirmation(m):

    if m is None or m.empty:

        return {

            "score": 0,

            "level": "UNAVAILABLE",

            "reasons": [
                "Market data unavailable."
            ],

            "details": {}
        }


    x = m.copy()


    required = {
        "close",
        "high",
        "low"
    }


    if not required.issubset(
        set(x.columns)
    ):

        return {

            "score": 0,

            "level": "UNAVAILABLE",

            "reasons": [
                "Required OHLC columns are unavailable."
            ],

            "details": {}
        }


    # --------------------------------------------------------
    # MOVING AVERAGES
    # --------------------------------------------------------

    x["SMA50"] = (
        x["close"]
        .rolling(50)
        .mean()
    )

    x["SMA200"] = (
        x["close"]
        .rolling(200)
        .mean()
    )


    score = 0

    reasons = []

    details = {}


    price = float(
        x["close"].iloc[-1]
    )


    sma50 = (

        float(x["SMA50"].iloc[-1])

        if pd.notna(
            x["SMA50"].iloc[-1]
        )

        else np.nan
    )


    sma200 = (

        float(x["SMA200"].iloc[-1])

        if pd.notna(
            x["SMA200"].iloc[-1]
        )

        else np.nan
    )


    # --------------------------------------------------------
    # 1 — PRICE > SMA200
    # --------------------------------------------------------

    if not np.isnan(sma200):

        if price > sma200:

            score += 1

            details[
                "Price > SMA200"
            ] = "PASS"

            reasons.append(
                "Price is above SMA200."
            )

        else:

            details[
                "Price > SMA200"
            ] = "FAIL"

            reasons.append(
                "Price is below SMA200."
            )

    else:

        details[
            "Price > SMA200"
        ] = "UNAVAILABLE"


    # --------------------------------------------------------
    # 2 — SMA50 > SMA200
    # --------------------------------------------------------

    if (
        not np.isnan(sma50)
        and
        not np.isnan(sma200)
    ):

        if sma50 > sma200:

            score += 1

            details[
                "SMA50 > SMA200"
            ] = "PASS"

            reasons.append(
                "SMA50 is above SMA200."
            )

        else:

            details[
                "SMA50 > SMA200"
            ] = "FAIL"

            reasons.append(
                "SMA50 is below SMA200."
            )

    else:

        details[
            "SMA50 > SMA200"
        ] = "UNAVAILABLE"


    # --------------------------------------------------------
    # 3 — HIGHER LOW
    # --------------------------------------------------------

    if len(x) >= 20:

        recent = x.iloc[-10:-1]

        previous = x.iloc[-20:-10]


        recent_low = float(
            recent["low"].min()
        )

        previous_low = float(
            previous["low"].min()
        )


        if recent_low > previous_low:

            score += 1

            details[
                "Higher Low"
            ] = "PASS"

            reasons.append(
                "Recent price structure shows a higher low."
            )

        else:

            details[
                "Higher Low"
            ] = "FAIL"

            reasons.append(
                "No clear higher-low structure."
            )

    else:

        details[
            "Higher Low"
        ] = "UNAVAILABLE"


    # --------------------------------------------------------
    # 4 — CONFIRMATION CANDLE
    # --------------------------------------------------------

    if len(x) >= 2:

        last = x.iloc[-1]

        previous = x.iloc[-2]


        if (
            float(last["close"])
            >
            float(previous["high"])
        ):

            score += 1

            details[
                "Confirmation Candle"
            ] = "PASS"

            reasons.append(
                "Latest completed candle closed above the previous high."
            )

        else:

            details[
                "Confirmation Candle"
            ] = "FAIL"

            reasons.append(
                "No close above the previous candle high."
            )

    else:

        details[
            "Confirmation Candle"
        ] = "UNAVAILABLE"


    # --------------------------------------------------------
    # 5 — ATR VOLATILITY FILTER
    # --------------------------------------------------------

    if len(x) >= 30:

        previous_close = (
            x["close"]
            .shift(1)
        )


        tr = pd.concat(

            [

                (
                    x["high"]
                    -
                    x["low"]
                ).abs(),

                (
                    x["high"]
                    -
                    previous_close
                ).abs(),

                (
                    x["low"]
                    -
                    previous_close
                ).abs(),

            ],

            axis=1
        ).max(axis=1)


        atr14 = (
            tr
            .rolling(14)
            .mean()
        )


        current_atr = (

            float(
                atr14.iloc[-1]
            )

            if pd.notna(
                atr14.iloc[-1]
            )

            else np.nan
        )


        historical_atr = (
            atr14.iloc[-30:-1]
        )


        median_atr = (

            float(
                historical_atr.median()
            )

            if historical_atr.notna().any()

            else np.nan
        )


        if (
            not np.isnan(current_atr)
            and
            not np.isnan(median_atr)
            and
            median_atr > 0
        ):

            ratio = (
                current_atr
                /
                median_atr
            )


            if ratio <= 1.8:

                score += 1

                details[
                    "ATR Filter"
                ] = f"PASS ({ratio:.2f}x)"

                reasons.append(
                    "ATR is not in an extreme volatility regime."
                )

            else:

                details[
                    "ATR Filter"
                ] = f"FAIL ({ratio:.2f}x)"

                reasons.append(
                    "ATR is unusually elevated."
                )

        else:

            details[
                "ATR Filter"
            ] = "UNAVAILABLE"

    else:

        details[
            "ATR Filter"
        ] = "UNAVAILABLE"


    # --------------------------------------------------------
    # TECHNICAL CLASSIFICATION
    # --------------------------------------------------------

    if score >= 4:

        level = "CONFIRMED"

    elif score >= 2:

        level = "PARTIAL"

    else:

        level = "WEAK"


    details[
        "Technical Score"
    ] = f"{score}/5"


    return {

        "score": score,

        "level": level,

        "reasons": reasons,

        "details": details,
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
    technical_level
):

    regime_text = str(regime)


    # --------------------------------------------------------
    # CRITICAL SYSTEMIC STRESS
    # --------------------------------------------------------

    if early_score >= 75:

        return {

            "decision":
                "CRITICAL — NO NEW TRADE",

            "color":
                "red",

            "reason":
                (
                    "Early Warning is CRITICAL. "
                    "Systemic stress overrides technical signals."
                )
        }


    # --------------------------------------------------------
    # RECESSION / BEAR RISK
    # --------------------------------------------------------

    if regime_text.startswith("E"):

        return {

            "decision":
                "DEFENSIVE",

            "color":
                "red",

            "reason":
                (
                    "Macro regime indicates "
                    "recession / bear risk."
                )
        }


    # --------------------------------------------------------
    # FINANCIAL / LIQUIDITY SHOCK
    # --------------------------------------------------------

    if regime_text.startswith("F"):

        return {

            "decision":
                "DEFENSIVE",

            "color":
                "red",

            "reason":
                (
                    "Financial/liquidity stress is detected."
                )
        }


    # --------------------------------------------------------
    # HIGH EARLY WARNING
    # --------------------------------------------------------

    if early_score >= 50:

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "orange",

            "reason":
                (
                    "Multiple leading indicators are showing "
                    "meaningful deterioration."
                )
        }


    # --------------------------------------------------------
    # MODERATE EARLY WARNING
    # --------------------------------------------------------

    if early_score >= 25:

        return {

            "decision":
                "CAUTION",

            "color":
                "yellow",

            "reason":
                (
                    "Early warning indicators are deteriorating. "
                    "Technical confirmation is required."
                )
        }


    # --------------------------------------------------------
    # INFLATION / RATE SHOCK
    # --------------------------------------------------------

    if regime_text.startswith("C"):

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "orange",

            "reason":
                (
                    "Inflation/rates pressure is elevated. "
                    "Wait for technical confirmation."
                )
        }


    # --------------------------------------------------------
    # MIXED STRESS
    # --------------------------------------------------------

    if regime_text.startswith("D"):

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "orange",

            "reason":
                (
                    "Growth and inflation signals are mixed. "
                    "Technical confirmation is required."
                )
        }


    # --------------------------------------------------------
    # VERY DEEP DRAWDOWN
    # --------------------------------------------------------

    if drawdown <= -20:

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "orange",

            "reason":
                (
                    "Drawdown is very deep. "
                    "Depth alone does not justify a buy."
                )
        }


    # --------------------------------------------------------
    # TECHNICAL WEAK
    # --------------------------------------------------------

    if technical_level == "WEAK":

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "yellow",

            "reason":
                (
                    "Technical confirmation is weak."
                )
        }


    # --------------------------------------------------------
    # DEEP PULLBACK
    # --------------------------------------------------------

    if drawdown <= -10:

        if (
            technical_level == "CONFIRMED"
            and
            macro_score >= 3
        ):

            return {

                "decision":
                    "SUPPORTIVE / CONFIRMED",

                "color":
                    "green",

                "reason":
                    (
                        "Deep pullback with supportive macro "
                        "conditions and confirmed technical structure."
                    )
            }


        return {

            "decision":
                "SUPPORTIVE / CONFIRM",

            "color":
                "yellow",

            "reason":
                (
                    "Macro conditions remain relatively supportive, "
                    "but technical confirmation is incomplete."
                )
        }


    # --------------------------------------------------------
    # NORMAL PULLBACK + FULL CONFIRMATION
    # --------------------------------------------------------

    if (
        early_score < 25
        and
        macro_score >= 3
        and
        technical_level == "CONFIRMED"
    ):

        return {

            "decision":
                "BUY SETUP",

            "color":
                "green",

            "reason":
                (
                    "Macro, early-warning and technical "
                    "conditions are aligned."
                )
        }


    # --------------------------------------------------------
    # PARTIAL TECHNICAL
    # --------------------------------------------------------

    if technical_level == "PARTIAL":

        return {

            "decision":
                "CAUTION",

            "color":
                "yellow",

            "reason":
                (
                    "Macro conditions are acceptable, "
                    "but technical confirmation is only partial."
                )
        }


    # --------------------------------------------------------
    # DEFAULT
    # --------------------------------------------------------

    return {

        "decision":
            "CAUTION",

        "color":
            "yellow",

        "reason":
            (
                "Signals are not sufficiently strong "
                "to classify the environment as a confirmed setup."
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

        help=(
            "يمكن حفظه في Streamlit Secrets "
            "باسم FRED_API_KEY."
        )
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

        f"Market feed: {MARKET_TICKER} | "
        f"Refresh target: {REFRESH_MINUTES} min"
    )


# ============================================================
# DATA UPDATE
# ============================================================

if (
    "force" in st.session_state
    or
    "f" not in st.session_state
):

    if not key:

        st.info(
            "ضع FRED_API_KEY في Secrets/Environment "
            "أو أدخل المفتاح هنا ثم REFRESH NOW."
        )

        st.stop()


    try:

        with st.spinner(
            "Updating official macro + market data..."
        ):

            st.session_state.f = (
                fred_all(
                    key,
                    start
                )
            )


            st.session_state.b = (
                bls_all(
                    start.year,
                    date.today().year
                )
            )


            st.session_state.m = (
                market(start)
            )


            st.session_state.ts = (
                datetime.now()
            )


            st.session_state.fomc = (
                parse_fomc(
                    fomc_page()
                )
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
# LOAD DATA
# ============================================================

f = st.session_state.f

m = st.session_state.m


# ============================================================
# MARKET STATE
# ============================================================

price, ath, dd, atr = state(m)


# ============================================================
# MACRO ENGINE
# ============================================================

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


# ============================================================
# EARLY WARNING
# ============================================================

ew = early_warning(f)

ew_score = ew["score"]

ew_level = ew["level"]


# ============================================================
# TECHNICAL CONFIRMATION
# ============================================================

tech = technical_confirmation(m)

tech_score = tech["score"]

tech_level = tech["level"]


# ============================================================
# FINAL DECISION
# ============================================================

decision_result = decision_engine(

    early_score=ew_score,

    early_level=ew_level,

    macro_score=score,

    regime=reg,

    drawdown=dd,

    technical_score=tech_score,

    technical_level=tech_level
)


dec = decision_result["decision"]

dec_color = decision_result["color"]

dec_reason = decision_result["reason"]


# ============================================================
# SAVE SNAPSHOT
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


# ============================================================
# ALERTS
# ============================================================

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
# TOP DASHBOARD
# ============================================================

cols = st.columns(9)


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
        "Technical",
        f"{tech_score}/5"
    ),

    (
        "Decision",
        dec
    )
]


for column, item in zip(
    cols,
    dashboard
):

    label, value = item

    column.metric(
        label,
        value
    )


# ============================================================
# DECISION BANNER
# ============================================================

if dec_color == "red":

    st.error(
        f"🔴 {dec}"
    )

elif dec_color == "orange":

    st.warning(
        f"🟠 {dec}"
    )

elif dec_color == "yellow":

    st.warning(
        f"🟡 {dec}"
    )

else:

    st.success(
        f"🟢 {dec}"
    )


st.write(
    dec_reason
)


# ============================================================
# TABS
# ============================================================

tabs = st.tabs(

    [
        "LIVE",
        "EARLY WARNING",
        "TECHNICAL",
        "MACRO",
        "TRADING",
        "EVENTS",
        "HISTORY"
    ]
)


# ============================================================
# LIVE
# ============================================================

with tabs[0]:

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
        f"**Early Warning:** "
        f"{ew_score}/100 — {ew_level}"
    )


    st.write(
        f"**Technical:** "
        f"{tech_score}/5 — {tech_level}"
    )


    st.write(
        f"**Final Decision:** {dec}"
    )


    st.divider()


    st.write(
        "**الفلسفة:**"
    )


    st.write(

        "Drawdown + Macro Regime + "
        "Early Warning + Technical Structure "
        "= Trading Decision"
    )


# ============================================================
# EARLY WARNING
# ============================================================

with tabs[1]:

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
        min(ew_score, 100) / 100
    )


    st.subheader(
        "Component Breakdown"
    )


    maximums = {

        "Credit": 20,

        "Labor": 20,

        "Yield Curve": 15,

        "Financial Conditions": 20,

        "Market Risk": 15,

        "Macro Momentum": 10
    }


    rows = []


    for name, value in ew[
        "details"
    ].items():

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
        )
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


# ============================================================
# TECHNICAL
# ============================================================

with tabs[2]:

    st.subheader(
        "📈 Technical Confirmation"
    )


    c1, c2 = st.columns(2)


    c1.metric(
        "Technical Score",
        f"{tech_score}/5"
    )


    c2.metric(
        "Technical Status",
        tech_level
    )


    st.progress(
        tech_score / 5
    )


    st.info(

        "Technical confirmation uses Daily OHLC data "
        "as a confirmation filter. It is not an "
        "automatic trade execution signal."
    )


    st.subheader(
        "Technical Factors"
    )


    technical_rows = []


    for factor, status in tech[
        "details"
    ].items():

        technical_rows.append(

            [
                factor,
                status
            ]
        )


    st.dataframe(

        pd.DataFrame(

            technical_rows,

            columns=[
                "Factor",
                "Status"
            ]
        ),

        use_container_width=True,

        hide_index=True
    )


    st.subheader(
        "Technical Reasons"
    )


    for reason in tech[
        "reasons"
    ]:

        if (

            "FAIL" in reason.upper()

            or

            "below" in reason.lower()

            or

            "No " in reason
        ):

            st.warning(
                f"⚠️ {reason}"
            )

        else:

            st.success(
                f"✅ {reason}"
            )


    st.divider()


    st.subheader(
        "Technical Scoring Model"
    )


    st.dataframe(

        pd.DataFrame(

            [

                [
                    "Price > SMA200",
                    "Long-term trend",
                    1
                ],

                [
                    "SMA50 > SMA200",
                    "Medium-term trend",
                    1
                ],

                [
                    "Higher Low",
                    "Pullback structure",
                    1
                ],

                [
                    "Close > Previous High",
                    "Daily confirmation",
                    1
                ],

                [
                    "ATR not extreme",
                    "Volatility filter",
                    1
                ]

            ],

            columns=[
                "Factor",
                "Purpose",
                "Points"
            ]
        ),

        use_container_width=True,

        hide_index=True
    )


# ============================================================
# MACRO
# ============================================================

with tabs[3]:

    st.subheader(
        "Macro Dashboard"
    )


    macro_rows = []


    macro_indicators = [

        (
            "10Y",
            "US10Y"
        ),

        (
            "2Y",
            "US2Y"
        ),

        (
            "10Y-2Y",
            "T10Y2Y"
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
            "PCE",
            "PCE"
        ),

        (
            "Core PCE",
            "CORE_PCE"
        ),

        (
            "Unemployment",
            "UNRATE"
        ),

        (
            "Initial Claims 4W",
            "INITIAL_CLAIMS_4W"
        ),

        (
            "HY Spread",
            "HY_SPREAD"
        ),

        (
            "Corporate OAS",
            "CORP_OAS"
        ),

        (
            "NFCI",
            "NFCI"
        ),

        (
            "Industrial Production",
            "INDPRO"
        ),

        (
            "Retail Sales",
            "RETAIL"
        )
    ]


    for name, key_name in macro_indicators:

        macro_rows.append(

            [

                name,

                safe_value(
                    f.get(key_name)
                )
            ]
        )


    st.dataframe(

        pd.DataFrame(

            macro_rows,

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

with tabs[4]:

    st.subheader(
        "Trading Decision Support"
    )


    st.metric(
        "Final Decision",
        dec
    )


    st.write(
        dec_reason
    )


    if ew_score >= 50:

        st.error(

            "⚠️ Early Warning is elevated. "
            "Do not treat a deep pullback as an "
            "automatic buying opportunity."
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

        "SL = Lowest Low of previous 5 completed "
        "Daily candles − 0.5 × ATR(14)\n"
        "TP = Entry + 4R"
    )


    st.subheader(
        "Pullback Levels"
    )


    st.dataframe(

        pd.DataFrame(

            {

                "Pullback":
                    [
                        f"-{x}%"
                        for x in PULLBACKS
                    ],

                "Price":
                    [
                        ath * (1 - x / 100)
                        for x in PULLBACKS
                    ]
            }
        ),

        use_container_width=True,

        hide_index=True
    )


# ============================================================
# EVENTS
# ============================================================

with tabs[5]:

    st.subheader(
        "FOMC / Events"
    )


    st.write(
        "Official Fed source fetched:"
    )


    st.write(
        st.session_state.fomc.get(
            "source"
        )
    )


    st.write(
        "Years detected:"
    )


    st.write(
        st.session_state.fomc.get(
            "years_found"
        )
    )


    st.warning(

        "Actual / Forecast / Previous consensus "
        "is not fabricated. It requires a reliable "
        "consensus provider."
    )


# ============================================================
# HISTORY
# ============================================================

with tabs[6]:

    st.subheader(
        "Saved Engine History"
    )


    hist = history()


    if hist:

        st.dataframe(

            pd.DataFrame(

                hist,

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

    else:

        st.info(
            "No saved history yet."
        )


    st.subheader(
        "Alerts"
    )


    alert_data = alerts()


    if alert_data:

        st.dataframe(

            pd.DataFrame(

                alert_data,

                columns=[

                    "Time",

                    "Type",

                    "Message"
                ]
            ),

            use_container_width=True,

            hide_index=True
        )

    else:

        st.info(
            "No alerts yet."
        )
