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
    decision,
    sl_tp,
    PULLBACKS,
)

from db import init, save_snapshot, save_alert, history, alerts


# ============================================================
# EARLY WARNING ENGINE
# ============================================================

def safe_value(x):
    try:
        v = latest(x)
        if v is None or np.isnan(v):
            return np.nan
        return float(v)
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
            reasons.append("HY credit spread is at a severe stress level.")
        elif hy >= 5:
            scores["Credit"] += 9
            reasons.append("HY credit spread is significantly elevated.")
        elif hy >= 4:
            scores["Credit"] += 5
            reasons.append("HY credit spread is elevated.")

    hy_change = safe_pct_change(f.get("HY_SPREAD"), 60)

    if not np.isnan(hy_change):

        if hy_change >= 30:
            scores["Credit"] += 8
            reasons.append("HY spread has widened sharply over the recent period.")
        elif hy_change >= 15:
            scores["Credit"] += 5
            reasons.append("HY spread is widening.")
        elif hy_change >= 8:
            scores["Credit"] += 3
            reasons.append("HY spread shows increasing stress.")

    corp = safe_value(f.get("CORP_OAS"))

    if not np.isnan(corp):

        if corp >= 3:
            scores["Credit"] += 5
            reasons.append("Corporate OAS is highly elevated.")
        elif corp >= 2.5:
            scores["Credit"] += 3
            reasons.append("Corporate OAS is elevated.")

    scores["Credit"] = min(scores["Credit"], 20)


    # --------------------------------------------------------
    # LABOR
    # --------------------------------------------------------

    claims = safe_pct_change(f.get("INITIAL_CLAIMS_4W"), 12)

    if not np.isnan(claims):

        if claims >= 8:
            scores["Labor"] += 12
            reasons.append("Initial claims trend is deteriorating materially.")
        elif claims >= 5:
            scores["Labor"] += 8
            reasons.append("Initial claims trend is weakening.")
        elif claims >= 3:
            scores["Labor"] += 4
            reasons.append("Initial claims are showing early deterioration.")

    unemployment = safe_delta(f.get("UNRATE"), 3)

    if not np.isnan(unemployment):

        if unemployment >= 0.2:
            scores["Labor"] += 8
            reasons.append("Unemployment rate has risen materially.")
        elif unemployment >= 0.1:
            scores["Labor"] += 4
            reasons.append("Unemployment rate is trending higher.")

    scores["Labor"] = min(scores["Labor"], 20)


    # --------------------------------------------------------
    # YIELD CURVE
    # --------------------------------------------------------

    curve = safe_value(f.get("T10Y2Y"))

    if not np.isnan(curve):

        if curve < -0.50:
            scores["Yield Curve"] += 10
            reasons.append("Yield curve is deeply inverted.")
        elif curve < 0:
            scores["Yield Curve"] += 7
            reasons.append("Yield curve remains inverted.")

    curve_change = safe_delta(f.get("T10Y2Y"), 60)

    if not np.isnan(curve_change):

        if curve_change <= -0.50:
            scores["Yield Curve"] += 5
            reasons.append("Yield curve has deteriorated significantly.")
        elif curve_change <= -0.25:
            scores["Yield Curve"] += 3
            reasons.append("Yield curve is becoming less supportive.")

    scores["Yield Curve"] = min(scores["Yield Curve"], 15)


    # --------------------------------------------------------
    # FINANCIAL CONDITIONS
    # --------------------------------------------------------

    nfci = safe_value(f.get("NFCI"))

    if not np.isnan(nfci):

        if nfci >= 1:
            scores["Financial Conditions"] += 12
            reasons.append("Financial conditions are severely tight.")
        elif nfci >= 0.5:
            scores["Financial Conditions"] += 8
            reasons.append("Financial conditions are materially tight.")
        elif nfci > 0:
            scores["Financial Conditions"] += 4
            reasons.append("Financial conditions are tighter than average.")

    nfci_change = safe_delta(f.get("NFCI"), 4)

    if not np.isnan(nfci_change):

        if nfci_change >= 0.30:
            scores["Financial Conditions"] += 8
            reasons.append("Financial conditions are tightening rapidly.")
        elif nfci_change >= 0.15:
            scores["Financial Conditions"] += 5
            reasons.append("Financial conditions are tightening.")
        elif nfci_change >= 0.08:
            scores["Financial Conditions"] += 2
            reasons.append("Financial conditions show early tightening.")

    scores["Financial Conditions"] = min(scores["Financial Conditions"], 20)


    # --------------------------------------------------------
    # MARKET RISK
    # --------------------------------------------------------

    vix = safe_value(f.get("VIX"))

    if not np.isnan(vix):

        if vix >= 35:
            scores["Market Risk"] += 15
            reasons.append("VIX is at a severe risk level.")
        elif vix >= 30:
            scores["Market Risk"] += 10
            reasons.append("VIX is highly elevated.")
        elif vix >= 25:
            scores["Market Risk"] += 6
            reasons.append("VIX is elevated.")
        elif vix >= 20:
            scores["Market Risk"] += 3
            reasons.append("VIX is above the normal low-risk zone.")

    vix_change = safe_pct_change(f.get("VIX"), 20)

    if not np.isnan(vix_change):

        if vix_change >= 50:
            scores["Market Risk"] += 5
            reasons.append("VIX has risen sharply.")
        elif vix_change >= 25:
            scores["Market Risk"] += 3
            reasons.append("VIX is rising significantly.")

    dxy_change = safe_pct_change(f.get("DXY"), 60)

    if not np.isnan(dxy_change):

        if dxy_change >= 8:
            scores["Market Risk"] += 3
            reasons.append("DXY has strengthened materially.")
        elif dxy_change >= 5:
            scores["Market Risk"] += 2
            reasons.append("DXY is showing a strong upward trend.")

    scores["Market Risk"] = min(scores["Market Risk"], 15)


    # --------------------------------------------------------
    # MACRO MOMENTUM
    # --------------------------------------------------------

    indpro = safe_pct_change(f.get("INDPRO"), 3)

    if not np.isnan(indpro) and indpro < 0:
        scores["Macro Momentum"] += 3
        reasons.append("Industrial production momentum is weakening.")

    retail = safe_pct_change(f.get("RETAIL"), 3)

    if not np.isnan(retail) and retail < 0:
        scores["Macro Momentum"] += 3
        reasons.append("Retail sales momentum is weakening.")

    pce = safe_pct_change(f.get("PCE"), 3)

    if not np.isnan(pce) and pce > 0:
        scores["Macro Momentum"] += 4
        reasons.append("PCE trend is accelerating.")

    scores["Macro Momentum"] = min(scores["Macro Momentum"], 10)


    # --------------------------------------------------------
    # TOTAL
    # --------------------------------------------------------

    total = int(sum(scores.values()))

    if total <= 24:
        level = "LOW"
    elif total <= 49:
        level = "MODERATE"
    elif total <= 74:
        level = "HIGH"
    else:
        level = "CRITICAL"

    details = {
        "Credit": scores["Credit"],
        "Labor": scores["Labor"],
        "Yield Curve": scores["Yield Curve"],
        "Financial Conditions": scores["Financial Conditions"],
        "Market Risk": scores["Market Risk"],
        "Macro Momentum": scores["Macro Momentum"],
    }

    return {
        "score": total,
        "level": level,
        "reasons": reasons,
        "details": details,
    }


