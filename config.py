import os

try:
    import streamlit as st
except Exception:
    st = None


# ============================================================
# SECRET / ENVIRONMENT VARIABLE HELPER
# ============================================================

def secret(name, default=None):
    """
    Read a value from Streamlit Secrets first,
    then fall back to environment variables.
    """

    if st is not None:
        try:
            value = st.secrets.get(name, None)

            if value not in (None, ""):
                return value

        except Exception:
            pass

    return os.getenv(name, default)


# ============================================================
# GENERAL CONFIGURATION
# ============================================================

# FRED API key
FRED_API_KEY = secret(
    "FRED_API_KEY",
    ""
)


# US500 market ticker
# Default: S&P 500 index from Yahoo Finance
MARKET_TICKER = secret(
    "US500_TICKER",
    "^GSPC"
)


# Automatic refresh interval
REFRESH_MINUTES = int(
    secret(
        "REFRESH_MINUTES",
        30
    )
)


# ============================================================
# FEDERAL RESERVE
# ============================================================

FED_URL = (
    "https://www.federalreserve.gov/"
    "monetarypolicy/fomccalendars.htm"
)


# ============================================================
# DATABASE
# ============================================================

DB_PATH = "us500_macro_intelligence.db"


# ============================================================
# FRED SERIES
# ============================================================

FRED_SERIES = {

    # --------------------------------------------------------
    # INTEREST RATES
    # --------------------------------------------------------

    "US10Y": "DGS10",

    "US2Y": "DGS2",


    # --------------------------------------------------------
    # MARKET RISK / SENTIMENT
    # --------------------------------------------------------

    "VIX": "VIXCLS",

    "DXY": "DTWEXBGS",


    # --------------------------------------------------------
    # LABOR MARKET
    # --------------------------------------------------------

    "UNRATE": "UNRATE",

    # 4-week moving average of initial unemployment claims
    "INITIAL_CLAIMS_4W": "IC4WSA",


    # --------------------------------------------------------
    # FEDERAL RESERVE
    # --------------------------------------------------------

    "FEDFUNDS": "FEDFUNDS",


    # --------------------------------------------------------
    # CREDIT CONDITIONS
    # --------------------------------------------------------

    # ICE BofA US High Yield Index Option-Adjusted Spread
    "HY_SPREAD": "BAMLH0A0HYM2",

    # ICE BofA US Corporate Index Option-Adjusted Spread
    "CORP_OAS": "BAMLC0A0CM",


    # --------------------------------------------------------
    # FINANCIAL CONDITIONS
    # --------------------------------------------------------

    # Chicago Fed National Financial Conditions Index
    "NFCI": "NFCI",


    # --------------------------------------------------------
    # ECONOMIC GROWTH
    # --------------------------------------------------------

    # Industrial Production
    "INDPRO": "INDPRO",

    # Retail Sales
    "RETAIL": "RSAFS",

    # Real GDP
    "REAL_GDP": "GDPC1",


    # --------------------------------------------------------
    # INFLATION
    # --------------------------------------------------------

    # PCE Price Index
    "PCE": "PCE",

    # Core PCE Price Index
    "CORE_PCE": "PCEPILFE",

    # CPI Price Index
    "CPI": "CPIAUCSL"
}


# ============================================================
# BLS SERIES
# ============================================================

BLS_SERIES = {

    # Consumer Price Index
    "CPI": "CUSR0000SA0",

    # Core CPI
    "CORE_CPI": "CUSR0000SA0L1E",

    # Unemployment Rate
    "UNEMPLOYMENT": "LNS14000000",

    # Nonfarm Payrolls
    "NFP": "CES0000000001",

    # Average Hourly Earnings
    "HOURLY_EARNINGS": "CES0500000003"
}
