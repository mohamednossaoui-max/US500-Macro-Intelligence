"""
US500 Macro Intelligence
Financial Stress Intelligence — Historical Collector v1

Research-only. No Decision Engine integration.

Sources:
- VIX: Cboe daily historical CSV.
- Treasury 2Y/10Y: Federal Reserve H.15.
- NFCI/ANFCI: Chicago Fed series via ALFRED initial-release-only transport.
  ALFRED output_type=4 supplies the initial release and its realtime_start date.

FIXED 6:
- Improved ALFRED transport reliability for CI runners.
- curl IPv4 + HTTP/1.1 transport.
- Longer timeout and retry/backoff.
- requests fallback.
- PIT methodology unchanged.
- No revised-data fallback.
"""

from __future__ import annotations

import io
import time
import hashlib
import re
import subprocess

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from urllib.parse import quote

import pandas as pd
import requests


OUT = "financial_stress_records_input_v1.csv"

START = pd.Timestamp("2020-01-01")
END = pd.Timestamp.today().normalize()


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

ALFRED_URL = "https://api.stlouisfed.org/fred/series/observations"

ALFRED_INITIAL_RELEASE = (
    "https://alfred.stlouisfed.org/graph/alfredgraph.csv"
    "?id={series}&output_type=4&cosd={start}&coed={end}"
)

ALFRED_CHUNK_MONTHS = 6

ALFRED_TRANSPORT_TIMEOUT = 90


H15_URL = "https://www.federalreserve.gov/releases/h15/"

CHICAGO_URL = (
    "https://www.chicagofed.org/research/data/nfci/current-data"
)


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


def session():
    s = requests.Session()

    s.headers.update(
        {
            "User-Agent": "US500-Macro-Intelligence/2.0"
        }
    )

    return s


def _curl_get(url, timeout=90, tries=3):
    """
    Reliable transport for public CSV endpoints on CI runners.

    Used specifically for ALFRED because direct requests can time out
    from GitHub Actions runners.
    """

    last = None

    for i in range(tries):
        try:
            cp = subprocess.run(
                [
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--location",
                    "--ipv4",
                    "--http1.1",
                    "--connect-timeout",
                    "20",
                    "--max-time",
                    str(timeout),
                    "--retry",
                    "1",
                    "--retry-delay",
                    "2",
                    "--retry-all-errors",
                    "-A",
                    "US500-Macro-Intelligence/2.0",
                    url,
                ],
                check=True,
                capture_output=True,
                timeout=timeout + 10,
            )

            return cp.stdout

        except Exception as exc:
            last = exc

            if i < tries - 1:
                time.sleep(2 ** i)

    raise RuntimeError(
        f"curl GET failed: {url}: {last}"
    )


def get(s, url, tries=4, timeout=45):
    """
    HTTP GET helper.

    ALFRED:
        Try curl first because GitHub Actions runners have shown
        intermittent requests timeouts against ALFRED.

    Other sources:
        Continue using requests.

    No source substitution is performed here.
    """

    last = None

    # Dedicated ALFRED transport path.
    if "alfred.stlouisfed.org/graph/alfredgraph.csv" in url:
        try:
            content = _curl_get(
                url,
                timeout=max(90, timeout),
                tries=3,
            )

            r = requests.Response()
            r.status_code = 200
            r.url = url
            r._content = content

            return r

        except Exception as exc:
            last = exc

            print(
                "ALFRED curl transport failed; "
                f"trying requests: {exc}"
            )

    # Standard requests fallback.
    for i in range(tries):
        try:
            r = s.get(
                url,
                timeout=(20, timeout),
            )

            r.raise_for_status()

            return r

        except Exception as e:
            last = e

            if i < tries - 1:
                time.sleep(2 ** i)

    raise RuntimeError(
        f"GET failed: {url}: {last}"
    )


def rid(row):
    key = "|".join(
        str(row[c])
        for c in COLS
    )

    return hashlib.sha256(
        key.encode()
    ).hexdigest()


def next_business_day(ts):
    x = (
        pd.Timestamp(ts)
        + pd.Timedelta(days=1)
    )

    while x.weekday() >= 5:
        x += pd.Timedelta(days=1)

    return x


def load_vix(s):
    r = get(s, VIX_URL)

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
        subset=["DATE", "CLOSE"]
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
                "unit": "INDEX_LEVEL",
                "frequency": "DAILY",
                "source": "Cboe",
                "source_url": VIX_URL,
                "vintage":
                    d.date().isoformat(),
                "revision_flag": False,
                "point_in_time_safe": True,
                "availability_semantics":
                    "EOD_CLOSE",
            }
        )

    return rows


