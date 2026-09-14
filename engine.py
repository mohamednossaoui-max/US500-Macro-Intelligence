import numpy as np
import pandas as pd


# =========================================================
# US500 MACRO INTELLIGENCE
# ENGINE
# =========================================================

PULLBACKS = [3, 5, 10, 20, 30]


# =========================================================
# BASIC HELPERS
# =========================================================

def latest(x):
    """
    Return latest value from a FRED-style dataframe.
    Expected columns: date, value
    """
    if x is None or x.empty:
        return np.nan

    try:
        return float(x.iloc[-1]["value"])
    except Exception:
        return np.nan


def delta(x, n=1):
    """
    Difference between latest value and n observations ago.
    """
    if x is None or x.empty or len(x) <= n:
        return np.nan

    try:
        return float(
            x.iloc[-1]["value"] -
            x.iloc[-1 - n]["value"]
        )
    except Exception:
        return np.nan


def pct_delta(x, n=1):
    """
    Percentage change versus n observations ago.
    """
    if x is None or x.empty or len(x) <= n:
        return np.nan

    try:
        old = float(x.iloc[-1 - n]["value"])
        new = float(x.iloc[-1]["value"])

        if old == 0:
            return np.nan

        return (new / old - 1.0) * 100.0
    except Exception:
        return np.nan


def safe_value(x, default=np.nan):
    """
    Safe float conversion.
    """
    try:
        if x is None or pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


# =========================================================
# MARKET STATE
# =========================================================

def state(m):
    """
    Calculate:
    price
    ATH
    drawdown
    ATR(14)
    """

    if m is None or m.empty:
        return np.nan, np.nan, np.nan, np.nan

    price = float(m.close.iloc[-1])

    ath = float(
        m.close.cummax().iloc[-1]
    )

    drawdown = (
        (price / ath) - 1.0
    ) * 100.0

    previous_close = m.close.shift(1)

    true_range = pd.concat(
        [
            (m.high - m.low).abs(),
            (m.high - previous_close).abs(),
            (m.low - previous_close).abs(),
        ],
        axis=1
    ).max(axis=1)

    atr14 = float(
        true_range.rolling(14).mean().iloc[-1]
    )

    return price, ath, drawdown, atr14


# =========================================================
# MACRO ANALYSIS
# =========================================================

def analyze(f, fed):
    """
    Existing macro scoring system.

    Score:
        -10 = very negative
        +10 = very supportive
    """

    g = 0

    # Growth
    indpro_change = pct_delta(
        f.get("INDPRO"), 3
    )

    retail_change = pct_delta(
        f.get("RETAIL"), 3
    )

    if not np.isnan(indpro_change):
        g += int(np.sign(indpro_change))

    if not np.isnan(retail_change):
        g += int(np.sign(retail_change))

    # Labor
    unemployment_change = delta(
        f.get("UNRATE"), 3
    )

    if not np.isnan(unemployment_change):
        g -= int(np.sign(unemployment_change))

    # Inflation
    pce_change = pct_delta(
        f.get("PCE"), 3
    )

    if not np.isnan(pce_change):
        g -= int(np.sign(pce_change))

    # Market risk
    vix = latest(f.get("VIX"))
    credit = latest(f.get("HY_SPREAD"))
    y10 = latest(f.get("US10Y"))

    # Fed stance
    if fed == "Dovish":
        score = g + 2
    elif fed == "Hawkish":
        score = g - 2
    else:
        score = g

    if not np.isnan(vix):

        if vix >= 30:
            score -= 2

        elif vix >= 25:
            score -= 1

        elif vix < 18:
            score += 1

    if not np.isnan(credit):

        if credit >= 5:
            score -= 2

        elif credit >= 4:
            score -= 1

        elif credit < 3.5:
            score += 1

    score = int(
        np.clip(score, -10, 10)
    )

    # =====================================================
    # REGIME CLASSIFICATION
    # =====================================================

    if (
        (not np.isnan(vix) and vix >= 35)
        or
        (not np.isnan(credit) and credit >= 6)
    ):

        regime = (
            "F — Liquidity / Financial Shock"
        )

    elif score <= -4:

        regime = (
            "E — Recession / Bear Risk"
        )

    elif (
        fed == "Hawkish"
        and
        not np.isnan(pce_change)
        and
        pce_change > 0
    ):

        regime = (
            "C — Inflation / Rates Shock"
        )

    elif score < 0:

        regime = (
            "D — Mixed Macro Stress"
        )

    elif score < 3:

        regime = (
            "B — Growth Scare / Mixed"
        )

    else:

        regime = (
            "A — Healthy / Supportive"
        )

    meta = {
        "growth": g,
        "vix": vix,
        "credit": credit,
        "10y": y10,
        "fed": fed,
    }

    return score, regime, meta


