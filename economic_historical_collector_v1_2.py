"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B.2
Historical Collector v1.2 — OFFICIAL MANIFEST MODE

Adds verified U.S. Department of Labor Initial Jobless Claims records
to the validated BLS historical manifest.

No scraping is performed. No consensus is fabricated.
All values are release-time observations from official DOL releases.
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
# VERIFIED OFFICIAL MANIFEST
# BLS records are retained from v1.1.
# DOL claims records below are verified against official DOL releases.
# Consensus remains UNKNOWN by design.
# ---------------------------------------------------------------------

OFFICIAL_MANIFEST = [
    # ------------------------- BLS CPI -------------------------
    Record("CPI","BLS","2022-08-10","08:30 ET","July 2022",0.0,1.3,None,None,None,"2022-08-10",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CORE_CPI","BLS","2022-08-10","08:30 ET","July 2022",0.3,None,None,None,None,"2022-08-10",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CPI","BLS","2022-10-13","08:30 ET","September 2022",0.4,0.1,None,None,None,"2022-10-13",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CORE_CPI","BLS","2022-10-13","08:30 ET","September 2022",0.6,None,None,None,None,"2022-10-13",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CPI","BLS","2022-11-10","08:30 ET","October 2022",0.4,0.4,None,None,None,"2022-11-10",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CORE_CPI","BLS","2022-11-10","08:30 ET","October 2022",0.3,None,None,None,None,"2022-11-10",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CPI","BLS","2023-01-12","08:30 ET","December 2022",-0.1,0.1,None,None,None,"2023-01-12",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_01122023.htm"),
    Record("CORE_CPI","BLS","2023-01-12","08:30 ET","December 2022",0.3,None,None,None,None,"2023-01-12",
           "U.S. Bureau of Labor Statistics — CPI News Release",
           "https://www.bls.gov/news.release/archives/cpi_01122023.htm"),

    # ---------------------- BLS EMPLOYMENT ---------------------
    Record("NFP","BLS","2022-08-05","08:30 ET","July 2022",528000,None,None,None,None,"2022-08-05",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-08-05","08:30 ET","July 2022",3.5,None,None,None,None,"2022-08-05",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("NFP","BLS","2022-09-02","08:30 ET","August 2022",315000,None,None,None,None,"2022-09-02",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-09-02","08:30 ET","August 2022",3.7,None,None,None,None,"2022-09-02",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("NFP","BLS","2022-11-04","08:30 ET","October 2022",261000,None,None,None,None,"2022-11-04",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_11042022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-11-04","08:30 ET","October 2022",3.7,None,None,None,None,"2022-11-04",
           "U.S. Bureau of Labor Statistics — Employment Situation",
           "https://www.bls.gov/news.release/archives/empsit_11042022.htm"),

    # -------------------- DOL INITIAL CLAIMS -------------------
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-07","08:30 ET",
           "Week ending July 2, 2022",235000,231000,None,None,None,"2022-07-07",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220707"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-14","08:30 ET",
           "Week ending July 9, 2022",244000,235000,None,None,None,"2022-07-14",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220714"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-21","08:30 ET",
           "Week ending July 16, 2022",251000,244000,None,None,None,"2022-07-21",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220721"),

    # Important revision: July 28 release says previous week was revised
    # from 251k to 261k. Preserve both the release's actual and revision.
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-28","08:30 ET",
           "Week ending July 23, 2022",256000,261000,10000,None,None,"2022-07-28",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220728"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-11","08:30 ET",
           "Week ending August 6, 2022",262000,248000,12000,None,None,"2022-08-11",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220811"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-18","08:30 ET",
           "Week ending August 13, 2022",250000,252000,10000,None,None,"2022-08-18",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220818"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-25","08:30 ET",
           "Week ending August 20, 2022",243000,245000,5000,None,None,"2022-08-25",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220825"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-01","08:30 ET",
           "Week ending August 27, 2022",232000,237000,6000,None,None,"2022-09-01",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220901"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-08","08:30 ET",
           "Week ending September 3, 2022",222000,228000,4000,None,None,"2022-09-08",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220908"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-15","08:30 ET",
           "Week ending September 10, 2022",213000,218000,4000,None,None,"2022-09-15",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220915"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-22","08:30 ET",
           "Week ending September 17, 2022",213000,208000,5000,None,None,"2022-09-22",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220922"),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-29","08:30 ET",
           "Week ending September 24, 2022",193000,209000,4000,None,None,"2022-09-29",
           "U.S. Department of Labor — Unemployment Insurance Weekly Claims Report",
           "https://www.dol.gov/newsroom/releases/eta/eta20220929"),
]


def validate(df):
    rows = []
    for _, r in df.iterrows():
        issues = []
        for col in [
            "indicator","agency","release_date","release_time",
            "reference_period","actual","vintage_date","source","source_url"
        ]:
            if pd.isna(r[col]) or str(r[col]).strip() == "":
                issues.append(f"missing_{col}")

        try:
            release = pd.Timestamp(r["release_date"])
            vintage = pd.Timestamp(r["vintage_date"])
            if vintage > release:
                issues.append("vintage_after_release")
        except Exception:
            issues.append("invalid_release_or_vintage_date")

        rows.append({
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
    return pd.DataFrame(rows)


def main():
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1B.2")
    print("HISTORICAL COLLECTOR v1.2 — BLS + DOL OFFICIAL MANIFEST")
    print("=" * 72)

    df = pd.DataFrame([asdict(r) for r in OFFICIAL_MANIFEST])

    if df.empty:
        raise RuntimeError("Official manifest is empty. No data will be fabricated.")

    df = df.drop_duplicates(
        subset=["indicator","release_date","reference_period","source_url"]
    ).sort_values(["release_date","indicator"]).reset_index(drop=True)

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

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_QUALITY}")

    if pit != total:
        print("\nPIT QUALITY GATE: FAIL")
        print(quality.loc[~quality["point_in_time_safe"]].to_string(index=False))
        raise RuntimeError("Historical data quality gate failed.")

    print("\nPIT QUALITY GATE: PASS")
    print("Research-only. No Decision Engine integration.")


if __name__ == "__main__":
    main()
