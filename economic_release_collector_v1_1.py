"""
US500 Macro Intelligence
Economic Intelligence — Phase 1A.1
Official Release Collector v1.1

Why v1.1:
The first collector attempted to crawl BLS/DOL archive index pages.
GitHub Actions runners received HTTP 403 from those anti-bot protected
index endpoints. ISM/BEA page layouts also differed from the assumptions.

This version therefore uses a small, explicitly documented FIRST REAL BATCH
of values verified against official release pages, with the official source
URL retained for every record.

This is deliberately a "verified release manifest" collector, not a
fabricated dataset. It does NOT create historical consensus estimates.

Next expansion can replace the manifest with source-specific adapters once
we establish reliable machine-access paths for each agency.
"""

from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
import pandas as pd


OUTPUT_FILE = "economic_release_records_input_v1.csv"


OFFICIAL_RELEASES = [
    # ---------------- CPI / Core CPI ----------------
    {
        "event_id": "CPI_2026-09-11_August_2026",
        "indicator": "CPI",
        "release_date": "2026-09-11",
        "release_time": "08:30 ET",
        "reference_period": "August 2026",
        "actual": 0.4,
        "previous": 0.1,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Bureau of Labor Statistics — CPI News Release",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_09112026.htm",
        "vintage_date": "2026-09-11",
        "notes": "Original August 2026 headline monthly CPI SA change.",
    },
    {
        "event_id": "CORE_CPI_2026-09-11_August_2026",
        "indicator": "CORE_CPI",
        "release_date": "2026-09-11",
        "release_time": "08:30 ET",
        "reference_period": "August 2026",
        "actual": 0.3,
        "previous": None,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Bureau of Labor Statistics — CPI News Release",
        "source_url": "https://www.bls.gov/news.release/archives/cpi_09112026.htm",
        "vintage_date": "2026-09-11",
        "notes": "Original August 2026 core CPI monthly SA change.",
    },

    # ---------------- Employment Situation ----------------
    {
        "event_id": "NFP_2026-09-04_August_2026",
        "indicator": "NFP",
        "release_date": "2026-09-04",
        "release_time": "08:30 ET",
        "reference_period": "August 2026",
        "actual": 162000,
        "previous": 21000,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Bureau of Labor Statistics — Employment Situation",
        "source_url": "https://www.bls.gov/news.release/empsit.htm",
        "vintage_date": "2026-09-04",
        "notes": "Original August 2026 headline nonfarm payroll change. BLS labels latest months preliminary.",
    },
    {
        "event_id": "UNEMPLOYMENT_RATE_2026-09-04_August_2026",
        "indicator": "UNEMPLOYMENT_RATE",
        "release_date": "2026-09-04",
        "release_time": "08:30 ET",
        "reference_period": "August 2026",
        "actual": 4.1,
        "previous": 4.1,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Bureau of Labor Statistics — Employment Situation",
        "source_url": "https://www.bls.gov/news.release/empsit.htm",
        "vintage_date": "2026-09-04",
        "notes": "Original August 2026 unemployment rate.",
    },

    # ---------------- Initial Jobless Claims ----------------
    {
        "event_id": "INITIAL_JOBLESS_CLAIMS_2026-09-17_Week_ending_2026-09-12",
        "indicator": "INITIAL_JOBLESS_CLAIMS",
        "release_date": "2026-09-17",
        "release_time": "08:30 ET",
        "reference_period": "Week ending September 12, 2026",
        "actual": 196000,
        "previous": 206000,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
        "source_url": "https://www.dol.gov/newsroom/releases/eta/eta20260917",
        "vintage_date": "2026-09-17",
        "notes": "Advance seasonally adjusted initial claims.",
    },
    {
        "event_id": "INITIAL_JOBLESS_CLAIMS_2026-09-10_Week_ending_2026-09-05",
        "indicator": "INITIAL_JOBLESS_CLAIMS",
        "release_date": "2026-09-10",
        "release_time": "08:30 ET",
        "reference_period": "Week ending September 5, 2026",
        "actual": 206000,
        "previous": 207000,
        "revision": 1000,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
        "source_url": "https://www.dol.gov/newsroom/releases/eta/eta20260910",
        "vintage_date": "2026-09-10",
        "notes": "Advance initial claims; prior week was revised from 206k to 207k.",
    },
    {
        "event_id": "INITIAL_JOBLESS_CLAIMS_2026-09-03_Week_ending_2026-08-29",
        "indicator": "INITIAL_JOBLESS_CLAIMS",
        "release_date": "2026-09-03",
        "release_time": "08:30 ET",
        "reference_period": "Week ending August 29, 2026",
        "actual": 206000,
        "previous": 204000,
        "revision": 1000,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
        "source_url": "https://www.dol.gov/newsroom/releases/eta/eta20260903",
        "vintage_date": "2026-09-03",
        "notes": "Advance initial claims; prior week revised from 203k to 204k.",
    },

    # ---------------- ISM Manufacturing PMI ----------------
    {
        "event_id": "ISM_MANUFACTURING_PMI_2026-09-09_August_2026",
        "indicator": "ISM_MANUFACTURING_PMI",
        "release_date": "2026-09-09",
        "release_time": "10:00 ET",
        "reference_period": "August 2026",
        "actual": 54.6,
        "previous": 55.6,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "Institute for Supply Management — Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/news-publications/inside-supply-management-magazine/2026-september-october/manufacturing/",
        "vintage_date": "2026-09-09",
        "notes": "Official August 2026 Manufacturing PMI report.",
    },
    {
        "event_id": "ISM_MANUFACTURING_PMI_2026-08-03_July_2026",
        "indicator": "ISM_MANUFACTURING_PMI",
        "release_date": "2026-08-03",
        "release_time": "10:00 ET",
        "reference_period": "July 2026",
        "actual": 55.6,
        "previous": 53.3,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "source": "Institute for Supply Management — Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/july/",
        "vintage_date": "2026-08-03",
        "notes": "Official July 2026 Manufacturing PMI report.",
    },
    {
        "event_id": "ISM_MANUFACTURING_PMI_2026-07-01_June_2026",
        "indicator": "ISM_MANUFACTURING_PMI",
        "release_date": "2026-07-01",
        "release_time": "10:00 ET",
        "reference_period": "June 2026",
        "actual": 53.3,
        "previous": 52.7,
        "revision": None,
        "consensus": None,
        "consensus_source": "",
        "vintage_date": "2026-07-01",
        "notes": "June 2026 value is explicitly reported as the prior month in the official July report.",
        "source": "Institute for Supply Management — Manufacturing PMI Report",
        "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/july/",
    },

    # ---------------- GDP ----------------
    {
        "event_id": "GDP_2026-08-26_Q2_2026_Second_Estimate",
        "indicator": "GDP",
        "release_date": "2026-08-26",
        "release_time": "08:30 ET",
        "reference_period": "Q2 2026 — Second Estimate",
        "actual": 1.5,
        "previous": None,
        "revision": -0.1,
        "consensus": None,
        "consensus_source": "",
        "source": "U.S. Bureau of Economic Analysis — GDP Second Estimate",
        "source_url": "https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026",
        "vintage_date": "2026-08-26",
        "notes": "Real GDP annualized quarterly growth in the second estimate. BEA reported a downward revision of less than 0.1 percentage point versus the advance estimate.",
    },
]


