"""
US500 Macro Intelligence
Financial Stress Historical Collector v1 — FIXED 8

Research-only historical collector.

Purpose
-------
Collect historical financial-stress indicators with
point-in-time-safe availability semantics.

Indicators
----------
1. VIX
2. US Treasury 2Y
3. US Treasury 10Y
4. Chicago Fed NFCI
5. Chicago Fed ANFCI

PIT principle
-------------
For NFCI / ANFCI, FRED API output_type=4 is used:

    Observations, Initial Release Only

The FRED realtime_start field is used as the
availability_date.

No revised observation is substituted when the
initial-release request fails.

This file is RESEARCH-ONLY.
It must not be connected to the Decision Engine.
"""


from __future__ import annotations

import io
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

START = pd.Timestamp("2020-01-01", tz="UTC")

END = pd.Timestamp(
    datetime.now(timezone.utc)
).normalize()


OUTPUT_FILE = (
    "financial_stress_records_input_v1.csv"
)


# ------------------------------------------------------------
# FRED API
# ------------------------------------------------------------

FRED_API_URL = (
    "https://api.stlouisfed.org/"
    "fred/series/observations"
)

FRED_API_TRIES = 5

FRED_API_TIMEOUT = 90


# ------------------------------------------------------------
# HTTP
# ------------------------------------------------------------

REQUEST_TIMEOUT = 45

REQUEST_TRIES = 3


USER_AGENT = (
    "US500-Macro-Intelligence/"
    "Financial-Stress-Collector-v1 "
    "(research-only)"
)


# ============================================================
# SESSION
# ============================================================

def create_session() -> requests.Session:

    session = requests.Session()

    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
        }
    )

    return session


# ============================================================
# GENERIC HTTP GET
# ============================================================

def get(
    session: requests.Session,
    url: str,
    *,
    params=None,
    timeout=REQUEST_TIMEOUT,
    tries=REQUEST_TRIES,
):
    """
    Generic GET with retry handling.
    """

    last_error = None

    for attempt in range(
        1,
        tries + 1,
    ):

        try:

            response = session.get(
                url,
                params=params,
                timeout=timeout,
            )

            response.raise_for_status()

            return response

        except Exception as exc:

            last_error = exc

            print(
                f"HTTP request attempt "
                f"{attempt}/{tries} failed: "
                f"{exc}"
            )

            if attempt < tries:

                time.sleep(
                    2 ** (attempt - 1)
                )

    raise RuntimeError(
        f"HTTP request failed after "
        f"{tries} attempts: "
        f"{last_error}"
    )


# ============================================================
# FRED API KEY
# ============================================================

def get_fred_api_key() -> str:
    """
    Read FRED API key from environment.

    GitHub Actions must expose:

        FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
    """

    api_key = os.environ.get(
        "FRED_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "FRED_API_KEY GitHub Actions "
            "secret is missing."
        )

    return api_key


# ============================================================
# FRED OBSERVATIONS
# ============================================================

