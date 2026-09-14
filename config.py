import os
import streamlit as st


# =========================================================
# US500 MACRO INTELLIGENCE
# CONFIGURATION
# =========================================================


# =========================================================
# BASIC APP SETTINGS
# =========================================================

APP_NAME = "US500 Macro Intelligence"

MARKET_TICKER = os.getenv(
    "US500_TICKER",
    "^GSPC"
)

REFRESH_MINUTES = int(
    os.getenv(
        "REFRESH_MINUTES",
        "30"
    )
)


# =========================================================
# FRED API
# =========================================================

def get_secret(name, default=""):
    """
    Read value from Streamlit Secrets first,
    then environment variables.
    """

    try:
        value = st.secrets.get(name)

        if value:
            return value

    except Exception:
        pass

    return os.getenv(
        name,
        default
    )


FRED_API_KEY = get_secret(
    "FRED_API_KEY",
    ""
)


# =========================================================
# FRED SERIES
# =========================================================

FRED_SERIES = {

    # -----------------------------------------------------
    # INTEREST RATES
    # -----------------------------------------------------

    "US10Y": "DGS10",

    "US2Y": "DGS2",

    "T10Y2Y": "T10Y2Y",


    # -----------------------------------------------------
    # MARKET RISK / SENTIMENT
    # -----------------------------------------------------

    "VIX": "VIXCLS",

    "DXY": "DTWEXBGS",


    # -----------------------------------------------------
    # LABOR MARKET
    # -----------------------------------------------------

    "UNRATE": "UNRATE",

    "INITIAL_CLAIMS_4W": "IC4WSA",


    # -----------------------------------------------------
    # FED / MONETARY POLICY
    # -----------------------------------------------------

    "FEDFUNDS": "FEDFUNDS",


    # -----------------------------------------------------
    # CREDIT
    # -----------------------------------------------------

    "HY_SPREAD": "BAMLH0A0HYM2",

    "CORP_OAS": "BAMLC0A0CM",


    # -----------------------------------------------------
    # FINANCIAL CONDITIONS
    # -----------------------------------------------------

    "NFCI": "NFCI",


    # -----------------------------------------------------
    # ECONOMIC GROWTH
    # -----------------------------------------------------

    "INDPRO": "INDPRO",

    "RETAIL": "RSAFS",

    "REAL_GDP": "GDPC1",


    # -----------------------------------------------------
    # INFLATION
    # -----------------------------------------------------

    "PCE": "PCE",

    "CORE_PCE": "PCEPILFE",

    "CPI": "CPIAUCSL",
}


# =========================================================
# BLS SERIES
# =========================================================

BLS_SERIES = {

    "CPI": "CUSR0000SA0",

    "CORE_CPI": "CUSR0000SA0L1E",

    "UNEMPLOYMENT": "LNS14000000",

    "NFP": "CES0000000001",

    "HOURLY_EARNINGS": "CES0500000003",
}


# =========================================================
# FEDERAL RESERVE
# =========================================================

FED_URL = (
    "https://www.federalreserve.gov/"
    "monetarypolicy/fomccalendars.htm"
)


# =========================================================
# DATABASE
# =========================================================

DB_PATH = os.getenv(
    "DB_PATH",
    "us500_macro.db"
)
