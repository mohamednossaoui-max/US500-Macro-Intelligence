"""
US500 Macro Intelligence
Financial Stress Intelligence — Historical Collector v1

Research-only. No Decision Engine integration.

Sources:
- VIX: Cboe daily historical CSV.
- Treasury 2Y/10Y: Federal Reserve H.15.
- NFCI/ANFCI: FRED API using output_type=4
  (Initial Release Only).

FIXED 7:
- Replaced ALFRED transport with FRED API.
- NFCI/ANFCI retrieved through official FRED API.
- output_type=4 preserves Initial Release Only semantics.
- FRED API key is read from GitHub Actions secret:
  FRED_API_KEY
- No fallback to revised data.
- PIT methodology preserved.
- Research-only.
- No Decision Engine integration.
"""

from __future__ import annotations

import hashlib
import io
import os
import time

import pandas as pd
import requests


OUT = "financial_stress_records_input_v1.csv"

START = pd.Timestamp("2020-01-01")
END = pd.Timestamp.today().normalize()


# ============================================================
# Official sources
# ============================================================

VIX_URL = (
    "https://cdn.cboe.com/api/global/us_indices/daily_prices/"
    "VIX_History.csv"
)

H15_CMT_URL = (
    "https://www.federalreserve.gov/datadownload/Output.aspx?"
    "rel=H15&series=bf17364827e38702b42a58cf8eaa3f78"
    "&lastobs=&from=&to=&filetype=csv&label=include"
    "&layout=seriescolumn&type=package"
)

FRED_API_URL = (
    "https://api.stlouisfed.org/fred/series/observations"
)

H15_URL = "https://www.federalreserve.gov/releases/h15/"

CHICAGO_URL = (
    "https://www.chicagofed.org/research/data/nfci/current-data"
)


# ============================================================
# Runtime settings
# ============================================================

REQUEST_TIMEOUT = 90
REQUEST_TRIES = 5

FRED_API_TIMEOUT = 90
FRED_API_TRIES = 5


# ============================================================
# Output schema
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
# HTTP session
# ============================================================

