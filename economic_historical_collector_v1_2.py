"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B.1
Historical Collector v1.1 — OFFICIAL MANIFEST MODE

IMPORTANT:
This version does NOT scrape BLS archive index pages.
GitHub Actions runners can receive HTTP 403 from BLS, even though the
official archive and individual releases are publicly accessible.

Therefore the collector is manifest-driven:
- official release URL
- release date/time
- reference period
- actual value(s)
- vintage date
- source

Only records explicitly present in the verified manifest are exported.
No value is calculated from a current/revised API and no consensus is
invented.

Batch 1.1 = verified BLS releases used to validate the historical pipeline.
After this passes, expand the manifest in controlled batches.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional
import pandas as pd


OUTPUT_EVENTS = "economic_historical_events_v1.csv"
OUTPUT_QUALITY = "economic_historical_quality_v1.csv"


@dataclass(frozen=True)
class Record:
    indicator: str
    agency: str
    release_date: str
    release_time: str
    reference_period: str
    actual: float
    previous: Optional[float]
    revision: Optional[float]
    consensus: Optional[float]
    consensus_source: Optional[str]
    vintage_date: str
    source: str
    source_url: str


# ---------------------------------------------------------------------
# VERIFIED OFFICIAL RELEASE MANIFEST
# ---------------------------------------------------------------------
# Values below are copied from the official BLS release pages.
# They are intentionally small in this first manifest batch so that
# every record can be audited before the manifest is expanded.
#
# Official archive pages warn that archived data can later be revised.
# vintage_date therefore equals the information-release date.
#
# Sources:
# CPI:
#   https://www.bls.gov/news.release/archives/cpi_08102022.htm
#   https://www.bls.gov/news.release/archives/cpi_10132022.htm
#   https://www.bls.gov/news.release/archives/cpi_11102022.htm
#   https://www.bls.gov/news.release/archives/cpi_01122023.htm
#
# Employment:
#   https://www.bls.gov/news.release/archives/empsit_08052022.htm
#   https://www.bls.gov/news.release/archives/empsit_09022022.htm
#   https://www.bls.gov/news.release/archives/empsit_11042022.htm
#
# We do not populate consensus because these official releases do not
# provide the market consensus that existed immediately before release.
# ---------------------------------------------------------------------

OFFICIAL_MANIFEST = [
    # CPI — July 2022, released Aug 10, 2022
    Record(
        "CPI", "BLS", "2022-08-10", "08:30 ET", "July 2022",
        0.0, 1.3, None, None, None, "2022-08-10",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_08102022.htm",
    ),
    # Core CPI July 2022: 0.3% monthly increase (official release table/text).
    Record(
        "CORE_CPI", "BLS", "2022-08-10", "08:30 ET", "July 2022",
        0.3, None, None, None, None, "2022-08-10",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_08102022.htm",
    ),

    # CPI — September 2022, released Oct 13, 2022
    Record(
        "CPI", "BLS", "2022-10-13", "08:30 ET", "September 2022",
        0.4, 0.1, None, None, None, "2022-10-13",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_10132022.htm",
    ),
    Record(
        "CORE_CPI", "BLS", "2022-10-13", "08:30 ET", "September 2022",
        0.6, None, None, None, None, "2022-10-13",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_10132022.htm",
    ),

    # CPI — October 2022, released Nov 10, 2022
    Record(
        "CPI", "BLS", "2022-11-10", "08:30 ET", "October 2022",
        0.4, 0.4, None, None, None, "2022-11-10",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_11102022.htm",
    ),
    Record(
        "CORE_CPI", "BLS", "2022-11-10", "08:30 ET", "October 2022",
        0.3, None, None, None, None, "2022-11-10",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_11102022.htm",
    ),

    # CPI — December 2022, released Jan 12, 2023
    Record(
        "CPI", "BLS", "2023-01-12", "08:30 ET", "December 2022",
        -0.1, 0.1, None, None, None, "2023-01-12",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_01122023.htm",
    ),
    Record(
        "CORE_CPI", "BLS", "2023-01-12", "08:30 ET", "December 2022",
        0.3, None, None, None, None, "2023-01-12",
        "U.S. Bureau of Labor Statistics — CPI News Release",
        "https://www.bls.gov/news.release/archives/cpi_01122023.htm",
    ),

    # Employment Situation — July 2022, released Aug 5, 2022
    Record(
        "NFP", "BLS", "2022-08-05", "08:30 ET", "July 2022",
        528000, None, None, None, None, "2022-08-05",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_08052022.htm",
    ),
    Record(
        "UNEMPLOYMENT_RATE", "BLS", "2022-08-05", "08:30 ET", "July 2022",
        3.5, None, None, None, None, "2022-08-05",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_08052022.htm",
    ),

    # Employment Situation — August 2022, released Sep 2, 2022
    Record(
        "NFP", "BLS", "2022-09-02", "08:30 ET", "August 2022",
        315000, None, None, None, None, "2022-09-02",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_09022022.htm",
    ),
    Record(
        "UNEMPLOYMENT_RATE", "BLS", "2022-09-02", "08:30 ET", "August 2022",
        3.7, None, None, None, None, "2022-09-02",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_09022022.htm",
    ),

    # Employment Situation — October 2022, released Nov 4, 2022
    Record(
        "NFP", "BLS", "2022-11-04", "08:30 ET", "October 2022",
        261000, None, None, None, None, "2022-11-04",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_11042022.htm",
    ),
    Record(
        "UNEMPLOYMENT_RATE", "BLS", "2022-11-04", "08:30 ET", "October 2022",
        3.7, None, None, None, None, "2022-11-04",
        "U.S. Bureau of Labor Statistics — Employment Situation",
        "https://www.bls.gov/news.release/archives/empsit_11042022.htm",
    ),
]