# =========================================================
# EARLY WARNING SYSTEM
# =========================================================

def early_warning(f):
    """
    Preliminary rule-based Early Warning System.

    Score:
        0-24   LOW
        25-49  MODERATE
        50-74  HIGH
        75-100 CRITICAL

    IMPORTANT:
    This is a rule-based monitoring model.
    It is NOT yet statistically validated/backtested.
    """

    total = 0

    reasons = []

    details = {}

    # =====================================================
    # 1. CREDIT RISK — 20 POINTS
    # =====================================================

    credit_score = 0

    hy = latest(
        f.get("HY_SPREAD")
    )

    corp = latest(
        f.get("CORP_OAS")
    )

    hy_change = pct_delta(
        f.get("HY_SPREAD"), 60
    )

    if not np.isnan(hy):

        if hy >= 6:
            credit_score += 12
            reasons.append(
                "🔴 HY spread ≥ 6% — severe credit stress"
            )

        elif hy >= 5:
            credit_score += 9
            reasons.append(
                "🟠 HY spread ≥ 5% — elevated credit stress"
            )

        elif hy >= 4:
            credit_score += 5
            reasons.append(
                "🟡 HY spread ≥ 4% — credit risk elevated"
            )

    if not np.isnan(hy_change):

        if hy_change >= 30:
            credit_score += 8
            reasons.append(
                "🔴 HY spread has widened sharply"
            )

        elif hy_change >= 15:
            credit_score += 5
            reasons.append(
                "🟠 HY spread widening"
            )

        elif hy_change >= 8:
            credit_score += 3
            reasons.append(
                "🟡 HY spread trend worsening"
            )

    # Corporate OAS
    if not np.isnan(corp):

        if corp >= 3.0:
            credit_score += 5
            reasons.append(
                "🔴 Corporate OAS very elevated"
            )

        elif corp >= 2.5:
            credit_score += 3
            reasons.append(
                "🟠 Corporate OAS elevated"
            )

    credit_score = min(
        credit_score, 20
    )

    total += credit_score

    details["credit"] = {
        "score": credit_score,
        "max": 20,
        "hy": hy,
        "corp_oas": corp,
        "hy_change_pct": hy_change,
    }

    # =====================================================
    # 2. LABOR / CLAIMS — 20 POINTS
    # =====================================================

    labor_score = 0

    claims = f.get(
        "INITIAL_CLAIMS_4W"
    )

    claims_now = latest(
        claims
    )

    claims_4w = pct_delta(
        claims, 4
    )

    claims_12w = pct_delta(
        claims, 12
    )

    unemployment_change = delta(
        f.get("UNRATE"), 3
    )

    if not np.isnan(claims_12w):

        if claims_12w >= 8:
            labor_score += 12
            reasons.append(
                "🔴 Initial Claims 4WMA rising sharply"
            )

        elif claims_12w >= 5:
            labor_score += 8
            reasons.append(
                "🟠 Initial Claims 4WMA trending higher"
            )

        elif claims_12w >= 3:
            labor_score += 4
            reasons.append(
                "🟡 Initial Claims trend slightly higher"
            )

    if (
        not np.isnan(unemployment_change)
        and unemployment_change >= 0.2
    ):

        labor_score += 8
        reasons.append(
            "🔴 Unemployment rate rising over 3 months"
        )

    elif (
        not np.isnan(unemployment_change)
        and unemployment_change >= 0.1
    ):

        labor_score += 4
        reasons.append(
            "🟡 Unemployment rate beginning to rise"
        )

    labor_score = min(
        labor_score, 20
    )

    total += labor_score

    details["labor"] = {
        "score": labor_score,
        "max": 20,
        "claims": claims_now,
        "claims_4w_pct": claims_4w,
        "claims_12w_pct": claims_12w,
        "unemployment_3m_change": unemployment_change,
    }

    # =====================================================
    # 3. YIELD CURVE — 15 POINTS
    # =====================================================

    curve_score = 0

    curve = latest(
        f.get("T10Y2Y")
    )

    curve_change = delta(
        f.get("T10Y2Y"), 60
    )

    if not np.isnan(curve):

        if curve < -0.50:
            curve_score += 10
            reasons.append(
                "🔴 Yield curve deeply inverted"
            )

        elif curve < 0:
            curve_score += 7
            reasons.append(
                "🟠 Yield curve inverted"
            )

    if not np.isnan(curve_change):

        if curve_change <= -0.50:
            curve_score += 5
            reasons.append(
                "🔴 Yield curve deteriorating significantly"
            )

        elif curve_change <= -0.25:
            curve_score += 3
            reasons.append(
                "🟡 Yield curve becoming less supportive"
            )

    curve_score = min(
        curve_score, 15
    )

    total += curve_score

    details["yield_curve"] = {
        "score": curve_score,
        "max": 15,
        "spread": curve,
        "change": curve_change,
    }

    # =====================================================
    # 4. FINANCIAL CONDITIONS — 20 POINTS
    # =====================================================

    financial_score = 0

    nfci = latest(
        f.get("NFCI")
    )

    nfci_change = delta(
        f.get("NFCI"), 4
    )

    if not np.isnan(nfci):

        if nfci >= 1.0:
            financial_score += 12
            reasons.append(
                "🔴 NFCI indicates very tight financial conditions"
            )

        elif nfci >= 0.5:
            financial_score += 8
            reasons.append(
                "🟠 NFCI indicates tighter financial conditions"
            )

        elif nfci > 0:
            financial_score += 4
            reasons.append(
                "🟡 NFCI above zero"
            )

    if not np.isnan(nfci_change):

        if nfci_change >= 0.30:
            financial_score += 8
            reasons.append(
                "🔴 Financial conditions tightening rapidly"
            )

        elif nfci_change >= 0.15:
            financial_score += 5
            reasons.append(
                "🟠 Financial conditions tightening"
            )

        elif nfci_change >= 0.08:
            financial_score += 2
            reasons.append(
                "🟡 Financial conditions becoming less supportive"
            )

    financial_score = min(
        financial_score, 20
    )

    total += financial_score

    details["financial_conditions"] = {
        "score": financial_score,
        "max": 20,
        "nfci": nfci,
        "nfci_change": nfci_change,
    }

    # =====================================================
    # 5. MARKET RISK — 15 POINTS
    # =====================================================

    market_score = 0

    vix = latest(
        f.get("VIX")
    )

    vix_change = pct_delta(
        f.get("VIX"), 20
    )

    dxy_change = pct_delta(
        f.get("DXY"), 60
    )

    if not np.isnan(vix):

        if vix >= 35:
            market_score += 15
            reasons.append(
                "🔴 VIX ≥ 35 — extreme market stress"
            )

        elif vix >= 30:
            market_score += 10
            reasons.append(
                "🔴 VIX ≥ 30 — severe risk aversion"
            )

        elif vix >= 25:
            market_score += 6
            reasons.append(
                "🟠 VIX ≥ 25 — elevated volatility"
            )

        elif vix >= 20:
            market_score += 3
            reasons.append(
                "🟡 VIX above 20"
            )

    if not np.isnan(vix_change):

        if vix_change >= 50:
            market_score += 5
            reasons.append(
                "🔴 VIX has surged sharply"
            )

        elif vix_change >= 25:
            market_score += 3
            reasons.append(
                "🟠 VIX rising rapidly"
            )

    if not np.isnan(dxy_change):

        if dxy_change >= 8:
            market_score += 3
            reasons.append(
                "🟠 DXY rising sharply"
            )

        elif dxy_change >= 5:
            market_score += 2
            reasons.append(
                "🟡 DXY showing strong upside momentum"
            )

    market_score = min(
        market_score, 15
    )

    total += market_score

    details["market_risk"] = {
        "score": market_score,
        "max": 15,
        "vix": vix,
        "vix_change_pct": vix_change,
        "dxy_change_pct": dxy_change,
    }

    # =====================================================
    # 6. MACRO MOMENTUM — 10 POINTS
    # =====================================================

    macro_score = 0

    indpro = pct_delta(
        f.get("INDPRO"), 3
    )

    retail = pct_delta(
        f.get("RETAIL"), 3
    )

    pce = pct_delta(
        f.get("PCE"), 3
    )

    if not np.isnan(indpro) and indpro < 0:
        macro_score += 3
        reasons.append(
            "🟡 Industrial production momentum weakening"
        )

    if not np.isnan(retail) and retail < 0:
        macro_score += 3
        reasons.append(
            "🟡 Retail sales momentum weakening"
        )

    if not np.isnan(pce) and pce > 0:
        macro_score += 4
        reasons.append(
            "🟡 PCE inflation momentum accelerating"
        )

    macro_score = min(
        macro_score, 10
    )

    total += macro_score

    details["macro_momentum"] = {
        "score": macro_score,
        "max": 10,
        "industrial_production_pct": indpro,
        "retail_pct": retail,
        "pce_pct": pce,
    }

    # =====================================================
    # FINAL SCORE
    # =====================================================

    total = int(
        np.clip(total, 0, 100)
    )

    if total >= 75:
        level = "CRITICAL"

    elif total >= 50:
        level = "HIGH"

    elif total >= 25:
        level = "MODERATE"

    else:
        level = "LOW"

    # If there are no warnings, give a positive message
    if not reasons:
        reasons.append(
            "🟢 No major early-warning cluster detected"
        )

    return {
        "score": total,
        "level": level,
        "reasons": reasons,
        "details": details,
    }


