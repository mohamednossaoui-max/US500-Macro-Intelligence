import numpy as np
import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

PULLBACKS = [3, 5, 10, 20, 30]


# ============================================================
# BASIC DATA HELPERS
# ============================================================

def latest(x):
    """
    Return latest value from a DataFrame containing a 'value' column.
    """

    if x is None or x.empty:
        return np.nan

    try:
        values = x["value"].dropna()

        if values.empty:
            return np.nan

        return float(values.iloc[-1])

    except Exception:
        return np.nan


def delta(x, n=1):
    """
    Absolute change versus n observations ago.
    """

    if x is None or x.empty:
        return np.nan

    try:
        values = x["value"].dropna()

        if len(values) <= n:
            return np.nan

        return float(
            values.iloc[-1] -
            values.iloc[-1 - n]
        )

    except Exception:
        return np.nan


def pct_delta(x, n=1):
    """
    Percentage change versus n observations ago.
    """

    if x is None or x.empty:
        return np.nan

    try:

        values = x["value"].dropna()

        if len(values) <= n:
            return np.nan

        current = float(values.iloc[-1])
        previous = float(values.iloc[-1 - n])

        if previous == 0:
            return np.nan

        return (
            (current / previous) - 1
        ) * 100

    except Exception:
        return np.nan


# ============================================================
# SAFE NUMERIC HELPERS
# ============================================================

def safe_float(value, default=0.0):

    try:

        if value is None:
            return default

        value = float(value)

        if np.isnan(value):
            return default

        return value

    except Exception:

        return default


# ============================================================
# MARKET STATE
# ============================================================

def state(m):

    if m is None or m.empty:

        return (
            np.nan,
            np.nan,
            np.nan,
            np.nan,
        )

    data = m.copy()

    price = float(
        data["close"].iloc[-1]
    )

    ath = float(
        data["close"].cummax().iloc[-1]
    )

    previous_close = (
        data["close"].shift(1)
    )

    true_range = pd.concat(
        [
            (
                data["high"] -
                data["low"]
            ).abs(),

            (
                data["high"] -
                previous_close
            ).abs(),

            (
                data["low"] -
                previous_close
            ).abs(),
        ],
        axis=1,
    ).max(axis=1)

    atr_series = (
        true_range
        .rolling(14)
        .mean()
    )

    atr = (
        float(atr_series.iloc[-1])
        if not pd.isna(atr_series.iloc[-1])
        else np.nan
    )

    drawdown = (
        (price / ath) - 1
    ) * 100

    return (
        price,
        ath,
        drawdown,
        atr,
    )


# ============================================================
# MACRO ANALYSIS
# ============================================================