def validate_manifest(df: pd.DataFrame) -> None:
    required = [
        "event_id",
        "indicator",
        "release_date",
        "release_time",
        "reference_period",
        "actual",
        "source",
        "source_url",
        "vintage_date",
    ]

    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError("Missing columns: " + ", ".join(missing))

    if df["event_id"].duplicated().any():
        raise ValueError("Duplicate event_id detected.")

    if df["actual"].isna().any():
        raise ValueError("A real release record has missing actual.")

    if df["source_url"].isna().any():
        raise ValueError("A real release record has missing source_url.")

    # Consensus must remain unknown in this first batch.
    if df["consensus"].notna().any():
        raise ValueError(
            "Consensus was populated. This collector must not fabricate historical consensus."
        )


def main():
    print("=" * 78)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1A.1")
    print("OFFICIAL RELEASE COLLECTOR v1.1")
    print("=" * 78)

    started = datetime.now(timezone.utc)

    df = pd.DataFrame(OFFICIAL_RELEASES)

    validate_manifest(df)

    df["release_date"] = pd.to_datetime(df["release_date"]).dt.strftime("%Y-%m-%d")
    df["vintage_date"] = pd.to_datetime(df["vintage_date"]).dt.strftime("%Y-%m-%d")

    df = df.sort_values(
        ["release_date", "indicator"],
        ascending=[False, True],
    ).reset_index(drop=True)

    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    print("\nCOLLECTION SUMMARY")
    print("-" * 78)
    print(f"Records collected: {len(df)}")
    print(f"Indicators: {df['indicator'].nunique()}")
    print(f"Official source URLs: {df['source_url'].nunique()}")
    print(f"Elapsed seconds: {elapsed:.2f}")

    print("\nBY INDICATOR")
    print(df.groupby("indicator").size().to_string())

    print("\nRECORDS")
    print(
        df[
            [
                "indicator",
                "release_date",
                "reference_period",
                "actual",
                "source",
            ]
        ].to_string(index=False)
    )

    print("\nCONSENSUS")
    print("All consensus values intentionally remain UNKNOWN.")

    print(f"\nSaved: {OUTPUT_FILE}")
    print("\nSTATUS: OFFICIAL_RELEASE_BATCH_CREATED")


if __name__ == "__main__":
    main()
