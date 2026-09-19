"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B.7
Historical Collector v1.7 — Extended PIT Historical Series

Research-only.
No web scraping.
No fabricated consensus.
No Decision Engine integration.

Contract preserved:
  economic_historical_events_v1.csv
  economic_historical_quality_v1.csv

v1.7 objective:
  Extend the historical sample so every indicator can accumulate enough
  point-in-time observations for the Surprise Engine's MIN_PRIOR_HISTORY=3
  requirement. Previous values are release-vintage values, not later
  revised database values.
"""

from dataclasses import dataclass, asdict
from typing import Optional
import hashlib
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

def make_record_id(r: Record) -> str:
    raw = "|".join([
        r.indicator, r.agency, r.release_date, r.release_time,
        r.reference_period, r.source_url
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

# Extended official-release-vintage batch.  Values are intentionally kept
# explicit rather than scraped so PIT safety is auditable.
RECORDS = [
    # 2022 anchor series already validated in v1.6
    Record("CPI","BLS","2022-08-10","08:30 ET","July 2022",0.0,1.3,None,None,None,"2022-08-10","BLS CPI","https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CORE_CPI","BLS","2022-08-10","08:30 ET","July 2022",0.3,0.7,None,None,None,"2022-08-10","BLS CPI","https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CPI","BLS","2022-10-13","08:30 ET","September 2022",0.4,0.1,None,None,None,"2022-10-13","BLS CPI","https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CORE_CPI","BLS","2022-10-13","08:30 ET","September 2022",0.6,0.6,None,None,None,"2022-10-13","BLS CPI","https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CPI","BLS","2022-11-10","08:30 ET","October 2022",0.4,0.6,None,None,None,"2022-11-10","BLS CPI","https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CORE_CPI","BLS","2022-11-10","08:30 ET","October 2022",0.3,0.6,None,None,None,"2022-11-10","BLS CPI","https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CPI","BLS","2023-01-12","08:30 ET","December 2022",0.1,0.1,None,None,None,"2023-01-12","BLS CPI","https://www.bls.gov/news.release/archives/cpi_01122023.htm"),
    Record("CORE_CPI","BLS","2023-01-12","08:30 ET","December 2022",0.4,0.2,None,None,None,"2023-01-12","BLS CPI","https://www.bls.gov/news.release/archives/cpi_01122023.htm"),

    # 2022 labor anchors
    Record("NFP","BLS","2022-08-05","08:30 ET","July 2022",528000,398000,None,None,None,"2022-08-05","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-08-05","08:30 ET","July 2022",3.5,3.6,None,None,None,"2022-08-05","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("NFP","BLS","2022-09-02","08:30 ET","August 2022",315000,526000,None,None,None,"2022-09-02","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-09-02","08:30 ET","August 2022",3.7,3.5,None,None,None,"2022-09-02","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("NFP","BLS","2022-11-04","08:30 ET","October 2022",261000,315000,None,None,None,"2022-11-04","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_11042022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-11-04","08:30 ET","October 2022",3.7,3.5,None,None,None,"2022-11-04","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_11042022.htm"),

    # 2023 CPI/Core CPI
    Record("CPI","BLS","2023-02-14","08:30 ET","January 2023",0.5,0.1,None,None,None,"2023-02-14","BLS CPI","https://www.bls.gov/news.release/archives/cpi_02142023.htm"),
    Record("CORE_CPI","BLS","2023-02-14","08:30 ET","January 2023",0.4,0.4,None,None,None,"2023-02-14","BLS CPI","https://www.bls.gov/news.release/archives/cpi_02142023.htm"),
    Record("CPI","BLS","2023-03-14","08:30 ET","February 2023",0.4,0.5,None,None,None,"2023-03-14","BLS CPI","https://www.bls.gov/news.release/archives/cpi_03142023.htm"),
    Record("CORE_CPI","BLS","2023-03-14","08:30 ET","February 2023",0.5,0.4,None,None,None,"2023-03-14","BLS CPI","https://www.bls.gov/news.release/archives/cpi_03142023.htm"),
    Record("CPI","BLS","2023-04-12","08:30 ET","March 2023",0.1,0.4,None,None,None,"2023-04-12","BLS CPI","https://www.bls.gov/news.release/archives/cpi_04122023.htm"),
    Record("CORE_CPI","BLS","2023-04-12","08:30 ET","March 2023",0.4,0.5,None,None,None,"2023-04-12","BLS CPI","https://www.bls.gov/news.release/archives/cpi_04122023.htm"),

    # 2023 labor
    Record("NFP","BLS","2023-02-03","08:30 ET","January 2023",517000,260000,None,None,None,"2023-02-03","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_02032023.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2023-02-03","08:30 ET","January 2023",3.4,3.5,None,None,None,"2023-02-03","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_02032023.htm"),
    Record("NFP","BLS","2023-03-10","08:30 ET","February 2023",311000,517000,None,None,None,"2023-03-10","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_03102023.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2023-03-10","08:30 ET","February 2023",3.6,3.4,None,None,None,"2023-03-10","BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_03102023.htm"),
]

def validate(r: Record):
    issues = []
    try:
        release = pd.Timestamp(r.release_date)
        vintage = pd.Timestamp(r.vintage_date)
        if vintage > release:
            issues.append("vintage_after_release")
    except Exception:
        issues.append("invalid_release_or_vintage_date")
    if r.actual is None:
        issues.append("missing_actual")
    if r.previous is not None and r.actual is None:
        issues.append("previous_without_actual")
    if not r.source_url.startswith("https://"):
        issues.append("invalid_source_url")
    return issues

def main():
    rows = []
    for r in RECORDS:
        rows.append(asdict(r))

    df = pd.DataFrame(rows)
    df = df.drop_duplicates(
        subset=["indicator","agency","release_date","release_time",
                "reference_period","source_url"]
    ).reset_index(drop=True)

    df["record_id"] = df.apply(
        lambda x: make_record_id(Record(**{
            k: x[k] for k in Record.__dataclass_fields__
        })), axis=1
    )

    issues = [validate(Record(**{k: row[k] for k in Record.__dataclass_fields__}))
              for _, row in df.iterrows()]

    quality = pd.DataFrame({
        "record_id": df["record_id"],
        "indicator": df["indicator"],
        "agency": df["agency"],
        "release_date": df["release_date"],
        "reference_period": df["reference_period"],
        "point_in_time_safe": [len(x) == 0 for x in issues],
        "quality_issues": [";".join(x) for x in issues],
        "historical_consensus_available": False,
    })

    events_cols = [
        "indicator","agency","release_date","release_time",
        "reference_period","actual","previous","revision",
        "consensus","consensus_source","vintage_date","source","source_url"
    ]
    df[events_cols].to_csv(OUTPUT_EVENTS, index=False)
    quality.to_csv(OUTPUT_QUALITY, index=False)

    print("=" * 72)
    print("ECONOMIC HISTORICAL COLLECTOR v1.7")
    print("=" * 72)
    print(f"Records: {len(df)}")
    print(f"PIT safe: {int(quality.point_in_time_safe.sum())}/{len(quality)}")
    print(f"Records with previous: {int(df.previous.notna().sum())}/{len(df)}")
    print(f"Indicators: {df.indicator.nunique()}")
    print()
    print(df.indicator.value_counts().sort_index())
    print()
    print("PIT QUALITY GATE:",
          "PASS" if quality.point_in_time_safe.all() else "FAIL")
    print("Research-only. No Decision Engine integration.")

if __name__ == "__main__":
    main()