def load_treasury(s, package=None):
    """
    Load 2Y/10Y Treasury CMTs from the official Fed H.15 DDP package.

    The package is downloaded once because FRED transport can time out in CI.

    H.15 is the authoritative source used here.

    The release is posted Monday-Friday at 4:15pm ET,
    so an EOD observation is information-available on
    its observation date after the daily release.
    """

    if package is None:

        r = get(
            s,
            H15_CMT_URL,
            tries=5,
            timeout=90,
        )

        package = pd.read_csv(
            io.BytesIO(r.content),
            header=5,
        )

    # H.15 DDP Treasury Constant Maturities package:
    # date + 11 maturity columns.

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

    # Package order:
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
                    "indicator": indicator,
                    "observation_date":
                        d.date().isoformat(),
                    "availability_date":
                        d.date().isoformat(),
                    "actual":
                        float(x[value_col]),
                    "unit": "PERCENT",
                    "frequency": "DAILY",
                    "source":
                        "Federal Reserve H.15",
                    "source_url":
                        H15_CMT_URL,
                    "vintage":
                        d.date().isoformat(),
                    "revision_flag": False,
                    "point_in_time_safe": True,
                    "availability_semantics":
                        "OFFICIAL_RELEASE",
                }
            )

    return rows


def _chunk_ranges(
    start,
    end,
    months=6,
):
    """
    Return non-overlapping calendar chunks
    for ALFRED bulk retrieval.
    """

    out = []

    cur = (
        pd.Timestamp(start)
        .normalize()
    )

    finish = (
        pd.Timestamp(end)
        .normalize()
    )

    while cur <= finish:

        nxt = (
            cur
            + pd.DateOffset(months=months)
            - pd.Timedelta(days=1)
        )

        if nxt > finish:
            nxt = finish

        out.append(
            (cur, nxt)
        )

        cur = (
            nxt
            + pd.Timedelta(days=1)
        )

    return out


def _parse_alfred_initial_csv(
    content,
    series,
):
    df = pd.read_csv(
        io.BytesIO(content)
    )

    lower = {
        str(c).lower(): c
        for c in df.columns
    }

    date_col = (
        lower.get("observation_date")
        or lower.get("date")
    )

    value_col = (
        lower.get("value")
        or lower.get(series.lower())
    )

    rt_col = (
        lower.get("realtime_start")
        or lower.get("realtime start")
    )

    if not date_col or not value_col or not rt_col:

        raise RuntimeError(
            f"Unexpected ALFRED {series} columns: "
            f"{list(df.columns)}"
        )

    df[date_col] = pd.to_datetime(
        df[date_col],
        errors="coerce",
    )

    df[rt_col] = pd.to_datetime(
        df[rt_col],
        errors="coerce",
    )

    df[value_col] = pd.to_numeric(
        df[value_col],
        errors="coerce",
    )

    return (
        df.dropna(
            subset=[
                date_col,
                rt_col,
                value_col,
            ]
        ),
        date_col,
        value_col,
        rt_col,
    )


def load_nfci_initial_release(
    s,
    series,
):
    """
    Load ALFRED output_type=4 in small calendar chunks.

    FIXED 6 improves transport reliability only.

    Methodology remains:

    - ALFRED initial-release-only.
    - output_type=4.
    - realtime_start retained.
    - No fallback to revised Chicago Fed/FRED history.
    - PIT safety preserved.
    """

    frames = []

    failures = []

    ranges = _chunk_ranges(
        START,
        END,
        ALFRED_CHUNK_MONTHS,
    )

    print(
        f"{series}: "
        "ALFRED initial-release-only, "
        f"{len(ranges)} chunks"
    )

    for i, (a, b) in enumerate(
        ranges,
        1,
    ):

        url = ALFRED_INITIAL_RELEASE.format(
            series=series,
            start=a.date().isoformat(),
            end=b.date().isoformat(),
        )

        try:

            r = get(
                s,
                url,
                tries=3,
                timeout=ALFRED_TRANSPORT_TIMEOUT,
            )

            (
                df,
                date_col,
                value_col,
                rt_col,
            ) = _parse_alfred_initial_csv(
                r.content,
                series,
            )

            frames.append(df)

            print(
                f"{series}: "
                f"chunk {i}/{len(ranges)} OK "
                f"({a.date()} to {b.date()})"
            )

        except Exception as exc:

            failures.append(
                (
                    i,
                    str(a.date()),
                    str(b.date()),
                    exc,
                )
            )

            print(
                f"{series}: "
                f"chunk {i}/{len(ranges)} FAIL — "
                f"{exc}"
            )

    if failures:

        raise RuntimeError(
            f"{series}: "
            f"{len(failures)}/{len(ranges)} "
            "ALFRED chunks failed; "
            "refusing to substitute revised data. "
            "First failure: "
            + str(failures[0])
        )

    df = pd.concat(
        frames,
        ignore_index=True,
    )

    lower = {
        str(c).lower(): c
        for c in df.columns
    }

    date_col = (
        lower.get("observation_date")
        or lower.get("date")
    )

    value_col = (
        lower.get("value")
        or lower.get(series.lower())
    )

    rt_col = (
        lower.get("realtime_start")
        or lower.get("realtime start")
    )

    df = df[
        (df[date_col] >= START)
        & (df[date_col] <= END)
    ]

    df = df[
        df[rt_col] <= END
    ]

    # Defensive uniqueness.
    #
    # output_type=4 should already provide the
    # first released observation, but overlapping
    # or duplicate source rows are rejected unless
    # they represent the same observation key.

    df = df.sort_values(
        [date_col, rt_col]
    )

    rows = []

    seen = set()

    for _, x in df.iterrows():

        od = pd.Timestamp(
            x[date_col]
        )

        avail = pd.Timestamp(
            x[rt_col]
        )

        if avail < od:
            continue

        key = od.date().isoformat()

        value = float(
            x[value_col]
        )

        tup = (
            key,
            avail.date().isoformat(),
            value,
        )

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "indicator": series,
                "observation_date": key,
                "availability_date":
                    avail.date().isoformat(),
                "actual": value,
                "unit": "INDEX_LEVEL",
                "frequency": "WEEKLY",
                "source": "Chicago Fed",
                "source_url": CHICAGO_URL,
                "vintage":
                    avail.date().isoformat(),
                "revision_flag": False,
                "point_in_time_safe": True,
                "availability_semantics":
                    "ARCHIVED_VINTAGE",
            }
        )

    print(
        f"{series}: "
        f"{len(rows)} PIT initial-release records"
    )

    return rows


