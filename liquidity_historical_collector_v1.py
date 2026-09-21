"""
Liquidity Historical Collector v1
---------------------------------

Research-only historical liquidity data collector.

Sources:
- Federal Reserve H.4.1
- New York Fed reference rates

Indicators:
- Fed Total Assets
- Reserve Balances
- U.S. Treasury Securities
- Mortgage-Backed Securities
- Treasury General Account (TGA)
- Reverse Repurchase Agreements (ON RRP / RRP)
- SOFR
- EFFR

Research principles:
- Point-in-time safe
- Conservative availability-date semantics
- No trading signals
- No forecasts
- No liquidity score
- No Decision Engine integration
"""

from __future__ import annotations

import io
import os
import sys
from datetime import timedelta

import pandas as pd
import requests


# ============================================================
# Configuration
# ============================================================

START_DATE = pd.Timestamp(
    os.getenv(
        "LIQUIDITY_START_DATE",
        "2019-01-01",
    )
)

END_DATE = pd.Timestamp(
    os.getenv(
        "LIQUIDITY_END_DATE",
        pd.Timestamp.utcnow().date().isoformat(),
    )
)

OUTPUT_FILE = (
    "liquidity_historical_records_input_v1.csv"
)

SUMMARY_FILE = (
    "liquidity_historical_collection_summary_v1.csv"
)


# ============================================================
# Source URLs
# ============================================================

H41_CURRENT_URL = (
    "https://www.federalreserve.gov/"
    "releases/h41/Current/"
)

H41_DATA_URL = (
    "https://www.federalreserve.gov/"
    "datadownload/Choose.aspx?rel=H41"
)

SOFR_URL = (
    "https://markets.newyorkfed.org/"
    "api/rates/secured/sofr/"
    "search.json"
)

EFFR_URL = (
    "https://markets.newyorkfed.org/"
    "api/rates/unsecured/effr/"
    "search.json"
)


# ============================================================
# Metadata
# ============================================================

COLLECTOR_NAME = (
    "Liquidity Historical Collector v1"
)

SOURCE_H41 = (
    "Federal Reserve H.4.1"
)

SOURCE_NYFED = (
    "Federal Reserve Bank of New York"
)

AVAILABILITY_H41 = (
    "H.4.1 weekly release date used as "
    "conservative availability proxy; "
    "not exact publication timestamp."
)

AVAILABILITY_NYFED = (
    "New York Fed daily publication date "
    "used as conservative availability proxy."
)


# ============================================================
# HTTP helper
# ============================================================

def get_url(
    url: str,
    params: dict | None = None,
    timeout: int = 60,
) -> requests.Response:

    response = requests.get(
        url,
        params=params,
        timeout=timeout,
        headers={
            "User-Agent": (
                "US500-Macro-Intelligence/"
                "LiquidityCollector-v1"
            )
        },
    )

    response.raise_for_status()

    return response


# ============================================================
# Utility
# ============================================================

def clean_number(value):

    if pd.isna(value):
        return pd.NA

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).strip()

    if text in {
        "",
        "-",
        "—",
        "NA",
        "N/A",
        "nan",
        "None",
    }:
        return pd.NA

    text = (
        text
        .replace(",", "")
        .replace("$", "")
        .strip()
    )

    try:
        return float(text)
    except ValueError:
        return pd.NA


def normalize_columns(df: pd.DataFrame):

    df = df.copy()

    df.columns = [
        str(c).strip()
        for c in df.columns
    ]

    return df


# ============================================================
# H.4.1
# ============================================================

