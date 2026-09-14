import os

try:
    import streamlit as st
except Exception:
    st = None


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


# =========================
# General Configuration
# =========================

FRED_API_KEY = secret("FRED_API_KEY", "")

MARKET_TICKER = secret(
    "US500_TICKER",
    "^GSPC"
)

REFRESH_MINUTES = int(
    secret("REFRESH_MINUTES", 30)
)


# =========================
# Federal Reserve
# =========================

FED_URL = (
    "https://www.federalreserve.gov/"
    "monetarypolicy/fomccalendars.htm"
)


# =========================
# Database
# =========================

DB_PATH = "us500_macro_intelligence.db"


# =========================
# FRED Series
# =========================

FRED_SERIES = {
    "US10Y": "DGS10",
    "US2Y": "DGS2",
    "VIX": "VIXCLS",
    "DXY": "DTWEXBGS",
    "UNRATE": "UNRATE",
    "FEDFUNDS": "FEDFUNDS",
    "HY_SPREAD": "BAMLH0A0HYM2",
    "INDPRO": "INDPRO",
    "RETAIL": "RSAFS",
    "PCE": "PCE",
    "CORE_PCE": "PCEPILFE",
    "CPI": "CPIAUCSL",
    "REAL_GDP": "GDPC1"
}


# =========================
# BLS Series
# =========================

BLS_SERIES = {
    "CPI": "CUSR0000SA0",
    "CORE_CPI": "CUSR0000SA0L1E",
    "UNEMPLOYMENT": "LNS14000000",
    "NFP": "CES0000000001",
    "HOURLY_EARNINGS": "CES0500000003"
}