def analyze(f, fed="Neutral"):

    growth_score = 0

    # --------------------------------------------------------
    # Industrial Production
    # --------------------------------------------------------

    indpro_change = pct_delta(
        f.get("INDPRO"),
        3
    )

    if not np.isnan(indpro_change):

        growth_score += int(
            np.sign(indpro_change)
        )

    # --------------------------------------------------------
    # Retail Sales
    # --------------------------------------------------------

    retail_change = pct_delta(
        f.get("RETAIL"),
        3
    )

    if not np.isnan(retail_change):

        growth_score += int(
            np.sign(retail_change)
        )

    # --------------------------------------------------------
    # Unemployment
    # --------------------------------------------------------

    unemployment_change = delta(
        f.get("UNRATE"),
        3
    )

    if not np.isnan(
        unemployment_change
    ):

        growth_score -= int(
            np.sign(
                unemployment_change
            )
        )

    # --------------------------------------------------------
    # PCE
    # --------------------------------------------------------

    pce_change = pct_delta(
        f.get("PCE"),
        3
    )

    if not np.isnan(pce_change):

        growth_score -= int(
            np.sign(pce_change)
        )

    # --------------------------------------------------------
    # Base macro score
    # --------------------------------------------------------

    score = growth_score

    # --------------------------------------------------------
    # Fed stance
    # --------------------------------------------------------

    fed_text = str(
        fed
    ).strip().lower()

    if fed_text == "dovish":

        score += 2

    elif fed_text == "hawkish":

        score -= 2

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    vix = latest(
        f.get("VIX")
    )

    if not np.isnan(vix):

        if vix >= 30:
            score -= 2

        elif vix >= 25:
            score -= 1

        elif vix < 18:
            score += 1

    # --------------------------------------------------------
    # High Yield Spread
    # --------------------------------------------------------

    credit = latest(
        f.get("HY_SPREAD")
    )

    if not np.isnan(credit):

        if credit >= 6:
            score -= 2

        elif credit >= 5:
            score -= 1

        elif credit < 3.5:
            score += 1

    # --------------------------------------------------------
    # 10Y
    # --------------------------------------------------------

    us10y = latest(
        f.get("US10Y")
    )

    score = int(
        np.clip(
            score,
            -10,
            10,
        )
    )

    # ========================================================
    # REGIME CLASSIFICATION
    # ========================================================

    if (
        not np.isnan(vix)
        and vix >= 35
    ) or (
        not np.isnan(credit)
        and credit >= 6
    ):

        regime = (
            "F — Liquidity / Financial Shock"
        )

    elif score <= -4:

        regime = (
            "E — Recession / Bear Risk"
        )

    elif (
        fed_text == "hawkish"
        and not np.isnan(pce_change)
        and pce_change > 0
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

    return (
        score,
        regime,
        {
            "growth": growth_score,
            "vix": vix,
            "credit": credit,
            "10y": us10y,
            "fed": fed,
        },
    )


# ============================================================
# BASIC WARNINGS
# ============================================================

def warnings(
    f,
    score,
):

    w = []

    vix = latest(
        f.get("VIX")
    )

    credit = latest(
        f.get("HY_SPREAD")
    )

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    if (
        not np.isnan(vix)
        and vix >= 25
    ):

        w.append(
            "VIX elevated"
        )

    # --------------------------------------------------------
    # Credit
    # --------------------------------------------------------

    if (
        not np.isnan(credit)
        and credit >= 4
    ):

        w.append(
            "High-yield credit spread elevated"
        )

    # --------------------------------------------------------
    # Industrial Production
    # --------------------------------------------------------

    if (
        pct_delta(
            f.get("INDPRO"),
            3
        ) < 0
    ):

        w.append(
            "Industrial production momentum weakening"
        )

    # --------------------------------------------------------
    # Retail Sales
    # --------------------------------------------------------

    if (
        pct_delta(
            f.get("RETAIL"),
            3
        ) < 0
    ):

        w.append(
            "Retail-sales momentum weakening"
        )

    # --------------------------------------------------------
    # Unemployment
    # --------------------------------------------------------

    if (
        delta(
            f.get("UNRATE"),
            3
        ) > 0
    ):

        w.append(
            "Unemployment trend rising"
        )

    # --------------------------------------------------------
    # PCE
    # --------------------------------------------------------

    if (
        pct_delta(
            f.get("PCE"),
            3
        ) > 0
    ):

        w.append(
            "PCE trend accelerating"
        )

    # --------------------------------------------------------
    # Macro Score
    # --------------------------------------------------------

    if score <= -3:

        w.append(
            "Macro score entering risk zone"
        )

    return w


# ============================================================
# REGIME CLASSIFICATION
# ============================================================

def classify(
    dd,
    score,
    reg,
):

    reg_text = str(
        reg
    )

    if reg_text.startswith("F"):

        return (
            "F — Liquidity / Financial Shock"
        )

    if reg_text.startswith("E"):

        return (
            "E — Recession / Bear Risk"
        )

    if reg_text.startswith("C"):

        return (
            "C — Inflation / Rates Shock"
        )

    if (
        dd <= -10
        and score < 0
    ):

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


# ============================================================
# EARLY WARNING SYSTEM
# ============================================================

def early_warning(f):

    # --------------------------------------------------------
    # Component maximums
    # --------------------------------------------------------

    component_max = {
        "Credit": 20,
        "Labor": 20,
        "Yield Curve": 15,
        "Financial Conditions": 20,
        "Market Risk": 15,
        "Macro Momentum": 10,
    }

    # ========================================================
    # CREDIT
    # ========================================================

    credit_score = 0

    hy = latest(
        f.get("HY_SPREAD")
    )

    corp_oas = latest(
        f.get("CORP_OAS")
    )

    hy_change_60 = pct_delta(
        f.get("HY_SPREAD"),
        60
    )

    if not np.isnan(hy):

        if hy >= 6:
            credit_score += 12

        elif hy >= 5:
            credit_score += 9

        elif hy >= 4:
            credit_score += 5

    if not np.isnan(
        hy_change_60
    ):

        if hy_change_60 >= 30:
            credit_score += 8

        elif hy_change_60 >= 15:
            credit_score += 5

        elif hy_change_60 >= 8:
            credit_score += 3

    if not np.isnan(corp_oas):

        if corp_oas >= 3:
            credit_score += 5

        elif corp_oas >= 2.5:
            credit_score += 3

    credit_score = min(
        credit_score,
        component_max["Credit"]
    )

    # ========================================================
    # LABOR
    # ========================================================

    labor_score = 0

    claims_change = pct_delta(
        f.get("INITIAL_CLAIMS_4W"),
        12
    )

    unemployment_change = delta(
        f.get("UNRATE"),
        3
    )

    if not np.isnan(
        claims_change
    ):

        if claims_change >= 8:
            labor_score += 12

        elif claims_change >= 5:
            labor_score += 8

        elif claims_change >= 3:
            labor_score += 4

    if not np.isnan(
        unemployment_change
    ):

        if unemployment_change >= 0.2:
            labor_score += 8

        elif unemployment_change >= 0.1:
            labor_score += 4

    labor_score = min(
        labor_score,
        component_max["Labor"]
    )

    # ========================================================
    # YIELD CURVE
    # ========================================================

    yield_score = 0

    curve = latest(
        f.get("T10Y2Y")
    )

    curve_change_60 = delta(
        f.get("T10Y2Y"),
        60
    )

    if not np.isnan(curve):

        if curve < -0.50:
            yield_score += 10

        elif curve < 0:
            yield_score += 7

    if not np.isnan(
        curve_change_60
    ):

        if curve_change_60 <= -0.50:
            yield_score += 5

        elif curve_change_60 <= -0.25:
            yield_score += 3

    yield_score = min(
        yield_score,
        component_max["Yield Curve"]
    )

    # ========================================================
    # FINANCIAL CONDITIONS
    # ========================================================

    financial_score = 0

    nfci = latest(
        f.get("NFCI")
    )

    nfci_change_4 = delta(
        f.get("NFCI"),
        4
    )

    if not np.isnan(nfci):

        if nfci >= 1:
            financial_score += 12

        elif nfci >= 0.5:
            financial_score += 8

        elif nfci > 0:
            financial_score += 4

    if not np.isnan(
        nfci_change_4
    ):

        if nfci_change_4 >= 0.30:
            financial_score += 8

        elif nfci_change_4 >= 0.15:
            financial_score += 5

        elif nfci_change_4 >= 0.08:
            financial_score += 2

    financial_score = min(
        financial_score,
        component_max["Financial Conditions"]
    )

    # ========================================================
    # MARKET RISK
    # ========================================================

    market_score = 0

    vix = latest(
        f.get("VIX")
    )

    dxy_change_60 = pct_delta(
        f.get("DXY"),
        60
    )

    vix_change_20 = pct_delta(
        f.get("VIX"),
        20
    )

    if not np.isnan(vix):

        if vix >= 35:
            market_score += 15

        elif vix >= 30:
            market_score += 10

        elif vix >= 25:
            market_score += 6

        elif vix >= 20:
            market_score += 3

    if not np.isnan(
        vix_change_20
    ):

        if vix_change_20 >= 50:
            market_score += 5

        elif vix_change_20 >= 25:
            market_score += 3

    if not np.isnan(
        dxy_change_60
    ):

        if dxy_change_60 >= 8:
            market_score += 3

        elif dxy_change_60 >= 5:
            market_score += 2

    market_score = min(
        market_score,
        component_max["Market Risk"]
    )

    # ========================================================
    # MACRO MOMENTUM
    # ========================================================

    macro_score = 0

    indpro_change = pct_delta(
        f.get("INDPRO"),
        3
    )

    retail_change = pct_delta(
        f.get("RETAIL"),
        3
    )

    pce_change = pct_delta(
        f.get("PCE"),
        3
    )

    if (
        not np.isnan(indpro_change)
        and indpro_change < 0
    ):

        macro_score += 3

    if (
        not np.isnan(retail_change)
        and retail_change < 0
    ):

        macro_score += 3

    if (
        not np.isnan(pce_change)
        and pce_change > 0
    ):

        macro_score += 4

    macro_score = min(
        macro_score,
        component_max["Macro Momentum"]
    )

    # ========================================================
    # TOTAL
    # ========================================================

    total = (
        credit_score
        + labor_score
        + yield_score
        + financial_score
        + market_score
        + macro_score
    )

    total = int(
        np.clip(
            total,
            0,
            100,
        )
    )

    # ========================================================
    # LEVEL
    # ========================================================

    if total >= 75:

        level = "CRITICAL"

    elif total >= 50:

        level = "HIGH"

    elif total >= 25:

        level = "MODERATE"

    else:

        level = "LOW"

    # ========================================================
    # REASONS
    # ========================================================

    reasons = []

    if credit_score > 0:
        reasons.append(
            "Credit conditions are showing deterioration."
        )

    if labor_score > 0:
        reasons.append(
            "Labor-market leading indicators are deteriorating."
        )

    if yield_score > 0:
        reasons.append(
            "Yield-curve conditions are signaling increased risk."
        )

    if financial_score > 0:
        reasons.append(
            "Financial conditions are tightening."
        )

    if market_score > 0:
        reasons.append(
            "Market-risk indicators are elevated."
        )

    if macro_score > 0:
        reasons.append(
            "Macro momentum indicators are weakening."
        )

    if not reasons:

        reasons.append(
            "No significant early-warning deterioration detected."
        )

    return {

        "score": total,

        "level": level,

        "components": {

            "Credit": credit_score,

            "Labor": labor_score,

            "Yield Curve": yield_score,

            "Financial Conditions": financial_score,

            "Market Risk": market_score,

            "Macro Momentum": macro_score,
        },

        "max_components": component_max,

        "reasons": reasons,

        "indicators": {

            "HY Spread": hy,

            "Corporate OAS": corp_oas,

            "Claims 4W Change": claims_change,

            "Unemployment Change": unemployment_change,

            "10Y-2Y": curve,

            "NFCI": nfci,

            "VIX": vix,

            "DXY 60D Change": dxy_change_60,

            "VIX 20D Change": vix_change_20,

            "Industrial Production Change": indpro_change,

            "Retail Sales Change": retail_change,

            "PCE Change": pce_change,
        },
    }


# ============================================================
# TECHNICAL CONFIRMATION
# ============================================================

def technical_confirmation(m):

    """
    Daily technical confirmation.

    Five factors:

        1. Price > SMA200
        2. SMA50 > SMA200
        3. Higher Low
        4. Price > SMA20
        5. RSI(14) > 50

    Score:

        4-5 = STRONG
        3   = PARTIAL
        0-2 = WEAK

    This is a confirmation filter,
    NOT an automatic execution signal.
    """

    if (
        m is None
        or m.empty
        or len(m) < 220
    ):

        return {

            "score": 0,

            "max": 5,

            "status": "UNAVAILABLE",

            "factors": [],

            "values": {},
        }

    data = m.copy()

    # --------------------------------------------------------
    # Moving averages
    # --------------------------------------------------------

    data["SMA20"] = (
        data["close"]
        .rolling(20)
        .mean()
    )

    data["SMA50"] = (
        data["close"]
        .rolling(50)
        .mean()
    )

    data["SMA200"] = (
        data["close"]
        .rolling(200)
        .mean()
    )

    # --------------------------------------------------------
    # RSI
    # --------------------------------------------------------

    price_change = (
        data["close"]
        .diff()
    )

    gains = price_change.clip(
        lower=0
    )

    losses = -price_change.clip(
        upper=0
    )

    avg_gain = (
        gains
        .rolling(14)
        .mean()
    )

    avg_loss = (
        losses
        .rolling(14)
        .mean()
    )

    rs = (
        avg_gain /
        avg_loss.replace(
            0,
            np.nan
        )
    )

    data["RSI14"] = (
        100 -
        (
            100 /
            (1 + rs)
        )
    )

    # --------------------------------------------------------
    # Current values
    # --------------------------------------------------------

    close = float(
        data["close"].iloc[-1]
    )

    sma20 = float(
        data["SMA20"].iloc[-1]
    )

    sma50 = float(
        data["SMA50"].iloc[-1]
    )

    sma200 = float(
        data["SMA200"].iloc[-1]
    )

    rsi = float(
        data["RSI14"].iloc[-1]
    )

    # --------------------------------------------------------
    # Higher Low
    # --------------------------------------------------------

    recent_low = float(
        data["low"]
        .iloc[-10:-1]
        .min()
    )

    previous_low = float(
        data["low"]
        .iloc[-20:-10]
        .min()
    )

    higher_low = (
        recent_low >
        previous_low
    )

    # --------------------------------------------------------
    # Factors
    # --------------------------------------------------------

    factors = []

    # 1
    price_above_200 = (
        close > sma200
    )

    factors.append(
        {
            "factor": "Price > SMA200",

            "status": (
                "PASS"
                if price_above_200
                else "FAIL"
            ),

            "value": (
                f"{close:.2f} vs "
                f"{sma200:.2f}"
            ),
        }
    )

    # 2
    trend_positive = (
        sma50 > sma200
    )

    factors.append(
        {
            "factor": "SMA50 > SMA200",

            "status": (
                "PASS"
                if trend_positive
                else "FAIL"
            ),

            "value": (
                f"{sma50:.2f} vs "
                f"{sma200:.2f}"
            ),
        }
    )

    # 3
    factors.append(
        {
            "factor": "Higher Low",

            "status": (
                "PASS"
                if higher_low
                else "FAIL"
            ),

            "value": (
                f"{recent_low:.2f} vs "
                f"{previous_low:.2f}"
            ),
        }
    )

    # 4
    price_above_20 = (
        close > sma20
    )

    factors.append(
        {
            "factor": "Price > SMA20",

            "status": (
                "PASS"
                if price_above_20
                else "FAIL"
            ),

            "value": (
                f"{close:.2f} vs "
                f"{sma20:.2f}"
            ),
        }
    )

    # 5
    momentum_positive = (
        rsi > 50
    )

    factors.append(
        {
            "factor": "RSI(14) > 50",

            "status": (
                "PASS"
                if momentum_positive
                else "FAIL"
            ),

            "value": f"{rsi:.2f}",
        }
    )

    # --------------------------------------------------------
    # Score
    # --------------------------------------------------------

    score = sum(
        1
        for factor in factors
        if factor["status"] == "PASS"
    )

    # --------------------------------------------------------
    # Status
    # --------------------------------------------------------

    if score >= 4:

        status = "STRONG"

    elif score == 3:

        status = "PARTIAL"

    else:

        status = "WEAK"

    return {

        "score": score,

        "max": 5,

        "status": status,

        "factors": factors,

        "values": {

            "close": close,

            "sma20": sma20,

            "sma50": sma50,

            "sma200": sma200,

            "rsi14": rsi,

            "recent_low": recent_low,

            "previous_low": previous_low,
        },
    }


# ============================================================
# FINAL DECISION ENGINE
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

    regime_text = str(
        regime
    )

    # ========================================================
    # 1. CRITICAL SYSTEMIC STRESS
    # ========================================================

    if early_score >= 75:

        return {

            "decision":
                "CRITICAL — NO NEW TRADE",

            "color":
                "red",

            "reason":
                (
                    "Early Warning is CRITICAL. "
                    "The strategy should not assume "
                    "that a deep pullback is automatically "
                    "a buying opportunity."
                ),
        }

    # ========================================================
    # 2. RECESSION / BEAR RISK
    # ========================================================

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
                ),
        }

    # ========================================================
    # 3. FINANCIAL SHOCK
    # ========================================================

    if regime_text.startswith("F"):

        return {

            "decision":
                "DEFENSIVE",

            "color":
                "red",

            "reason":
                (
                    "Financial/liquidity stress "
                    "is detected."
                ),
        }

    # ========================================================
    # 4. HIGH EARLY WARNING
    # ========================================================

    if early_score >= 50:

        return {

            "decision":
                "WAIT / CONFIRM",

            "color":
                "orange",

            "reason":
                (
                    "Multiple leading indicators "
                    "are showing meaningful deterioration."
                ),
        }

    # ========================================================
    # 5. MODERATE EARLY WARNING
    # ========================================================

    if early_score >= 25:

        return {

            "decision":
                "CAUTION",

            "color":
                "yellow",

            "reason":
                (
                    "Early-warning indicators are deteriorating. "
                    "A pullback should not be treated "
                    "as automatically healthy."
                ),
        }

    # ========================================================
    # 6. INFLATION / RATE SHOCK
    # ========================================================

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
                ),
        }

    # ========================================================
    # 7. MIXED STRESS
    # ========================================================

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
                ),
        }

    # ========================================================
    # 8. TECHNICAL CONFIRMATION
    # ========================================================

    if technical_status == "UNAVAILABLE":

        return {

            "decision":
                "CAUTION — TECHNICAL DATA UNAVAILABLE",

            "color":
                "yellow",

            "reason":
                (
                    "There is not enough Daily market data "
                    "to confirm the technical structure."
                ),
        }

    if technical_score <= 2:

        return {

            "decision":
                "CAUTION — TECHNICAL CONFIRMATION WEAK",

            "color":
                "yellow",

            "reason":
                (
                    "Macro conditions are supportive, "
                    "but technical confirmation is weak."
                ),
        }

    if technical_score == 3:

        return {

            "decision":
                "SUPPORTIVE / CONFIRM",

            "color":
                "yellow",

            "reason":
                (
                    "Macro conditions are supportive and "
                    "technical structure is partially confirmed."
                ),
        }

    # ========================================================
    # 9. VERY DEEP DRAWDOWN
    # ========================================================

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
                ),
        }

    # ========================================================
    # 10. MODERATE DRAWDOWN
    # ========================================================

    if drawdown <= -10:

        return {

            "decision":
                "SUPPORTIVE / CONFIRM",

            "color":
                "green",

            "reason":
                (
                    "Macro conditions remain relatively "
                    "supportive, but the depth of the correction "
                    "requires confirmation."
                ),
        }

    # ========================================================
    # 11. NORMAL PULLBACK
    # ========================================================

    if (
        early_score < 25
        and macro_score >= 3
        and technical_score >= 4
    ):

        return {

            "decision":
                "SUPPORTIVE",

            "color":
                "green",

            "reason":
                (
                    "Macro conditions are supportive, "
                    "early-warning stress is low, and "
                    "technical confirmation is strong."
                ),
        }

    # ========================================================
    # DEFAULT
    # ========================================================

    return {

        "decision":
            "CAUTION",

        "color":
            "yellow",

        "reason":
            (
                "Signals are not sufficiently strong "
                "to classify the environment as clearly supportive."
            ),
    }


