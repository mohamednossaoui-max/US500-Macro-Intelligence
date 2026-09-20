"""
US500 Macro Intelligence
Financial Stress Intelligence — Historical Collector v1

FIXED 8

Research-only.
No Decision Engine integration.

Sources:
- VIX: Cboe daily historical CSV.
- Treasury 2Y/10Y: Federal Reserve H.15.
- NFCI/ANFCI: FRED API output_type=4
  (Initial Release Only).

PIT principle:
- FRED realtime_start is used as availability_date.
- Revised observations are NOT substituted.
"""

from __future__ import annotations

import hashlib
import io
import os
import time

import pandas as pd
import requests


# ============================================================
# CONFIGURATION
# ============================================================

OUT = "financial_stress_records_input_v1.csv"

START = pd.Timestamp("2020-01-01")
END = pd.Timestamp.today().normalize()


# ============================================================
# OFFICIAL SOURCES
# ============================================================

VIX_URL = (
    "https://cdn.cboe.com/"
    "api/global/us_indices/daily_prices/"
    "VIX_History.csv"
)

H15_CMT_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?"
    "rel=H15&series=bf17364827e38702b42a58cf8eaa3f78"
    "&lastobs=&from=&to=&filetype=csv&label=include"
    "&layout=seriescolumn&type=package"
)

H15_URL = (
    "https://www.federalreserve.gov/releases/h15/"
)

FRED_API_URL = (
    "https://api.stlouisfed.org/"
    "fred/series/observations"
)

CHICAGO_URL = (
    "https://www.chicagofed.org/"
    "research/data/nfci/current-data"
)


# ============================================================
# RUNTIME SETTINGS
# ============================================================

REQUEST_TIMEOUT = 90
REQUEST_TRIES = 5

FRED_API_TIMEOUT = 90
FRED_API_TRIES = 5


# ============================================================
# OUTPUT SCHEMA
# ============================================================