def get_fred_observations(
    session: requests.Session,
    series: str,
):
    """
    Retrieve FRED observations using:

        output_type=4

    FRED definition:

        Observations, Initial Release Only

    The FRED realtime_start / realtime_end
    parameters define the real-time period.

    units=lin is explicitly supplied because
    FRED output_type=4 requires linear units.

    IMPORTANT:
    The realtime_start field returned by FRED
    is later used as availability_date.
    """

    api_key = get_fred_api_key()


    params = {

        "series_id":
            series,

        "api_key":
            api_key,

        "file_type":
            "json",


        # ----------------------------------------------------
        # Observation window
        # ----------------------------------------------------

        "observation_start":
            START.date().isoformat(),

        "observation_end":
            END.date().isoformat(),


        # ----------------------------------------------------
        # Real-time period
        # ----------------------------------------------------

        "realtime_start":
            START.date().isoformat(),

        "realtime_end":
            END.date().isoformat(),


        # ----------------------------------------------------
        # Initial Release Only
        # ----------------------------------------------------

        "output_type":
            4,


        # ----------------------------------------------------
        # Required for output_type=4
        # ----------------------------------------------------

        "units":
            "lin",


        # ----------------------------------------------------
        # Ordering / limit
        # ----------------------------------------------------

        "sort_order":
            "asc",

        "limit":
            100000,
    }


    last = None


    for attempt in range(
        1,
        FRED_API_TRIES + 1,
    ):

        try:

            print(
                f"{series}: "
                f"FRED API request "
                f"attempt "
                f"{attempt}/"
                f"{FRED_API_TRIES}"
            )


            response = session.get(
                FRED_API_URL,
                params=params,
                timeout=(
                    20,
                    FRED_API_TIMEOUT,
                ),
            )


            # =================================================
            # DIAGNOSTIC ERROR HANDLING
            # =================================================

            if not response.ok:

                try:

                    error_payload = (
                        response.json()
                    )

                    error_code = (
                        error_payload.get(
                            "error_code",
                            "unknown",
                        )
                    )

                    error_message = (
                        error_payload.get(
                            "error_message",
                            "unknown",
                        )
                    )

                except Exception:

                    error_code = (
                        "unknown"
                    )

                    error_message = (
                        response.text[:500]
                    )


                raise RuntimeError(
                    f"FRED HTTP "
                    f"{response.status_code}; "
                    f"error_code="
                    f"{error_code}; "
                    f"message="
                    f"{error_message}"
                )


            # =================================================
            # JSON
            # =================================================

            payload = response.json()


            if "error_code" in payload:

                raise RuntimeError(
                    "FRED API error: "
                    f"{payload.get('error_code')} "
                    f"{payload.get('error_message')}"
                )


            if "observations" not in payload:

                raise RuntimeError(
                    f"FRED API response for "
                    f"{series} does not contain "
                    f"observations."
                )


            observations = (
                payload["observations"]
            )


            print(
                f"{series}: "
                f"FRED returned "
                f"{len(observations)} "
                f"observations"
            )


            print(
                f"{series}: "
                f"FRED output_type="
                f"{payload.get('output_type')}"
            )


            print(
                f"{series}: "
                f"FRED observation range="
                f"{payload.get('observation_start')} "
                f"→ "
                f"{payload.get('observation_end')}"
            )


            return observations


        except Exception as exc:

            last = exc


            print(
                f"{series}: "
                f"FRED API attempt "
                f"{attempt} failed: "
                f"{exc}"
            )


            if attempt < FRED_API_TRIES:

                time.sleep(
                    2 ** (attempt - 1)
                )


    raise RuntimeError(
        f"{series}: "
        f"FRED API retrieval failed "
        f"after "
        f"{FRED_API_TRIES} attempts: "
        f"{last}"
    )


# ============================================================
# FRED → DATAFRAME
# ============================================================

def load_fred_initial_release(
    session: requests.Session,
    series: str,
) -> pd.DataFrame:
    """
    Convert FRED initial-release observations
    into the normalized internal structure.
    """

    observations = get_fred_observations(
        session,
        series,
    )


    rows = []


    for obs in observations:

        observation_date = pd.to_datetime(
            obs.get("date"),
            errors="coerce",
            utc=True,
        )


        availability_date = pd.to_datetime(
            obs.get("realtime_start"),
            errors="coerce",
            utc=True,
        )


        value = pd.to_numeric(
            obs.get("value"),
            errors="coerce",
        )


        if pd.isna(observation_date):

            continue


        if pd.isna(availability_date):

            raise RuntimeError(
                f"{series}: missing "
                "realtime_start in "
                "initial-release record."
            )


        if pd.isna(value):

            continue


        # =====================================================
        # PIT GATE
        # =====================================================

        if availability_date < observation_date:

            raise RuntimeError(
                f"{series}: PIT violation: "
                f"availability_date "
                f"{availability_date} "
                f"is earlier than "
                f"observation_date "
                f"{observation_date}"
            )


        rows.append(
            {
                "indicator": series,

                "observation_date":
                    observation_date,

                "availability_date":
                    availability_date,

                "actual":
                    float(value),

                "unit":
                    "index",

                "frequency":
                    "weekly",

                "source":
                    "Federal Reserve Bank of St. Louis / FRED",

                "source_url":
                    (
                        "https://fred.stlouisfed.org/"
                        f"series/{series}"
                    ),

                "vintage":
                    "initial_release",

                "revision_flag":
                    False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    "initial_release",
            }
        )


    df = pd.DataFrame(rows)


    if df.empty:

        raise RuntimeError(
            f"{series}: "
            "FRED returned no usable "
            "initial-release observations."
        )


    df = (
        df.sort_values(
            [
                "observation_date",
                "availability_date",
            ]
        )
        .drop_duplicates(
            subset=[
                "indicator",
                "observation_date",
            ],
            keep="first",
        )
        .reset_index(drop=True)
    )


    return df