# ============================================================
# APP
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
        ["Neutral", "Dovish", "Hawkish"]
    )

    if st.button("REFRESH NOW", type="primary"):
        st.session_state.force = True

    st.caption(
        f"Market feed: {MARKET_TICKER} | Refresh target: {REFRESH_MINUTES} min"
    )


# ============================================================
# DATA UPDATE
# ============================================================

if "force" in st.session_state or "f" not in st.session_state:

    if not key:

        st.info(
            "ضع FRED_API_KEY في Secrets/Environment أو أدخل المفتاح هنا ثم REFRESH NOW."
        )

        st.stop()

    try:

        with st.spinner("Updating official macro + market data..."):

            st.session_state.f = fred_all(key, start)

            st.session_state.b = bls_all(
                start.year,
                date.today().year
            )

            st.session_state.m = market(start)

            st.session_state.ts = datetime.now()

            st.session_state.fomc = parse_fomc(
                fomc_page()
            )

        st.session_state.pop("force", None)

    except Exception as e:

        st.error(f"Update failed: {e}")

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

dec = decision(
    score,
    dd,
    w
)

pb = classify(
    dd,
    score,
    reg
)

# NEW EARLY WARNING
ew = early_warning(f)

ew_score = ew["score"]
ew_level = ew["level"]


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


# ============================================================
# TOP DASHBOARD
# ============================================================

cols = st.columns(8)

metrics = [
    ("US500", f"{price:.2f}"),
    ("ATH", f"{ath:.2f}"),
    ("Drawdown", f"{dd:.2f}%"),
    ("Macro", f"{score:+d}/10"),
    ("Regime", reg.split("—")[0].strip()),
    ("Pullback", pb.split("—")[0].strip()),
    ("Early Warning", f"{ew_score}/100"),
    ("Decision", dec),
]

for c, (label, value) in zip(cols, metrics):

    c.metric(
        label,
        value
    )


# ============================================================
# DECISION BANNER
# ============================================================

if dec == "DEFENSIVE":

    st.error(
        "🔴 DEFENSIVE — لا نفترض أن الهبوط فرصة شراء."
    )