COLS = [
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


# ============================================================
# HTTP SESSION
# ============================================================

def session():

    s = requests.Session()

    s.headers.update(
        {
            "User-Agent":
                "US500-Macro-Intelligence/2.0",
            "Accept":
                "*/*",
        }
    )

    return s


def get(
    s,
    url,
    tries=REQUEST_TRIES,
    timeout=REQUEST_TIMEOUT,
):
    """
    Standard HTTP GET helper.

    No source substitution is performed.
    """

    last = None

    for i in range(tries):

        try:

            r = s.get(
                url,
                timeout=(20, timeout),
            )

            r.raise_for_status()

            return r

        except Exception as exc:

            last = exc

            print(
                f"HTTP request attempt "
                f"{i + 1}/{tries} failed: "
                f"{exc}"
            )

            if i < tries - 1:

                time.sleep(
                    2 ** i
                )

    raise RuntimeError(
        f"GET failed for source endpoint "
        f"after {tries} attempts: {last}"
    )


# ============================================================
# RECORD ID
# ============================================================

def rid(row):

    key = "|".join(
        str(row[c])
        for c in COLS
    )

    return hashlib.sha256(
        key.encode()
    ).hexdigest()


# ============================================================
# VIX
# ============================================================

def load_vix(s):

    print(
        "VIX: downloading Cboe "
        "historical data"
    )

    r = get(
        s,
        VIX_URL,
        tries=REQUEST_TRIES,
        timeout=REQUEST_TIMEOUT,
    )

    df = pd.read_csv(
        io.BytesIO(
            r.content
        )
    )

    df["DATE"] = pd.to_datetime(
        df["DATE"],
        errors="coerce",
    )

    df["CLOSE"] = pd.to_numeric(
        df["CLOSE"],
        errors="coerce",
    )

    df = df.dropna(
        subset=[
            "DATE",
            "CLOSE",
        ]
    )

    df = df[
        (df["DATE"] >= START)
        &
        (df["DATE"] <= END)
    ]

    rows = []

    for _, x in df.iterrows():

        d = x["DATE"]

        rows.append(
            {
                "indicator":
                    "VIX",

                "observation_date":
                    d.date().isoformat(),

                "availability_date":
                    d.date().isoformat(),

                "actual":
                    float(x["CLOSE"]),

                "unit":
                    "INDEX_LEVEL",

                "frequency":
                    "DAILY",

                "source":
                    "Cboe",

                "source_url":
                    VIX_URL,

                "vintage":
                    d.date().isoformat(),

                "revision_flag":
                    False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    "EOD_CLOSE",
            }
        )

    print(
        f"VIX: {len(rows)} records"
    )

    return rows


# ============================================================
# TREASURY 2Y / 10Y
# ============================================================

def load_treasury(
    s,
    package=None,
):
    """
    Load Treasury Constant Maturity
    2Y and 10Y from official Federal
    Reserve H.15.
    """

    print(
        "Treasury: downloading "
        "Federal Reserve H.15"
    )

    if package is None:

        r = get(
            s,
            H15_CMT_URL,
            tries=REQUEST_TRIES,
            timeout=REQUEST_TIMEOUT,
        )

        package = pd.read_csv(
            io.BytesIO(
                r.content
            ),
            header=5,
        )

    if package.shape[1] < 12:

        raise RuntimeError(
            "Unexpected H.15 Treasury "
            f"package shape: {package.shape}"
        )

    df = package.copy()

    date_col = df.columns[0]

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    # H.15 package:
    #
    # date,
    # 1m,
    # 3m,
    # 6m,
    # 1y,
    # 2y,
    # 3y,
    # 5y,
    # 7y,
    # 10y,
    # 20y,
    # 30y

    maturity_map = {
        "TREASURY_2Y":
            df.columns[5],

        "TREASURY_10Y":
            df.columns[9],
    }

    rows = []

    for indicator, value_col in (
        maturity_map.items()
    ):

        df[value_col] = pd.to_numeric(
            df[value_col],
            errors="coerce",
        )

        sub = df.dropna(
            subset=[
                date_col,
                value_col,
            ]
        )

        sub = sub[
            (sub[date_col] >= START)
            &
            (sub[date_col] <= END)
        ]

        for _, x in sub.iterrows():

            d = pd.Timestamp(
                x[date_col]
            )

            rows.append(
                {
                    "indicator":
                        indicator,

                    "observation_date":
                        d.date().isoformat(),

                    "availability_date":
                        d.date().isoformat(),

                    "actual":
                        float(
                            x[value_col]
                        ),

                    "unit":
                        "PERCENT",

                    "frequency":
                        "DAILY",

                    "source":
                        "Federal Reserve H.15",

                    "source_url":
                        H15_CMT_URL,

                    "vintage":
                        d.date().isoformat(),

                    "revision_flag":
                        False,

                    "point_in_time_safe":
                        True,

                    "availability_semantics":
                        "OFFICIAL_RELEASE",
                }
            )

    print(
        f"Treasury: {len(rows)} records"
    )

    return rows


# ============================================================
# FRED API KEY
# ============================================================

def get_fred_api_key():

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
# FRED API
# ============================================================

def get_fred_observations(
    s,
    series,
):
    """
    Retrieve FRED observations.

    output_type=4:
        Observations, Initial Release Only.

    realtime_start / realtime_end:
        Explicit real-time period.

    units=lin:
        Explicit linear units.

    The response error body is exposed
    for diagnostics instead of hiding it
    behind '400 Bad Request'.
    """

    api_key = get_fred_api_key()

    params = {

        "series_id":
            series,

        "api_key":
            api_key,

        "file_type":
            "json",

        # Observation period
        "observation_start":
            START.date().isoformat(),

        "observation_end":
            END.date().isoformat(),

        # Real-time period
        "realtime_start":
            START.date().isoformat(),

        "realtime_end":
            END.date().isoformat(),

        # Initial Release Only
        "output_type":
            4,

        # Explicit linear units
        "units":
            "lin",

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
                f"{series}: FRED API request "
                f"attempt "
                f"{attempt}/"
                f"{FRED_API_TRIES}"
            )

            r = s.get(
                FRED_API_URL,
                params=params,
                timeout=(
                    20,
                    FRED_API_TIMEOUT,
                ),
            )

            # =================================================
            # IMPORTANT:
            # Do NOT use raise_for_status()
            # before reading FRED error payload.
            # =================================================

            if not r.ok:

                try:

                    error_payload = (
                        r.json()
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
                        r.text[:1000]
                    )

                raise RuntimeError(
                    f"FRED HTTP "
                    f"{r.status_code}; "
                    f"error_code="
                    f"{error_code}; "
                    f"message="
                    f"{error_message}"
                )

            payload = r.json()

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
                    "observations."
                )

            observations = (
                payload["observations"]
            )

            print(
                f"{series}: FRED returned "
                f"{len(observations)} "
                "observations"
            )

            print(
                f"{series}: FRED output_type="
                f"{payload.get('output_type')}"
            )

            print(
                f"{series}: FRED observation "
                f"range="
                f"{payload.get('observation_start')} "
                f"→ "
                f"{payload.get('observation_end')}"
            )

            return observations

        except Exception as exc:

            last = exc

            print(
                f"{series}: FRED API attempt "
                f"{attempt} failed: "
                f"{exc}"
            )

            if attempt < FRED_API_TRIES:

                time.sleep(
                    2 ** (attempt - 1)
                )

    raise RuntimeError(
        f"{series}: FRED API retrieval "
        f"failed after "
        f"{FRED_API_TRIES} attempts: "
        f"{last}"
    )