def collect_h41():

    print()
    print("=" * 70)
    print("Collecting Federal Reserve H.4.1")
    print("=" * 70)

    print(
        "Source:",
        H41_CURRENT_URL,
    )

    print(
        "Data page:",
        H41_DATA_URL,
    )

    # --------------------------------------------------------
    # IMPORTANT
    #
    # H.4.1 publishes a weekly release.
    #
    # The collector retrieves the official current
    # H.4.1 release and attempts to use its downloadable
    # historical CSV endpoints.
    #
    # If the historical endpoint structure changes,
    # fail explicitly rather than silently using another source.
    # --------------------------------------------------------

    # Official H.4.1 XML endpoint.
    xml_url = (
        "https://www.federalreserve.gov/"
        "datadownload/Output.aspx"
        "?rel=H41"
        "&filetype=xml"
        "&label=include"
        "&layout=seriescolumn"
        "&from=01/01/2019"
        "&to="
        + END_DATE.strftime("%m/%d/%Y")
    )

    print(
        "Requesting official H.4.1 XML..."
    )

    response = get_url(
        xml_url,
        timeout=120,
    )

    print(
        "HTTP status:",
        response.status_code,
    )

    content = response.content

    if not content:
        raise RuntimeError(
            "H.4.1 response is empty."
        )

    print(
        "Downloaded bytes:",
        len(content),
    )

    # --------------------------------------------------------
    # Parse XML
    # --------------------------------------------------------

    try:

        from xml.etree import ElementTree as ET

        root = ET.fromstring(content)

    except Exception as exc:

        raise RuntimeError(
            "Could not parse H.4.1 XML."
        ) from exc

    rows = []

    # --------------------------------------------------------
    # Locate series
    # --------------------------------------------------------

    for series in root.iter():

        tag = (
            series.tag.split("}")[-1]
            .lower()
        )

        if tag != "series":
            continue

        attrs = {
            str(k).lower(): str(v)
            for k, v in series.attrib.items()
        }

        series_name = (
            attrs.get("seriesname")
            or attrs.get("name")
            or attrs.get("description")
            or ""
        )

        series_id = (
            attrs.get("seriesid")
            or attrs.get("id")
            or ""
        )

        text_name = (
            series_name
            + " "
            + series_id
        ).lower()

        # ----------------------------------------------------
        # Identify required H.4.1 concepts.
        #
        # Matching is intentionally conservative.
        # ----------------------------------------------------

        indicator = None

        if (
            "reserve balances" in text_name
            and "depository" in text_name
        ):
            indicator = "RESERVE_BALANCES"

        elif (
            "reverse repurchase agreements"
            in text_name
        ):
            indicator = "ON_RRP"

        elif (
            "u.s. treasury, general account"
            in text_name
            or "treasury general account"
            in text_name
        ):
            indicator = "TGA"

        elif (
            "total assets" in text_name
            and "federal reserve" in text_name
        ):
            indicator = "FED_TOTAL_ASSETS"

        elif (
            "u.s. treasury securities"
            in text_name
            and "securities held outright"
            not in text_name
        ):
            indicator = "TREASURY_SECURITIES"

        elif (
            "mortgage-backed securities"
            in text_name
        ):
            indicator = "MBS"

        if indicator is None:
            continue

        # ----------------------------------------------------
        # Observations
        # ----------------------------------------------------

        for child in series:

            child_tag = (
                child.tag.split("}")[-1]
                .lower()
            )

            if child_tag not in {
                "obs",
                "observation",
                "data",
            }:
                continue

            child_attrs = {
                str(k).lower(): str(v)
                for k, v in child.attrib.items()
            }

            date_value = (
                child_attrs.get("date")
                or child_attrs.get(
                    "observation_date"
                )
                or child_attrs.get("time")
            )

            actual_value = (
                child_attrs.get("value")
                or child_attrs.get("actual")
            )

            if date_value is None:
                continue

            if actual_value is None:
                actual_value = (
                    child.text
                )

            if actual_value is None:
                continue

            rows.append(
                {
                    "indicator": indicator,
                    "observation_date": date_value,
                    "actual": clean_number(
                        actual_value
                    ),
                    "source": SOURCE_H41,
                    "source_url": H41_CURRENT_URL,
                    "frequency": "weekly",
                    "unit": "millions_usd",
                }
            )

    if not rows:

        raise RuntimeError(
            "H.4.1 parser returned zero observations. "
            "Official source structure may have changed."
        )

    df = pd.DataFrame(rows)

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "observation_date",
            "actual",
        ]
    )

    df = df[
        (df["observation_date"] >= START_DATE)
        &
        (df["observation_date"] <= END_DATE)
    ]

    # --------------------------------------------------------
    # Conservative availability
    #
    # H.4.1 is released Thursday and describes
    # the Wednesday/week-ended observation.
    #
    # We use the following Thursday as availability.
    # --------------------------------------------------------

    df["availability_date"] = (
        df["observation_date"]
        + pd.Timedelta(days=1)
    )

    df["availability_semantics"] = (
        AVAILABILITY_H41
    )

    df["point_in_time_safe"] = True

    df["revision_flag"] = False

    df["vintage"] = (
        df["availability_date"]
        .dt.strftime("%Y-%m-%d")
    )

    print(
        "H.4.1 rows:",
        len(df),
    )

    print(
        "H.4.1 indicators:",
        sorted(
            df["indicator"]
            .dropna()
            .unique()
            .tolist()
        ),
    )

    return df