elif dec.startswith("WAIT"):

    st.warning(
        "🟡 WAIT / CONFIRM — نحتاج تأكيداً إضافياً."
    )

else:

    st.success(
        "🟢 SUPPORTIVE — التصحيح أقرب إلى Pullback داخل الاتجاه."
    )


# ============================================================
# EARLY WARNING BANNER
# ============================================================

if ew_level == "CRITICAL":

    st.error(
        f"🚨 EARLY WARNING CRITICAL — {ew_score}/100"
    )

elif ew_level == "HIGH":

    st.error(
        f"🔴 EARLY WARNING HIGH — {ew_score}/100"
    )

elif ew_level == "MODERATE":

    st.warning(
        f"🟠 EARLY WARNING MODERATE — {ew_score}/100"
    )

else:

    st.success(
        f"🟢 EARLY WARNING LOW — {ew_score}/100"
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

    st.subheader("الخلاصة التنفيذية")

    st.write(
        f"**Regime:** {reg}"
    )

    st.write(
        f"**Pullback:** {pb}"
    )

    st.write(
        f"**Why:** score={score:+d}, "
        f"drawdown={dd:.2f}%, "
        f"VIX={meta['vix']:.2f}, "
        f"HY spread={meta['credit']:.2f}"
    )

    st.write(
        "**Base scenario:** "
        +
        (
            "استمرار الاتجاه مع تصحيح محدود"
            if score >= 3
            else
            "تذبذب/تصحيح مع الحاجة لتأكيد"
            if score > -4
            else
            "خطر هبوطي مرتفع، الأولوية لحماية رأس المال"
        )
    )

    st.write(
        "**Next trigger:** "
        "تدهور متزامن في النمو + العمل + الائتمان/التقلب "
        "يرفع مستوى الخطر أسرع من عمق الهبوط وحده."
    )


# ============================================================
# EARLY WARNING
# ============================================================

with t2:

    st.subheader(
        "🚨 Early Warning Score"
    )

    st.metric(
        "Early Warning Score",
        f"{ew_score}/100"
    )

    st.metric(
        "Risk Level",
        ew_level
    )

    st.progress(
        min(ew_score, 100) / 100
    )

    st.divider()

    st.subheader(
        "Component Breakdown"
    )

    component_rows = []

    maximums = {
        "Credit": 20,
        "Labor": 20,
        "Yield Curve": 15,
        "Financial Conditions": 20,
        "Market Risk": 15,
        "Macro Momentum": 10,
    }

    for name, value in ew["details"].items():

        component_rows.append(
            [
                name,
                value,
                maximums[name],
                f"{value / maximums[name] * 100:.0f}%"
            ]
        )

    st.dataframe(
        pd.DataFrame(
            component_rows,
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

    indicator_rows = []

    for name, key_name in [
        ("HY Spread", "HY_SPREAD"),
        ("Corporate OAS", "CORP_OAS"),
        ("Initial Claims 4W", "INITIAL_CLAIMS_4W"),
        ("Unemployment", "UNRATE"),
        ("10Y-2Y Yield Curve", "T10Y2Y"),
        ("NFCI", "NFCI"),
        ("VIX", "VIX"),
        ("DXY", "DXY"),
        ("Industrial Production", "INDPRO"),
        ("Retail Sales", "RETAIL"),
        ("PCE", "PCE"),
    ]:

        indicator_rows.append(
            [
                name,
                safe_value(f.get(key_name))
            ]
        )

    st.dataframe(
        pd.DataFrame(
            indicator_rows,
            columns=["Indicator", "Latest"]
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

    interpretation = pd.DataFrame(
        [
            ["0–24", "LOW", "No major systemic warning detected."],
            ["25–49", "MODERATE", "Some early deterioration. Monitor closely."],
            ["50–74", "HIGH", "Multiple risk indicators are aligning."],
            ["75–100", "CRITICAL", "Potential regime/systemic stress. Reassess strategy."],
        ],
        columns=[
            "Score",
            "Level",
            "Meaning"
        ]
    )

    st.dataframe(
        interpretation,
        use_container_width=True,
        hide_index=True
    )

    st.info(
        "الهدف من Early Warning هو اكتشاف تغير النظام قبل أن يصل Drawdown إلى -10% أو -20%."
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
                safe_value(f.get(k))
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

    if ew_score >= 50:

        st.error(
            "⚠️ Early Warning ≥ 50 — البيئة الماكروية تستدعي الحذر قبل أي دخول."
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

    st.metric(
        "SL",
        f"{sl:.2f}"
    )

    st.metric(
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
        st.session_state.fomc.get("source")
    )

    st.write(
        "Years detected:",
        st.session_state.fomc.get("years_found")
    )

    st.warning(
        "Actual/Forecast/Previous consensus is intentionally not fabricated. "
        "It requires a reliable calendar/consensus provider."
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