# ============================================================
# LOAD NFCI / ANFCI INITIAL RELEASE
# ============================================================

def load_nfci_initial_release(
    s,
    series,
):
    """
    Load NFCI or ANFCI from FRED.

    output_type=4 means Initial Release Only.

    realtime_start is treated as
    availability_date.

    Revised data is never substituted.
    """

    observations = (
        get_fred_observations(
            s,
            series,
        )
    )

    rows = []

    seen = set()

    for obs in observations:

        observation_date = obs.get(
            "date"
        )

        value = obs.get(
            "value"
        )

        availability_date = obs.get(
            "realtime_start"
        )

        if not observation_date:
            continue

        if value in (
            None,
            "",
            ".",
            "nan",
            "NaN",
        ):
            continue

        if not availability_date:

            raise RuntimeError(
                f"{series}: missing "
                f"realtime_start for "
                f"{observation_date}"
            )

        od = pd.Timestamp(
            observation_date
        )

        ad = pd.Timestamp(
            availability_date
        )

        if pd.isna(od) or pd.isna(ad):
            continue

        if od < START or od > END:
            continue

        # =====================================================
        # PIT CHECK
        # =====================================================

        if ad < od:

            raise RuntimeError(
                f"{series}: PIT violation: "
                f"availability_date "
                f"{ad.date()} is earlier than "
                f"observation_date "
                f"{od.date()}"
            )

        key = (
            series,
            od.date().isoformat(),
        )

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "indicator":
                    series,

                "observation_date":
                    od.date().isoformat(),

                "availability_date":
                    ad.date().isoformat(),

                "actual":
                    float(value),

                "unit":
                    "INDEX_LEVEL",

                "frequency":
                    "WEEKLY",

                "source":
                    "Chicago Fed",

                "source_url":
                    CHICAGO_URL,

                "vintage":
                    ad.date().isoformat(),

                "revision_flag":
                    False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    "FRED_INITIAL_RELEASE",
            }
        )

    if not rows:

        raise RuntimeError(
            f"{series}: FRED returned zero "
            "usable initial-release "
            "observations."
        )

    print(
        f"{series}: "
        f"{len(rows)} PIT "
        "initial-release records"
    )

    return rows


# ============================================================
# NFCI + ANFCI
# ============================================================

def load_nfci_pair(s):

    rows = []

    print(
        "NFCI/ANFCI: using FRED API "
        "output_type=4 — "
        "Initial Release Only"
    )

    # Sequential intentionally.
    for series in (
        "NFCI",
        "ANFCI",
    ):

        try:

            series_rows = (
                load_nfci_initial_release(
                    s,
                    series,
                )
            )

            rows.extend(
                series_rows
            )

        except Exception as exc:

            raise RuntimeError(
                f"{series}: initial-release "
                f"retrieval failed: "
                f"{exc}"
            ) from exc

    # Defensive uniqueness
    out = {}

    for row in rows:

        key = (
            row["indicator"],
            row["observation_date"],
        )

        if key not in out:

            out[key] = row

        else:

            existing = out[key]

            if (
                row["availability_date"]
                <
                existing[
                    "availability_date"
                ]
            ):

                out[key] = row

    result = list(
        out.values()
    )

    print(
        "NFCI/ANFCI collected: "
        f"{len(result)} records"
    )

    return result