# ============================================================
# LEGACY DECISION FUNCTION
# ============================================================

def decision(
    score,
    dd,
    w,
):

    """
    Backward-compatible decision function.

    The application should use decision_engine()
    for the final decision.
    """

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


# ============================================================
# ATR
# ============================================================

def atr14(m):

    if (
        m is None
        or m.empty
        or len(m) < 15
    ):

        return np.nan

    previous_close = (
        m["close"].shift(1)
    )

    true_range = pd.concat(
        [

            (
                m["high"] -
                m["low"]
            ).abs(),

            (
                m["high"] -
                previous_close
            ).abs(),

            (
                m["low"] -
                previous_close
            ).abs(),

        ],
        axis=1,
    ).max(axis=1)

    atr = (
        true_range
        .rolling(14)
        .mean()
        .iloc[-1]
    )

    return (
        float(atr)
        if not pd.isna(atr)
        else np.nan
    )


# ============================================================
# SL / TP
# ============================================================

def sl_tp(
    m,
    entry,
):

    """
    Mechanical long setup:

        SL =
            lowest Low of previous 5
            completed Daily candles
            - 0.5 * ATR(14)

        TP =
            Entry + 4 * Risk

    Current candle is excluded.
    """

    if (
        m is None
        or m.empty
        or len(m) < 20
    ):

        return (
            np.nan,
            np.nan,
            np.nan,
        )

    atr = atr14(
        m
    )

    if np.isnan(atr):

        return (
            np.nan,
            np.nan,
            np.nan,
        )

    # --------------------------------------------------------
    # Previous 5 COMPLETED candles
    # --------------------------------------------------------

    previous_five = (
        m["low"]
        .iloc[-6:-1]
    )

    lowest_low = float(
        previous_five.min()
    )

    sl = (
        lowest_low -
        0.5 * atr
    )

    risk = (
        float(entry) -
        sl
    )

    if risk <= 0:

        return (
            sl,
            np.nan,
            risk,
        )

    tp = (
        float(entry) +
        4 * risk
    )

    return (
        sl,
        tp,
        risk,
    )