# =========================================================
# LEGACY WARNING SYSTEM
# =========================================================

def warnings(f, score):
    """
    Existing simple warning system.
    Kept for compatibility.
    """

    w = []

    vix = latest(
        f.get("VIX")
    )

    credit = latest(
        f.get("HY_SPREAD")
    )

    if not np.isnan(vix) and vix >= 25:
        w.append(
            "VIX elevated"
        )

    if not np.isnan(credit) and credit >= 4:
        w.append(
            "High-yield credit spread elevated"
        )

    if pct_delta(
        f.get("INDPRO"), 3
    ) < 0:

        w.append(
            "Industrial production momentum weakening"
        )

    if pct_delta(
        f.get("RETAIL"), 3
    ) < 0:

        w.append(
            "Retail-sales momentum weakening"
        )

    if delta(
        f.get("UNRATE"), 3
    ) > 0:

        w.append(
            "Unemployment trend rising"
        )

    if pct_delta(
        f.get("PCE"), 3
    ) > 0:

        w.append(
            "PCE trend accelerating"
        )

    if score <= -3:

        w.append(
            "Macro score entering risk zone"
        )

    return w


# =========================================================
# PULLBACK CLASSIFICATION
# =========================================================

def classify(dd, score, reg):

    if reg.startswith("F"):
        return (
            "F — Liquidity / Financial Shock"
        )

    if reg.startswith("E"):
        return (
            "E — Recession / Bear Risk"
        )

    if reg.startswith("C"):
        return (
            "C — Inflation / Rates Shock"
        )

    if dd <= -10 and score < 0:
        return (
            "D — Mixed Macro Stress"
        )

    if score < 3:
        return (
            "B — Growth Scare / Mixed"
        )

    return (
        "A — Healthy / Supportive"
    )


# =========================================================
# TRADING DECISION
# =========================================================

def decision(score, dd, w):

    if (
        score <= -4
        or dd <= -20
        or len(w) >= 5
    ):
        return "DEFENSIVE"

    if (
        score < 3
        or dd <= -10
        or len(w) >= 3
    ):
        return "WAIT / CONFIRM"

    return "SUPPORTIVE"


# =========================================================
# POSITION RISK
# =========================================================

def sl_tp(m, entry):

    previous_close = m.close.shift(1)

    true_range = pd.concat(
        [
            (m.high - m.low).abs(),
            (m.high - previous_close).abs(),
            (m.low - previous_close).abs(),
        ],
        axis=1
    ).max(axis=1)

    atr14 = float(
        true_range.rolling(14).mean().iloc[-1]
    )

    # Previous 5 COMPLETED candles
    lowest_low = float(
        m.low.iloc[-6:-1].min()
    )

    sl = (
        lowest_low -
        0.5 * atr14
    )

    risk = (
        entry - sl
    )

    tp = (
        entry +
        4 * risk
    )

    return sl, tp, risk