# ============================================================
# MAIN
# ============================================================

def main():

    print(
        "=================================================="
    )

    print(
        "US500 Macro Intelligence"
    )

    print(
        "Financial Stress Historical "
        "Collector v1"
    )

    print(
        "FIXED 8 — FRED API / "
        "Initial Release Only"
    )

    print(
        "Research-only — "
        "No Decision Engine"
    )

    print(
        "=================================================="
    )

    print(
        f"Start: {START.date()}"
    )

    print(
        f"End:   {END.date()}"
    )

    s = session()

    rows = []

    # ========================================================
    # VIX
    # ========================================================

    rows += load_vix(s)

    # ========================================================
    # TREASURY
    # ========================================================

    rows += load_treasury(s)

    # ========================================================
    # NFCI / ANFCI
    # ========================================================

    rows += load_nfci_pair(s)

    # ========================================================
    # DATAFRAME
    # ========================================================

    out = pd.DataFrame(
        rows,
        columns=COLS,
    )

    if out.empty:

        raise RuntimeError(
            "Collector produced zero records."
        )

    # ========================================================
    # NORMALIZE DATES
    # ========================================================

    out[
        "observation_date"
    ] = pd.to_datetime(
        out[
            "observation_date"
        ]
    )

    out[
        "availability_date"
    ] = pd.to_datetime(
        out[
            "availability_date"
        ]
    )

    # ========================================================
    # PIT QUALITY GATE
    # ========================================================

    bad = (
        out["availability_date"]
        <
        out["observation_date"]
    )

    if bad.any():

        print(
            out.loc[
                bad
            ].head(20).to_string(
                index=False
            )
        )

        raise AssertionError(
            "PIT QUALITY GATE FAILED: "
            "availability_date is earlier "
            "than observation_date."
        )

    if not out[
        "point_in_time_safe"
    ].all():

        raise AssertionError(
            "PIT QUALITY GATE FAILED: "
            "non-PIT-safe record found."
        )

    # ========================================================
    # REQUIRED INDICATORS
    # ========================================================

    required_indicators = {
        "VIX",
        "TREASURY_2Y",
        "TREASURY_10Y",
        "NFCI",
        "ANFCI",
    }

    actual_indicators = set(
        out[
            "indicator"
        ].unique()
    )

    missing = (
        required_indicators
        -
        actual_indicators
    )

    if missing:

        raise AssertionError(
            "Missing required indicators: "
            f"{sorted(missing)}"
        )

    # ========================================================
    # SORT
    # ========================================================

    out = out.sort_values(
        [
            "observation_date",
            "indicator",
        ]
    ).reset_index(
        drop=True
    )

    # ========================================================
    # RECORD IDS
    # ========================================================

    out["record_id"] = out.apply(
        rid,
        axis=1,
    )

    # ========================================================
    # SAVE
    # ========================================================

    out.to_csv(
        OUT,
        index=False,
    )

    # ========================================================
    # REPORT
    # ========================================================

    print(
        "=================================================="
    )

    print(
        "COLLECTION COMPLETE"
    )

    print(
        "=================================================="
    )

    print(
        f"Output: {OUT}"
    )

    print(
        f"Rows: {len(out)}"
    )

    print(
        "Indicators:"
    )

    print(
        out[
            "indicator"
        ]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print(
        "PIT:"
    )

    print(
        f"{int(out['point_in_time_safe'].sum())}"
        f"/"
        f"{len(out)}"
    )

    print(
        "PIT QUALITY GATE: PASS"
    )

    print(
        "Research-only guard: PASS"
    )

    print(
        "Decision Engine integration: NONE"
    )

    print(
        "=================================================="
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