# ============================================================
# PULLBACK CALCULATION
# ============================================================

def pullback_levels(
    price,
    ath,
):

    levels = []

    if (
        price is None
        or ath is None
        or np.isnan(price)
        or np.isnan(ath)
        or ath <= 0
    ):

        return levels

    for percentage in PULLBACKS:

        level = (
            ath *
            (1 - percentage / 100)
        )

        current_dd = (
            (price / ath) - 1
        ) * 100

        levels.append(
            {
                "level": percentage,

                "price": level,

                "current_drawdown":
                    current_dd,

                "distance_from_price":
                    price - level,
            }
        )

    return levels


# ============================================================
# POSITION SIZE
# ============================================================

def position_size(
    risk_dollars,
    entry,
    stop,
    point_value=1.0,
):

    """
    Generic position sizing.

    risk per unit =
        abs(entry - stop) * point_value

    quantity =
        risk dollars / risk per unit
    """

    try:

        risk_dollars = float(
            risk_dollars
        )

        entry = float(
            entry
        )

        stop = float(
            stop
        )

        point_value = float(
            point_value
        )

    except Exception:

        return np.nan

    price_risk = abs(
        entry - stop
    )

    if (
        price_risk <= 0
        or point_value <= 0
        or risk_dollars <= 0
    ):

        return np.nan

    risk_per_unit = (
        price_risk *
        point_value
    )

    quantity = (
        risk_dollars /
        risk_per_unit
    )

    return quantity