# ============================================================
# New York Fed reference rates
# ============================================================

def collect_nyfed_rate(
    url: str,
    indicator: str,
):

    print()
    print(
        "=" * 70
    )
    print(
        "Collecting",
        indicator,
        "from New York Fed"
    )
    print(
        "=" * 70
    )

    params = {
        "startDate": START_DATE.strftime(
            "%Y-%m-%d"
        ),
        "endDate": END_DATE.strftime(
            "%Y-%m-%d"
        ),
        "type": "rate",
        "operation": "search",
    }

    response = get_url(
        url,
        params=params,
        timeout=120,
    )

    payload = response.json()

    # --------------------------------------------------------
    # Locate records robustly
    # --------------------------------------------------------

    records = None

    if isinstance(payload, dict):

        for key in [
            "refRates",
            "rates",
            "data",
            "results",
        ]:

            if (
                key in payload
                and isinstance(
                    payload[key],
                    list,
                )
            ):

                records = payload[key]
                break

    elif isinstance(payload, list):

        records = payload

    if not records:

        raise RuntimeError(
            f"{indicator}: New York Fed API "
            "returned no records."
        )

    df = pd.DataFrame(records)

    df = normalize_columns(df)

    # --------------------------------------------------------
    # Date
    # --------------------------------------------------------

    date_candidates = [
        "effectiveDate",
        "effective_date",
        "date",
        "observation_date",
    ]

    date_column = None

    for candidate in date_candidates:

        if candidate in df.columns:

            date_column = candidate
            break

    if date_column is None:

        raise RuntimeError(
            f"{indicator}: Could not identify "
            "date column. Columns: "
            f"{df.columns.tolist()}"
        )

    # --------------------------------------------------------
    # Rate
    # --------------------------------------------------------

    rate_candidates = [
        "percentRate",
        "percent_rate",
        "rate",
        "value",
    ]

    rate_column = None

    for candidate in rate_candidates:

        if candidate in df.columns:

            rate_column = candidate
            break

    if rate_column is None:

        raise RuntimeError(
            f"{indicator}: Could not identify "
            "rate column. Columns: "
            f"{df.columns.tolist()}"
        )

    df["observation_date"] = pd.to_datetime(
        df[date_column],
        errors="coerce",
    )

    df["actual"] = df[
        rate_column
    ].apply(clean_number)

    df = df.dropna(
        subset=[
            "observation_date",
            "actual",
        ]
    )

    df = df[
        (df["observation_date"] >= START_DATE)
        &
        (df["observation_date"] <= END_DATE)
    ]

    df["indicator"] = indicator

    df["unit"] = "percent"

    df["frequency"] = "daily"

    df["source"] = SOURCE_NYFED

    df["source_url"] = url

    df["availability_date"] = (
        df["observation_date"]
        + pd.Timedelta(days=1)
    )

    df["availability_semantics"] = (
        AVAILABILITY_NYFED
    )

    df["vintage"] = (
        df["availability_date"]
        .dt.strftime("%Y-%m-%d")
    )

    df["revision_flag"] = False

    df["point_in_time_safe"] = True

    df = df[
        [
            "indicator",
            "observation_date",
            "availability_date",
            "actual",
            "unit",
            "frequency",
            "source",
            "source_url",
            "vintage",
            "revision_flag",
            "point_in_time_safe",
            "availability_semantics",
        ]
    ]

    print(
        indicator,
        "rows:",
        len(df),
    )

    if not df.empty:

        print(
            "Date range:",
            df["observation_date"].min().date(),
            "->",
            df["observation_date"].max().date(),
        )

        print(
            "Latest value:",
            df.sort_values(
                "observation_date"
            ).iloc[-1]["actual"],
        )

    return df