# ============================================================
# NFCI / ANFCI
# ============================================================

def load_nfci_pair(
    session: requests.Session,
):

    print(
        "NFCI/ANFCI: using FRED API "
        "output_type=4 — "
        "Initial Release Only"
    )


    results = {}


    # Sequential intentionally.
    # This avoids unnecessary API pressure.

    for series in (
        "NFCI",
        "ANFCI",
    ):

        print(
            f"{series}: "
            "loading initial-release "
            "observations"
        )


        results[series] = (
            load_fred_initial_release(
                session,
                series,
            )
        )


        print(
            f"{series}: "
            f"{len(results[series])} "
            "usable PIT records"
        )


    return (
        results["NFCI"],
        results["ANFCI"],
    )


# ============================================================
# VIX
# ============================================================

def load_vix(
    session: requests.Session,
) -> pd.DataFrame:
    """
    Load CBOE VIX daily historical data.
    """

    url = (
        "https://cdn.cboe.com/"
        "api/global/us_indices/"
        "daily_prices/VIX_History.csv"
    )


    print(
        "VIX: downloading "
        "CBOE historical data"
    )


    response = get(
        session,
        url,
    )


    df = pd.read_csv(
        io.BytesIO(
            response.content
        )
    )


    df.columns = [
        str(c).strip()
        for c in df.columns
    ]


    # --------------------------------------------------------
    # Locate date / close columns
    # --------------------------------------------------------

    date_column = None
    close_column = None


    for c in df.columns:

        lc = c.lower()


        if lc == "date":

            date_column = c


        if lc in (
            "close",
            "close price",
        ):

            close_column = c


    if date_column is None:

        raise RuntimeError(
            "VIX: date column not found."
        )


    if close_column is None:

        raise RuntimeError(
            "VIX: close column not found."
        )


    df["observation_date"] = (
        pd.to_datetime(
            df[date_column],
            errors="coerce",
            utc=True,
        )
    )


    df["actual"] = pd.to_numeric(
        df[close_column],
        errors="coerce",
    )


    df = df.dropna(
        subset=[
            "observation_date",
            "actual",
        ]
    )


    start = START
    end = END


    df = df[
        (
            df["observation_date"]
            >= start
        )
        &
        (
            df["observation_date"]
            <= end
        )
    ].copy()


    df["indicator"] = "VIX"

    df["availability_date"] = (
        df["observation_date"]
    )

    df["unit"] = "index"

    df["frequency"] = "daily"

    df["source"] = "Cboe"

    df["source_url"] = url

    df["vintage"] = (
        "daily_historical"
    )

    df["revision_flag"] = False

    df["point_in_time_safe"] = True

    df["availability_semantics"] = (
        "observation_date"
    )


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


    df = (
        df.sort_values(
            "observation_date"
        )
        .drop_duplicates(
            subset=[
                "indicator",
                "observation_date",
            ]
        )
        .reset_index(drop=True)
    )


    print(
        f"VIX: {len(df)} records"
    )


    return df


# ============================================================
# TREASURY H.15
# ============================================================