# ============================================================
# COMPLETE ANALYSIS OBJECT
# ============================================================

def build_analysis(
    market,
    macro_data,
    fed="Neutral",
):

    # --------------------------------------------------------
    # Market state
    # --------------------------------------------------------

    price, ath, drawdown, atr = state(
        market
    )

    # --------------------------------------------------------
    # Macro
    # --------------------------------------------------------

    macro_score, regime, macro_details = analyze(
        macro_data,
        fed
    )

    # --------------------------------------------------------
    # Warnings
    # --------------------------------------------------------

    basic_warnings = warnings(
        macro_data,
        macro_score
    )

    # --------------------------------------------------------
    # Early Warning
    # --------------------------------------------------------

    ew = early_warning(
        macro_data
    )

    # --------------------------------------------------------
    # Classification
    # --------------------------------------------------------

    classified_regime = classify(
        drawdown,
        macro_score,
        regime
    )

    # --------------------------------------------------------
    # Technical
    # --------------------------------------------------------

    technical = technical_confirmation(
        market
    )

    # --------------------------------------------------------
    # Pullbacks
    # --------------------------------------------------------

    pullbacks = pullback_levels(
        price,
        ath
    )

    # --------------------------------------------------------
    # Decision
    # --------------------------------------------------------

    final_decision = decision_engine(

        early_score=ew["score"],

        early_level=ew["level"],

        macro_score=macro_score,

        regime=classified_regime,

        drawdown=drawdown,

        technical_score=technical["score"],

        technical_status=technical["status"],
    )

    return {

        "market": {

            "price": price,

            "ath": ath,

            "drawdown": drawdown,

            "atr14": atr,
        },

        "macro": {

            "score": macro_score,

            "regime": classified_regime,

            "details": macro_details,
        },

        "warnings": basic_warnings,

        "early_warning": ew,

        "technical": technical,

        "pullbacks": pullbacks,

        "decision": final_decision,
    }