# ============================================================
# Main
# ============================================================

def main():

    print()
    print("=" * 70)
    print(COLLECTOR_NAME)
    print("FIXED — Official Sources / Research Only")
    print("=" * 70)

    print(
        "Start date:",
        START_DATE.date(),
    )

    print(
        "End date:",
        END_DATE.date(),
    )

    print(
        "Research-only:",
        True,
    )

    print(
        "Decision Engine:",
        False,
    )

    print(
        "Trading signal:",
        False,
    )

    print(
        "Forecast:",
        False,
    )

    print()

    # --------------------------------------------------------
    # H.4.1
    # --------------------------------------------------------

    h41 = collect_h41()

    # --------------------------------------------------------
    # SOFR
    # --------------------------------------------------------

    sofr = collect_nyfed_rate(
        SOFR_URL,
        "SOFR",
    )

    # --------------------------------------------------------
    # EFFR
    # --------------------------------------------------------

    effr = collect_nyfed_rate(
        EFFR_URL,
        "EFFR",
    )

    # --------------------------------------------------------
    # Combine
    # --------------------------------------------------------

    df = pd.concat(
        [
            h41,
            sofr,
            effr,
        ],
        ignore_index=True,
    )

    # --------------------------------------------------------
    # Normalize
    # --------------------------------------------------------

    df["observation_date"] = pd.to_datetime(
        df["observation_date"],
        errors="coerce",
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
    )

    df["actual"] = df[
        "actual"
    ].apply(clean_number)

    # --------------------------------------------------------
    # Date filter
    # --------------------------------------------------------

    df = df[
        (df["observation_date"] >= START_DATE)
        &
        (df["observation_date"] <= END_DATE)
    ]

    # --------------------------------------------------------
    # Remove invalid records
    # --------------------------------------------------------

    df = df.dropna(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "actual",
        ]
    )

    # --------------------------------------------------------
    # Sort
    # --------------------------------------------------------

    df = df.sort_values(
        [
            "indicator",
            "observation_date",
            "availability_date",
        ]
    ).reset_index(drop=True)

    # --------------------------------------------------------
    # Duplicate protection
    # --------------------------------------------------------

    duplicate_mask = df.duplicated(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "vintage",
        ],
        keep=False,
    )

    duplicate_count = int(
        duplicate_mask.sum()
    )

    if duplicate_count:

        print(
            "WARNING: duplicate records:",
            duplicate_count,
        )

        df = df.drop_duplicates(
            subset=[
                "indicator",
                "observation_date",
                "availability_date",
                "vintage",
            ]
        )

    # --------------------------------------------------------
    # PIT validation
    # --------------------------------------------------------

    pit_failures = df[
        df["availability_date"]
        < df["observation_date"]
    ]

    if not pit_failures.empty:

        raise RuntimeError(
            "PIT validation failed: "
            "availability_date is before "
            "observation_date."
        )

    if not df[
        "point_in_time_safe"
    ].eq(True).all():

        raise RuntimeError(
            "PIT validation failed: "
            "not all rows are marked safe."
        )

    # --------------------------------------------------------
    # Required indicators
    # --------------------------------------------------------

    required_indicators = {
        "FED_TOTAL_ASSETS",
        "RESERVE_BALANCES",
        "TREASURY_SECURITIES",
        "MBS",
        "TGA",
        "ON_RRP",
        "SOFR",
        "EFFR",
    }

    available_indicators = set(
        df["indicator"]
        .unique()
        .tolist()
    )

    missing_indicators = (
        required_indicators
        - available_indicators
    )

    if missing_indicators:

        raise RuntimeError(
            "Missing required liquidity indicators: "
            + str(
                sorted(
                    missing_indicators
                )
            )
        )

    # --------------------------------------------------------
    # Add research metadata
    # --------------------------------------------------------

    df["research_only"] = True

    df["decision_engine_ready"] = False

    df["trading_signal_generated"] = False

    df["forecast_generated"] = False

    df["liquidity_score_generated"] = False

    # --------------------------------------------------------
    # Final column order
    # --------------------------------------------------------

    columns = [
        "indicator",
        "observation_date",
        "availability_date",
        "actual",
        "unit",
        "frequency",
        "source",
        "source_url",
        "vintage",
        "revision_flag",
        "point_in_time_safe",
        "availability_semantics",
        "research_only",
        "decision_engine_ready",
        "trading_signal_generated",
        "forecast_generated",
        "liquidity_score_generated",
    ]

    df = df[columns]

    # --------------------------------------------------------
    # Final validation
    # --------------------------------------------------------

    if df.empty:

        raise RuntimeError(
            "Final liquidity dataset is empty."
        )

    if df["indicator"].isna().any():

        raise RuntimeError(
            "Indicator contains missing values."
        )

    if df["actual"].isna().any():

        raise RuntimeError(
            "Actual contains missing values."
        )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary_rows = []

    for indicator, group in df.groupby(
        "indicator",
        sort=True,
    ):

        group = group.sort_values(
            "observation_date"
        )

        latest = group.iloc[-1]

        summary_rows.append(
            {
                "indicator": indicator,
                "rows": len(group),
                "first_observation": (
                    group[
                        "observation_date"
                    ].min()
                ),
                "last_observation": (
                    group[
                        "observation_date"
                    ].max()
                ),
                "latest_availability": (
                    latest[
                        "availability_date"
                    ]
                ),
                "latest_actual": (
                    latest["actual"]
                ),
                "point_in_time_safe": True,
                "research_only": True,
                "decision_engine_ready": False,
                "trading_signal_generated": False,
                "forecast_generated": False,
                "liquidity_score_generated": False,
            }
        )

    summary = pd.DataFrame(
        summary_rows
    )

    summary.to_csv(
        SUMMARY_FILE,
        index=False,
    )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "LIQUIDITY HISTORICAL COLLECTION COMPLETE"
    )
    print("=" * 70)

    print(
        "Total rows:",
        len(df),
    )

    print(
        "Indicators:",
        df["indicator"]
        .nunique(),
    )

    print(
        "Date range:",
        df["observation_date"].min().date(),
        "->",
        df["observation_date"].max().date(),
    )

    print()
    print(
        df.groupby("indicator")
        .size()
        .to_string()
    )

    print()
    print(
        "PIT safe:",
        df[
            "point_in_time_safe"
        ].all(),
    )

    print(
        "Research only:",
        df[
            "research_only"
        ].all(),
    )

    print(
        "Decision Engine:",
        df[
            "decision_engine_ready"
        ].any(),
    )

    print(
        "Trading signal:",
        df[
            "trading_signal_generated"
        ].any(),
    )

    print(
        "Forecast:",
        df[
            "forecast_generated"
        ].any(),
    )

    print(
        "Liquidity score:",
        df[
            "liquidity_score_generated"
        ].any(),
    )

    print()
    print(
        "Output:",
        OUTPUT_FILE,
    )

    print(
        "Summary:",
        SUMMARY_FILE,
    )

    print("=" * 70)


if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print()
        print(
            "ERROR:",
            str(exc),
        )

        sys.exit(1)