def validate(df: pd.DataFrame) -> pd.DataFrame:
    out = []

    for _, r in df.iterrows():
        issues = []

        required = [
            "indicator", "agency", "release_date", "release_time",
            "reference_period", "actual", "vintage_date",
            "source", "source_url",
        ]
        for col in required:
            if pd.isna(r[col]) or str(r[col]).strip() == "":
                issues.append(f"missing_{col}")

        try:
            release = pd.Timestamp(r["release_date"])
            vintage = pd.Timestamp(r["vintage_date"])
            if vintage > release:
                issues.append("vintage_after_release")
        except Exception:
            issues.append("invalid_release_or_vintage_date")

        out.append({
            "indicator": r["indicator"],
            "agency": r["agency"],
            "release_date": r["release_date"],
            "reference_period": r["reference_period"],
            "point_in_time_safe": len(issues) == 0,
            "quality_issues": ";".join(issues),
            "historical_consensus_available": (
                pd.notna(r["consensus"])
                and pd.notna(r["consensus_source"])
                and str(r["consensus_source"]).strip() != ""
            ),
        })

    return pd.DataFrame(out)


def main() -> None:
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1B.1")
    print("HISTORICAL COLLECTOR v1.1 — OFFICIAL MANIFEST MODE")
    print("=" * 72)

    df = pd.DataFrame([asdict(r) for r in OFFICIAL_MANIFEST])

    if df.empty:
        raise RuntimeError("Official manifest is empty. No data will be fabricated.")

    df = df.drop_duplicates(
        subset=["indicator", "release_date", "reference_period", "source_url"]
    ).sort_values(["release_date", "indicator"]).reset_index(drop=True)

    quality = validate(df)

    df.to_csv(OUTPUT_EVENTS, index=False)
    quality.to_csv(OUTPUT_QUALITY, index=False)

    pit = int(quality["point_in_time_safe"].sum())
    total = len(quality)
    consensus = int(quality["historical_consensus_available"].sum())

    print("\nSUMMARY")
    print("-" * 72)
    print(f"Records collected:          {total}")
    print(f"PIT safe:                    {pit}/{total}")
    print(f"Historical consensus:        {consensus}/{total}")
    print(f"Indicators:                  {df['indicator'].nunique()}")

    print("\nBY INDICATOR")
    print(df["indicator"].value_counts().sort_index().to_string())

    print("\nRECORDS")
    print(
        df[
            ["indicator", "release_date", "reference_period", "actual", "source_url"]
        ].to_string(index=False)
    )

    if pit != total:
        print("\nPIT QUALITY GATE: FAIL")
        print(quality.loc[~quality["point_in_time_safe"]].to_string(index=False))
        raise RuntimeError("Historical data quality gate failed.")

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_QUALITY}")
    print("\nPIT QUALITY GATE: PASS")
    print("Research-only. No Decision Engine integration.")


if __name__ == "__main__":
    main()