def load_treasury(
    session: requests.Session,
) -> pd.DataFrame:
    """
    Load US Treasury 2Y and 10Y rates
    from Federal Reserve H.15.
    """

    url = (
        "https://www.federalreserve.gov/"
        "datadownload/Output.aspx"
        "?rel=H15"
        "&filetype=csv"
        "&label=include"
        "&layout=seriescolumn"
        "&from=01/01/2020"
        "&to=12/31/2030"
    )


    print(
        "Treasury: downloading "
        "Federal Reserve H.15"
    )


    response = get(
        session,
        url,
        timeout=60,
    )


    raw = response.text


    # --------------------------------------------------------
    # H.15 CSV may contain metadata before data.
    # Detect the actual CSV header.
    # --------------------------------------------------------

    lines = raw.splitlines()


    header_index = None


    for i, line in enumerate(lines):

        low = line.lower()


        if (
            "series name" in low
            and "date" in low
        ):

            header_index = i

            break


        if (
            "date" in low
            and (
                "2-year" in low
                or "10-year" in low
            )
        ):

            header_index = i

            break


    if header_index is None:

        raise RuntimeError(
            "Treasury: could not detect "
            "H.15 CSV header."
        )


    csv_text = "\n".join(
        lines[header_index:]
    )


    df = pd.read_csv(
        io.StringIO(csv_text)
    )


    # --------------------------------------------------------
    # Identify date column
    # --------------------------------------------------------

    date_column = None


    for c in df.columns:

        if str(c).strip().lower() == "date":

            date_column = c

            break


    if date_column is None:

        raise RuntimeError(
            "Treasury: date column not found."
        )


    df["observation_date"] = (
        pd.to_datetime(
            df[date_column],
            errors="coerce",
            utc=True,
        )
    )


    # --------------------------------------------------------
    # Locate Treasury columns
    # --------------------------------------------------------

    columns = list(df.columns)


    treasury_2y = None
    treasury_10y = None


    for c in columns:

        name = str(c).lower()


        # Common H.15 naming patterns
        if (
            (
                "2-year" in name
                or "2 year" in name
                or "2-year treasury" in name
            )
            and treasury_2y is None
        ):

            treasury_2y = c


        if (
            (
                "10-year" in name
                or "10 year" in name
                or "10-year treasury" in name
            )
            and treasury_10y is None
        ):

            treasury_10y = c


    # --------------------------------------------------------
    # If labels differ, attempt maturity detection.
    # --------------------------------------------------------

    if treasury_2y is None:

        for c in columns:

            name = str(c).lower()

            if (
                "2" in name
                and (
                    "treasury" in name
                    or "constant" in name
                    or "yield" in name
                )
            ):

                treasury_2y = c

                break


    if treasury_10y is None:

        for c in columns:

            name = str(c).lower()

            if (
                "10" in name
                and (
                    "treasury" in name
                    or "constant" in name
                    or "yield" in name
                )
            ):

                treasury_10y = c

                break


    if treasury_2y is None:

        raise RuntimeError(
            "Treasury: 2Y column not found."
        )


    if treasury_10y is None:

        raise RuntimeError(
            "Treasury: 10Y column not found."
        )


    frames = []


    for series_name, column in (
        ("UST2Y", treasury_2y),
        ("UST10Y", treasury_10y),
    ):

        temp = df[
            [
                "observation_date",
                column,
            ]
        ].copy()


        temp["actual"] = pd.to_numeric(
            temp[column],
            errors="coerce",
        )


        temp = temp.dropna(
            subset=[
                "observation_date",
                "actual",
            ]
        )


        temp = temp[
            (
                temp["observation_date"]
                >= START
            )
            &
            (
                temp["observation_date"]
                <= END
            )
        ].copy()


        temp["indicator"] = (
            series_name
        )

        temp["availability_date"] = (
            temp["observation_date"]
        )

        temp["unit"] = "percent"

        temp["frequency"] = "daily"

        temp["source"] = (
            "Federal Reserve H.15"
        )

        temp["source_url"] = url

        temp["vintage"] = (
            "daily_historical"
        )

        temp["revision_flag"] = False

        temp["point_in_time_safe"] = True

        temp["availability_semantics"] = (
            "observation_date"
        )


        temp = temp[
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


        frames.append(temp)


    result = pd.concat(
        frames,
        ignore_index=True,
    )


    result = (
        result.sort_values(
            [
                "indicator",
                "observation_date",
            ]
        )
        .drop_duplicates(
            subset=[
                "indicator",
                "observation_date",
            ]
        )
        .reset_index(drop=True)
    )


    print(
        f"Treasury: "
        f"{len(result)} records"
    )


    return result


# ============================================================
# PIT QUALITY GATE
# ============================================================

def run_pit_quality_gate(
    df: pd.DataFrame,
) -> None:

    print(
        "\nRunning PIT quality gate..."
    )


    if df.empty:

        raise RuntimeError(
            "PIT QUALITY GATE: "
            "FAIL — empty dataset."
        )


    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    required = {

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
    }


    missing = (
        required
        - set(df.columns)
    )


    if missing:

        raise RuntimeError(
            "PIT QUALITY GATE: "
            f"FAIL — missing columns: "
            f"{sorted(missing)}"
        )


    # --------------------------------------------------------
    # Availability must not precede observation
    # --------------------------------------------------------

    invalid_dates = df[
        df["availability_date"]
        <
        df["observation_date"]
    ]


    if not invalid_dates.empty:

        raise RuntimeError(
            "PIT QUALITY GATE: "
            "FAIL — availability_date "
            "is earlier than "
            "observation_date."
        )


    # --------------------------------------------------------
    # All records must be PIT safe
    # --------------------------------------------------------

    if not df[
        "point_in_time_safe"
    ].all():

        raise RuntimeError(
            "PIT QUALITY GATE: "
            "FAIL — at least one "
            "record is not "
            "point_in_time_safe."
        )


    # --------------------------------------------------------
    # No missing actual values
    # --------------------------------------------------------

    if df["actual"].isna().any():

        raise RuntimeError(
            "PIT QUALITY GATE: "
            "FAIL — missing actual values."
        )


    print(
        "PIT QUALITY GATE: PASS"
    )


# ============================================================
# NORMALIZE DATA TYPES
# ============================================================

def normalize_dataframe(
    df: pd.DataFrame,
) -> pd.DataFrame:

    df = df.copy()


    df["observation_date"] = (
        pd.to_datetime(
            df["observation_date"],
            utc=True,
            errors="coerce",
        )
    )


    df["availability_date"] = (
        pd.to_datetime(
            df["availability_date"],
            utc=True,
            errors="coerce",
        )
    )


    df["actual"] = pd.to_numeric(
        df["actual"],
        errors="coerce",
    )


    df["revision_flag"] = (
        df["revision_flag"]
        .astype(bool)
    )


    df["point_in_time_safe"] = (
        df["point_in_time_safe"]
        .astype(bool)
    )


    df = df.sort_values(
        [
            "indicator",
            "observation_date",
            "availability_date",
        ]
    )


    return df.reset_index(
        drop=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=" * 70
    )

    print(
        "US500 Macro Intelligence"
    )

    print(
        "Financial Stress Historical "
        "Collector v1 — FIXED 8"
    )

    print(
        "Research-only"
    )

    print(
        "=" * 70
    )


    print(
        f"Start: {START}"
    )

    print(
        f"End:   {END}"
    )


    # ========================================================
    # SESSION
    # ========================================================

    session = create_session()


    # ========================================================
    # VIX
    # ========================================================

    vix = load_vix(
        session
    )


    # ========================================================
    # TREASURY
    # ========================================================

    treasury = load_treasury(
        session
    )


    # ========================================================
    # NFCI / ANFCI
    # ========================================================

    nfci, anfci = load_nfci_pair(
        session
    )


    # ========================================================
    # COMBINE
    # ========================================================

    df = pd.concat(
        [
            vix,
            treasury,
            nfci,
            anfci,
        ],
        ignore_index=True,
    )


    # ========================================================
    # NORMALIZE
    # ========================================================

    df = normalize_dataframe(
        df
    )


    # ========================================================
    # PIT QUALITY GATE
    # ========================================================

    run_pit_quality_gate(
        df
    )


    # ========================================================
    # FINAL VALIDATION
    # ========================================================

    expected_indicators = {
        "VIX",
        "UST2Y",
        "UST10Y",
        "NFCI",
        "ANFCI",
    }


    actual_indicators = set(
        df["indicator"].unique()
    )


    missing_indicators = (
        expected_indicators
        - actual_indicators
    )


    if missing_indicators:

        raise RuntimeError(
            "FINAL VALIDATION: "
            f"missing indicators: "
            f"{sorted(missing_indicators)}"
        )


    # ========================================================
    # SAVE
    # ========================================================

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )


    # ========================================================
    # SUMMARY
    # ========================================================

    print(
        "\n" + "=" * 70
    )

    print(
        "COLLECTION COMPLETE"
    )

    print(
        "=" * 70
    )


    print(
        f"Output: {OUTPUT_FILE}"
    )


    print(
        f"Rows: {len(df)}"
    )


    print(
        "\nIndicators:"
    )


    print(
        df["indicator"]
        .value_counts()
        .sort_index()
        .to_string()
    )


    print(
        "\nPIT:"
    )


    print(
        f"{int(df['point_in_time_safe'].sum())}"
        f" / "
        f"{len(df)}"
    )


    print(
        "\nAvailability semantics:"
    )


    print(
        df[
            [
                "indicator",
                "availability_semantics",
                "vintage",
            ]
        ]
        .drop_duplicates()
        .sort_values("indicator")
        .to_string(index=False)
    )


    print(
        "\nResearch-only guard: PASS"
    )


    print(
        "Decision Engine integration: NONE"
    )


    print(
        "=" * 70
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    main()