def load_nfci_pair(s):
    """
    Load NFCI and ANFCI using two PIT-safe
    initial-release requests.

    Do not fall back to the current Chicago Fed CSV.

    Chicago Fed history is revised as incoming data
    and weights change. Using current revised history
    as if it were known then would violate the project's
    PIT requirement.
    """

    rows = []

    failures = []

    with ThreadPoolExecutor(
        max_workers=2
    ) as ex:

        futs = {
            ex.submit(
                load_nfci_initial_release,
                session(),
                series,
            ): series
            for series in (
                "NFCI",
                "ANFCI",
            )
        }

        for fut in as_completed(futs):

            series = futs[fut]

            try:

                rows.extend(
                    fut.result()
                )

            except Exception as exc:

                failures.append(
                    (
                        series,
                        exc,
                    )
                )

                print(
                    f"{series}: FAIL — "
                    f"{exc}"
                )

    if failures:

        raise RuntimeError(
            "NFCI/ANFCI initial-release "
            "retrieval failed: "
            + "; ".join(
                f"{s}: {e}"
                for s, e in failures
            )
        )

    # Enforce logical PIT key defensively.

    out = {}

    for row in rows:

        key = (
            row["indicator"],
            row["observation_date"],
        )

        if (
            key not in out
            or row["availability_date"]
            < out[key]["availability_date"]
        ):

            out[key] = row

    result = list(
        out.values()
    )

    print(
        f"NFCI/ANFCI collected: "
        f"{len(result)} records"
    )

    return result


def main():

    s = session()

    rows = []

    # VIX
    rows += load_vix(s)

    # Treasury 2Y / 10Y
    treasury_package = None

    rows += load_treasury(
        s,
        treasury_package,
    )

    # NFCI / ANFCI
    rows += load_nfci_pair(s)

    # Build curve only where both
    # Treasury observations share the same date.

    tmp = pd.DataFrame(rows)

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

    common = t2.index.intersection(
        t10.index
    )

    for d in common:

        a = (
            float(
                t10.loc[d, "actual"]
            )
            -
            float(
                t2.loc[d, "actual"]
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

                "actual": a,

                "unit":
                    "PERCENTAGE_POINTS",

                "frequency": "DAILY",

                "source":
                    "Federal Reserve H.15",

                "source_url":
                    H15_URL,

                "vintage":
                    pd.Timestamp(
                        avail
                    ).date().isoformat(),

                "revision_flag": False,

                "point_in_time_safe":
                    True,

                "availability_semantics":
                    "OFFICIAL_RELEASE",
            }
        )

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

    # --------------------------------------------------
    # Conservative Point-in-Time Quality Gate
    # --------------------------------------------------

    od = pd.to_datetime(
        out["observation_date"]
    )

    ad = pd.to_datetime(
        out["availability_date"]
    )

    if (ad < od).any():

        raise AssertionError(
            "availability_date earlier "
            "than observation_date"
        )

    if not out[
        "point_in_time_safe"
    ].all():

        raise AssertionError(
            "Non-PIT-safe record found"
        )

    # --------------------------------------------------
    # Record IDs
    # --------------------------------------------------

    out["record_id"] = out.apply(
        rid,
        axis=1,
    )

    # --------------------------------------------------
    # Output
    # --------------------------------------------------

    out.to_csv(
        OUT,
        index=False,
    )

    print(
        "Financial Stress Historical "
        "Collector v1 — FIXED 6"
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
        out.groupby(
            "indicator"
        ).size().to_string()
    )

    print(
        "PIT QUALITY GATE: PASS"
    )


if __name__ == "__main__":
    main()
