"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B.6
Historical Collector v1.6 — PIT Integrity + Previous-Vintage Repair + 2023 Batch

Adds a conservative BEA GDP release manifest while preserving
release vintages (Advance / Second / Third estimates).

Research-only. No Decision Engine integration.
No consensus is fabricated.
No web scraping is performed.
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


# Existing 32 validated records from v1.3.
# Kept here explicitly so this collector is standalone and reproducible.
BASE_RECORDS = [
    # CPI / Core CPI
    Record("CPI","BLS","2022-08-10","08:30 ET","July 2022",0.0,1.3,None,None,None,"2022-08-10",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CORE_CPI","BLS","2022-08-10","08:30 ET","July 2022",0.3,0.7,None,None,None,"2022-08-10",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_08102022.htm"),
    Record("CPI","BLS","2022-10-13","08:30 ET","September 2022",0.4,0.1,None,None,None,"2022-10-13",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CORE_CPI","BLS","2022-10-13","08:30 ET","September 2022",0.6,0.6,None,None,None,"2022-10-13",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_10132022.htm"),
    Record("CPI","BLS","2022-11-10","08:30 ET","October 2022",0.4,0.4,None,None,None,"2022-11-10",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CORE_CPI","BLS","2022-11-10","08:30 ET","October 2022",0.3,0.6,None,None,None,"2022-11-10",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_11102022.htm"),
    Record("CPI","BLS","2023-01-12","08:30 ET","December 2022",-0.1,0.1,None,None,None,"2023-01-12",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_01122023.htm"),
    Record("CORE_CPI","BLS","2023-01-12","08:30 ET","December 2022",0.3,0.2,None,None,None,"2023-01-12",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_01122023.htm"),

    # NFP / Unemployment
    Record("NFP","BLS","2022-08-05","08:30 ET","July 2022",528000,398000,None,None,None,"2022-08-05",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-08-05","08:30 ET","July 2022",3.5,3.6,None,None,None,"2022-08-05",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_08052022.htm"),
    Record("NFP","BLS","2022-09-02","08:30 ET","August 2022",315000,526000,None,None,None,"2022-09-02",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-09-02","08:30 ET","August 2022",3.7,3.5,None,None,None,"2022-09-02",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_09022022.htm"),
    Record("NFP","BLS","2022-11-04","08:30 ET","October 2022",261000,315000,None,None,None,"2022-11-04",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_11042022.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2022-11-04","08:30 ET","October 2022",3.7,3.5,None,None,None,"2022-11-04",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_11042022.htm"),

    # DOL Initial Claims
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-07","08:30 ET","Week ending July 2, 2022",235000,231000,None,None,None,"2022-07-07",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220707"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-14","08:30 ET","Week ending July 9, 2022",244000,235000,None,None,None,"2022-07-14",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220714"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-21","08:30 ET","Week ending July 16, 2022",251000,244000,None,None,None,"2022-07-21",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220721"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-28","08:30 ET","Week ending July 23, 2022",256000,261000,10000,None,None,"2022-07-28",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220728"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-11","08:30 ET","Week ending August 6, 2022",262000,248000,12000,None,None,"2022-08-11",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220811"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-18","08:30 ET","Week ending August 13, 2022",250000,252000,10000,None,None,"2022-08-18",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220818"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-25","08:30 ET","Week ending August 20, 2022",243000,245000,5000,None,None,"2022-08-25",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220825"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-01","08:30 ET","Week ending August 27, 2022",232000,237000,6000,None,None,"2022-09-01",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220901"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-08","08:30 ET","Week ending September 3, 2022",222000,228000,4000,None,None,"2022-09-08",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220908"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-15","08:30 ET","Week ending September 10, 2022",213000,218000,4000,None,None,"2022-09-15",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220915"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-22","08:30 ET","Week ending September 17, 2022",213000,208000,5000,None,None,"2022-09-22",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220922"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-29","08:30 ET","Week ending September 24, 2022",193000,209000,4000,None,None,"2022-09-29",
           "DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220929"),

    # ISM Manufacturing PMI
    Record("ISM_MANUFACTURING_PMI","ISM","2022-08-01","10:00 ET","July 2022",52.8,53.0,None,None,None,"2022-08-01",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/august/"),
    Record("ISM_MANUFACTURING_PMI","ISM","2022-09-01","10:00 ET","August 2022",52.8,52.8,None,None,None,"2022-09-01",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/september/"),
    Record("ISM_MANUFACTURING_PMI","ISM","2022-10-03","10:00 ET","September 2022",50.9,52.8,None,None,None,"2022-10-03",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/october/"),
    Record("ISM_MANUFACTURING_PMI","ISM","2022-11-01","10:00 ET","October 2022",50.2,50.9,None,None,None,"2022-11-01",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/november/"),
    Record("ISM_MANUFACTURING_PMI","ISM","2022-12-01","10:00 ET","November 2022",49.0,50.2,None,None,None,"2022-12-01",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/december/"),
    Record("ISM_MANUFACTURING_PMI","ISM","2023-01-04","10:00 ET","December 2022",48.4,49.0,None,None,None,"2023-01-04",
           "ISM Manufacturing ISM Report On Business","https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/january/"),
]


# ---------------------------------------------------------------------
# BEA GDP — quarterly vintage records
#
# The field `actual` is real GDP annualized q/q growth.
# Estimate stage is encoded in reference_period.
#
# We intentionally do NOT overwrite an early estimate with later
# revisions. Each release is a separate information-set observation.
# ---------------------------------------------------------------------
GDP_RECORDS = [
    Record("GDP","BEA","2022-06-29","08:30 ET","Q1 2022 — Third Estimate",-1.6,-1.5,None,None,None,"2022-06-29",
           "U.S. Bureau of Economic Analysis — GDP Third Estimate",
           "https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-first-quarter-2022"),

    Record("GDP","BEA","2022-09-29","08:30 ET","Q2 2022 — Third Estimate",-0.6,-0.6,None,None,None,"2022-09-29",
           "U.S. Bureau of Economic Analysis — GDP Third Estimate",
           "https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-second-quarter-2022"),

    Record("GDP","BEA","2022-10-27","08:30 ET","Q3 2022 — Advance Estimate",2.6,None,None,None,None,"2022-10-27",
           "U.S. Bureau of Economic Analysis — GDP Advance Estimate",
           "https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-second-quarter-2022"),

    Record("GDP","BEA","2022-11-30","08:30 ET","Q3 2022 — Second Estimate",2.9,2.6,0.3,None,None,"2022-11-30",
           "U.S. Bureau of Economic Analysis — GDP Second Estimate",
           "https://www.bea.gov/news/2022/gross-domestic-product-second-estimate-corporate-profits-third-quarter-2022"),

    Record("GDP","BEA","2022-12-22","08:30 ET","Q3 2022 — Third Estimate",3.2,2.9,0.3,None,None,"2022-12-22",
           "U.S. Bureau of Economic Analysis — GDP Third Estimate",
           "https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-third-quarter-2022"),

    Record("GDP","BEA","2023-01-26","08:30 ET","Q4 2022 — Advance Estimate",2.9,None,None,None,None,"2023-01-26",
           "U.S. Bureau of Economic Analysis — GDP Advance Estimate",
           "https://www.bea.gov/news/2023/gross-domestic-product-fourth-quarter-and-year-2022-advance-estimate"),
]


# ---------------------------------------------------------------------
# 2023 PIT repair batch
#
# Previous values are the values available in the release itself.
# They are NOT backfilled from today's revised databases.
#
# This is critical for point-in-time research: a later revision must
# never leak backward into an earlier information set.
# ---------------------------------------------------------------------
BATCH_2023_1 = [
    # January 2023 CPI / Core CPI — released 2023-02-14
    Record("CPI","BLS","2023-02-14","08:30 ET","January 2023",0.5,0.1,None,None,None,"2023-02-14",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_02142023.htm"),
    Record("CORE_CPI","BLS","2023-02-14","08:30 ET","January 2023",0.4,0.4,None,None,None,"2023-02-14",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_02142023.htm"),

    # February 2023 CPI / Core CPI — released 2023-03-14
    Record("CPI","BLS","2023-03-14","08:30 ET","February 2023",0.4,0.5,None,None,None,"2023-03-14",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_03142023.htm"),
    Record("CORE_CPI","BLS","2023-03-14","08:30 ET","February 2023",0.5,0.4,None,None,None,"2023-03-14",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_03142023.htm"),

    # March 2023 CPI / Core CPI — released 2023-04-12
    Record("CPI","BLS","2023-04-12","08:30 ET","March 2023",0.1,0.4,None,None,None,"2023-04-12",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_04122023.htm"),
    Record("CORE_CPI","BLS","2023-04-12","08:30 ET","March 2023",0.4,0.5,None,None,None,"2023-04-12",
           "BLS CPI News Release","https://www.bls.gov/news.release/archives/cpi_04122023.htm"),

    # January 2023 NFP / unemployment — released 2023-02-03
    # December NFP was +260k in this release vintage.
    Record("NFP","BLS","2023-02-03","08:30 ET","January 2023",517000,260000,None,None,None,"2023-02-03",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_02032023.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2023-02-03","08:30 ET","January 2023",3.4,3.5,None,None,None,"2023-02-03",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_02032023.htm"),

    # February 2023 NFP / unemployment — released 2023-03-10
    # January NFP was still +517k in this release vintage; it was revised
    # later to +504k in the April information set.
    Record("NFP","BLS","2023-03-10","08:30 ET","February 2023",311000,517000,None,None,None,"2023-03-10",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_03102023.htm"),
    Record("UNEMPLOYMENT_RATE","BLS","2023-03-10","08:30 ET","February 2023",3.6,3.4,None,None,None,"2023-03-10",
           "BLS Employment Situation","https://www.bls.gov/news.release/archives/empsit_03102023.htm"),
]


def validate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, r in df.iterrows():
        issues = []

        required = [
            "indicator", "agency", "release_date", "release_time",
            "reference_period", "actual", "vintage_date", "source",
            "source_url"
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

        if pd.notna(r.get("previous")) and pd.isna(r.get("actual")):
            issues.append("previous_without_actual")

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
    print("ECONOMIC INTELLIGENCE — PHASE 1B.4")
    print("HISTORICAL COLLECTOR v1.6 — PIT + PREVIOUS-VINTAGE REPAIR + 2023")
    print("=" * 72)

    records = BASE_RECORDS + GDP_RECORDS + BATCH_2023_1
    df = pd.DataFrame([asdict(r) for r in records])

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
    print(f"Records with previous:       {int(df['previous'].notna().sum())}/{total}")
    print(f"2023 batch records:          {len(BATCH_2023_1)}")

    print("\nBY INDICATOR")
    print(df["indicator"].value_counts().sort_index().to_string())

    print("\nGDP VINTAGE STAGES")
    print(df.loc[df["indicator"] == "GDP",
                ["release_date","reference_period","actual","previous","revision"]]
          .to_string(index=False))

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_QUALITY}")

    if pit != total:
        print("\nPIT QUALITY GATE: FAIL")
        print(quality.loc[~quality["point_in_time_safe"]].to_string(index=False))
        raise RuntimeError("Historical data quality gate failed.")

    print("\nPIT QUALITY GATE: PASS")
    print("Previous values are release-vintage values; no later revisions are backfilled.")
    print("Research-only. No Decision Engine integration.")


if __name__ == "__main__":
    main()