def session():
    s = requests.Session()

    s.headers.update(
        {
            "User-Agent": (
                "US500-Macro-Intelligence/2.0"
            )
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

            if i < tries - 1:
                time.sleep(2 ** i)

    raise RuntimeError(
        f"GET failed for source endpoint after "
        f"{tries} attempts: {last}"
    )


# ============================================================
# Record ID
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

    print("VIX: downloading Cboe historical data")

    r = get(
        s,
        VIX_URL,
        tries=REQUEST_TRIES,
        timeout=REQUEST_TIMEOUT,
    )

    df = pd.read_csv(
        io.BytesIO(r.content)
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
        & (df["DATE"] <= END)
    ]

    rows = []

    for _, x in df.iterrows():

        d = x["DATE"]

        rows.append(
            {
                "indicator": "VIX",

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
# Treasury 2Y / 10Y
# ============================================================

def load_treasury(
    s,
    package=None,
):
    """
    Load 2Y/10Y Treasury Constant Maturity
    from official Federal Reserve H.15.
    """

    print(
        "Treasury: downloading Federal Reserve H.15"
    )

    if package is None:

        r = get(
            s,
            H15_CMT_URL,
            tries=REQUEST_TRIES,
            timeout=REQUEST_TIMEOUT,
        )

        package = pd.read_csv(
            io.BytesIO(r.content),
            header=5,
        )

    if package.shape[1] < 12:

        raise RuntimeError(
            "Unexpected H.15 Treasury package shape: "
            f"{package.shape}"
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
        "TREASURY_2Y": df.columns[5],
        "TREASURY_10Y": df.columns[9],
    }

    rows = []

    for indicator, value_col in maturity_map.items():

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
            & (sub[date_col] <= END)
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
                        float(x[value_col]),

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
# FRED API
# ============================================================

def get_fred_api_key():

    api_key = os.environ.get(
        "FRED_API_KEY"
    )

    if not api_key:

        raise RuntimeError(
            "FRED_API_KEY GitHub Actions secret "
            "is missing."
        )

    return api_key


def get_fred_observations(
    s,
    series,
):
    """
    Retrieve FRED observations using:

        output_type=4

    which means:

        Observations, Initial Release Only.

    The API returns realtime_start for each
    observation. This becomes availability_date.
    """

    api_key = get_fred_api_key()

    params = {
        "series_id":
            series,

        "api_key":
            api_key,

        "file_type":
            "json",

        "observation_start":
            START.date().isoformat(),

        "observation_end":
            END.date().isoformat(),

        "output_type":
            4,

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
                f"attempt {attempt}/{FRED_API_TRIES}"
            )

            r = s.get(
                FRED_API_URL,
                params=params,
                timeout=(
                    20,
                    FRED_API_TIMEOUT,
                ),
            )

            r.raise_for_status()

            payload = r.json()

            if "observations" not in payload:

                raise RuntimeError(
                    f"FRED API response for {series} "
                    "does not contain observations."
                )

            observations = payload[
                "observations"
            ]

            print(
                f"{series}: FRED returned "
                f"{len(observations)} observations"
            )

            return observations

        except Exception as exc:

            last = exc

            print(
                f"{series}: FRED API attempt "
                f"{attempt} failed: {exc}"
            )

            if attempt < FRED_API_TRIES:
                time.sleep(
                    2 ** (attempt - 1)
                )

    raise RuntimeError(
        f"{series}: FRED API retrieval failed "
        f"after {FRED_API_TRIES} attempts: "
        f"{last}"
    )


# ============================================================
# Parse FRED Initial Release
# ============================================================

def load_nfci_initial_release(
    s,
    series,
):
    """
    Load NFCI/ANFCI using FRED API output_type=4.

    IMPORTANT:

    output_type=4 means Initial Release Only.

    Therefore we do NOT use the current revised
    historical series as a substitute.

    realtime_start is treated as the date the
    observation became available.
    """

    observations = get_fred_observations(
        s,
        series,
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

        if not value:
            continue

        if value in (
            ".",
            "",
            "nan",
            "NaN",
        ):
            continue

        if not availability_date:
            raise RuntimeError(
                f"{series}: missing realtime_start "
                f"for observation {observation_date}"
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

        # Conservative PIT check.
        if ad < od:

            raise RuntimeError(
                f"{series}: PIT violation: "
                f"availability_date {ad.date()} "
                f"is earlier than observation_date "
                f"{od.date()}"
            )

        key = (
            series,
            od.date().isoformat(),
        )

        # output_type=4 should already contain
        # the initial release. This is an additional
        # defensive uniqueness check.
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
            "usable initial-release observations."
        )

    print(
        f"{series}: "
        f"{len(rows)} PIT initial-release records"
    )

    return rows


# ============================================================
# NFCI + ANFCI
# ============================================================

def load_nfci_pair(s):

    rows = []

    print(
        "NFCI/ANFCI: using FRED API "
        "output_type=4 — Initial Release Only"
    )

    # Sequential requests intentionally.
    #
    # There are only two series and this avoids
    # unnecessary simultaneous API connections
    # from GitHub Actions.

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
                f"retrieval failed: {exc}"
            ) from exc

    # Defensive PIT key enforcement.

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
                < existing["availability_date"]
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
# Main
# ============================================================

def main():

    print(
        "=================================================="
    )

    print(
        "US500 Macro Intelligence"
    )

    print(
        "Financial Stress Historical Collector v1"
    )

    print(
        "FIXED 7 — FRED API / Initial Release Only"
    )

    print(
        "Research-only — No Decision Engine"
    )

    print(
        "=================================================="
    )

    s = session()

    rows = []

    # --------------------------------------------------------
    # VIX
    # --------------------------------------------------------

    rows += load_vix(s)

    # --------------------------------------------------------
    # Treasury 2Y / 10Y
    # --------------------------------------------------------

    treasury_package = None

    rows += load_treasury(
        s,
        treasury_package,
    )

    # --------------------------------------------------------
    # NFCI / ANFCI
    # --------------------------------------------------------

    rows += load_nfci_pair(s)

    # --------------------------------------------------------
    # Build 10Y - 2Y curve
    # --------------------------------------------------------

    tmp = pd.DataFrame(
        rows
    )

    for c in [
        "observation_date",
        "availability_date",
    ]:

        tmp[c] = pd.to_datetime(
            tmp[c]
        )

    t2 = (
        tmp[
            tmp.indicator
            == "TREASURY_2Y"
        ]
        .set_index(
            "observation_date"
        )
    )

    t10 = (
        tmp[
            tmp.indicator
            == "TREASURY_10Y"
        ]
        .set_index(
            "observation_date"
        )
    )

    common = (
        t2.index.intersection(
            t10.index
        )
    )

    print(
        f"Curve: {len(common)} "
        "common Treasury dates"
    )

    for d in common:

        a = (
            float(
                t10.loc[
                    d,
                    "actual",
                ]
            )
            -
            float(
                t2.loc[
                    d,
                    "actual",
                ]
            )
        )

        avail = max(
            t2.loc[
                d,
                "availability_date",
            ],
            t10.loc[
                d,
                "availability_date",
            ],
        )

        rows.append(
            {
                "indicator":
                    "CURVE_10Y_2Y",

                "observation_date":
                    d.date().isoformat(),

                "availability_date":
                    pd.Timestamp(
                        avail
                    ).date().isoformat(),

                "actual":
                    a,

                "unit":
                    "PERCENTAGE_POINTS",

                "frequency":
                    "DAILY",

                "source":
                    "Federal Reserve H.15",

                "source_url":
                    H15_URL,

                "vintage":
                    pd.Timestamp(
                        avail
                    ).date().isoformat(),

                "revision_flag":
                    False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    "OFFICIAL_RELEASE",
            }
        )

    # --------------------------------------------------------
    # DataFrame
    # --------------------------------------------------------

    out = pd.DataFrame(
        rows,
        columns=COLS,
    )

    out = out.drop_duplicates(
        subset=[
            "indicator",
            "observation_date",
            "availability_date",
            "vintage",
        ]
    )

    out = out.sort_values(
        [
            "observation_date",
            "indicator",
        ]
    ).reset_index(
        drop=True
    )

    # --------------------------------------------------------
    # Conservative Point-in-Time Quality Gate
    # --------------------------------------------------------

    od = pd.to_datetime(
        out["observation_date"]
    )

    ad = pd.to_datetime(
        out["availability_date"]
    )

    if (ad < od).any():

        bad = out.loc[
            ad < od
        ].head(10)

        raise AssertionError(
            "availability_date earlier "
            "than observation_date.\n"
            f"{bad.to_string()}"
        )

    if not out[
        "point_in_time_safe"
    ].all():

        raise AssertionError(
            "Non-PIT-safe record found"
        )

    # --------------------------------------------------------
    # Record IDs
    # --------------------------------------------------------

    out["record_id"] = out.apply(
        rid,
        axis=1,
    )

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    out.to_csv(
        OUT,
        index=False,
    )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    print(
        "=================================================="
    )

    print(
        "Financial Stress Historical "
        "Collector v1 — FIXED 7"
    )

    print(
        f"Records: {len(out)}"
    )

    print(
        f"Indicators: "
        f"{out.indicator.nunique()}"
    )

    print(
        "PIT safe: "
        f"{int(out.point_in_time_safe.sum())}"
        f"/{len(out)}"
    )

    print(
        "Records by indicator:"
    )

    print(
        out.groupby(
            "indicator"
        )
        .size()
        .to_string()
    )

    print(
        "PIT QUALITY GATE: PASS"
    )

    print(
        f"Output: {OUT}"
    )

    print(
        "=================================================="
    )


if __name__ == "__main__":
    main()
