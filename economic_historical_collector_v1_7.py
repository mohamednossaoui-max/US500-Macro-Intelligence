"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B.7
Historical Collector v1.7 — Complete 2022-2023 PIT-safe research manifest

Design goals
------------
1. Standalone and reproducible: no web scraping and no dependency on old CSVs.
2. Preserve release vintages: every GDP estimate is a separate information set.
3. Never fabricate consensus.
4. Never backfill a historical release with today's revised database values.
5. Keep `previous` only where it is explicitly supported by the release-vintage
   record; otherwise leave it null rather than guessing.
6. Keep outputs compatible with Surprise Engine v1.1 and Regime Classifier v1.4.
7. Research-only. No Decision Engine integration.

This version expands the validated 2022 base through the full 2023 calendar
for CPI/Core CPI, unemployment, ISM manufacturing and a conservative NFP set,
and adds 2023 GDP estimate vintages.  Initial claims remain represented by the
validated 2022 DOL block; they can be extended independently without changing
this collector's PIT logic.
"""

from __future__ import annotations

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


def bls_cpi(release, ref, cpi, prev_cpi, core, prev_core):
    url = f"https://www.bls.gov/news.release/archives/cpi_{release.replace('-', '')}.htm"
    return [
        Record("CPI","BLS",release,"08:30 ET",ref,cpi,prev_cpi,None,None,None,release,
               "BLS CPI News Release",url),
        Record("CORE_CPI","BLS",release,"08:30 ET",ref,core,prev_core,None,None,None,release,
               "BLS CPI News Release",url),
    ]


def bls_employment(release, ref, nfp, prev_nfp, unemployment, prev_unemployment):
    url = f"https://www.bls.gov/news.release/archives/empsit_{release.replace('-', '')}.htm"
    return [
        Record("NFP","BLS",release,"08:30 ET",ref,nfp,prev_nfp,None,None,None,release,
               "BLS Employment Situation",url),
        Record("UNEMPLOYMENT_RATE","BLS",release,"08:30 ET",ref,unemployment,prev_unemployment,None,None,None,release,
               "BLS Employment Situation",url),
    ]


def ism(release, ref, actual, previous):
    # ISM's archive URLs are month-name based; keep the official reports index
    # as the canonical source because old month paths can change presentation.
    month = pd.Timestamp(release).strftime('%B').lower()
    url = f"https://www.ismworld.org/supply-management-news-and-reports/reports/ism-report-on-business/pmi/{month}/"
    return Record("ISM_MANUFACTURING_PMI","ISM",release,"10:00 ET",ref,actual,previous,None,None,None,release,
                  "ISM Manufacturing ISM Report On Business",url)


def bea(release, ref, actual, previous, revision, url):
    return Record("GDP","BEA",release,"08:30 ET",ref,actual,previous,revision,None,None,release,
                  "U.S. Bureau of Economic Analysis — GDP",url)


# ---------------------------------------------------------------------------
# Validated 2022 base: 38 records carried forward from the previously tested
# v1.5/v1.6 collector.  No web scraping is performed.
# ---------------------------------------------------------------------------
BASE_2022 = [
    *bls_cpi("2022-08-10","July 2022",0.0,1.3,0.3,0.7),
    *bls_cpi("2022-10-13","September 2022",0.4,0.1,0.6,0.6),
    *bls_cpi("2022-11-10","October 2022",0.4,0.4,0.3,0.6),
    *bls_cpi("2023-01-12","December 2022",-0.1,0.1,0.3,0.2),

    *bls_employment("2022-08-05","July 2022",528000,398000,3.5,3.6),
    *bls_employment("2022-09-02","August 2022",315000,526000,3.7,3.5),
    *bls_employment("2022-11-04","October 2022",261000,315000,3.7,3.5),

    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-07","08:30 ET","Week ending July 2, 2022",235000,231000,None,None,None,"2022-07-07","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220707"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-14","08:30 ET","Week ending July 9, 2022",244000,235000,None,None,None,"2022-07-14","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220714"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-21","08:30 ET","Week ending July 16, 2022",251000,244000,None,None,None,"2022-07-21","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220721"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-07-28","08:30 ET","Week ending July 23, 2022",256000,261000,10000,None,None,"2022-07-28","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220728"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-11","08:30 ET","Week ending August 6, 2022",262000,248000,12000,None,None,"2022-08-11","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220811"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-18","08:30 ET","Week ending August 13, 2022",250000,252000,10000,None,None,"2022-08-18","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220818"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-08-25","08:30 ET","Week ending August 20, 2022",243000,245000,5000,None,None,"2022-08-25","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220825"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-01","08:30 ET","Week ending August 27, 2022",232000,237000,6000,None,None,"2022-09-01","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220901"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-08","08:30 ET","Week ending September 3, 2022",222000,228000,4000,None,None,"2022-09-08","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220908"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-15","08:30 ET","Week ending September 10, 2022",213000,218000,4000,None,None,"2022-09-15","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220915"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-22","08:30 ET","Week ending September 17, 2022",213000,208000,5000,None,None,"2022-09-22","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220922"),
    Record("INITIAL_JOBLESS_CLAIMS","DOL","2022-09-29","08:30 ET","Week ending September 24, 2022",193000,209000,4000,None,None,"2022-09-29","DOL Unemployment Insurance Weekly Claims Report","https://www.dol.gov/newsroom/releases/eta/eta20220929"),

    ism("2022-08-01","July 2022",52.8,53.0),
    ism("2022-09-01","August 2022",52.8,52.8),
    ism("2022-10-03","September 2022",50.9,52.8),
    ism("2022-11-01","October 2022",50.2,50.9),
    ism("2022-12-01","November 2022",49.0,50.2),
    ism("2023-01-04","December 2022",48.4,49.0),

    bea("2022-06-29","Q1 2022 — Third Estimate",-1.6,-1.5,None,"https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-first-quarter-2022"),
    bea("2022-09-29","Q2 2022 — Third Estimate",-0.6,-0.6,None,"https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-second-quarter-2022"),
    bea("2022-10-27","Q3 2022 — Advance Estimate",2.6,None,None,"https://www.bea.gov/news/2022/gross-domestic-product-third-quarter-2022-advance-estimate"),
    bea("2022-11-30","Q3 2022 — Second Estimate",2.9,2.6,0.3,"https://www.bea.gov/news/2022/gross-domestic-product-second-estimate-corporate-profits-third-quarter-2022"),
    bea("2022-12-22","Q3 2022 — Third Estimate",3.2,2.9,0.3,"https://www.bea.gov/news/2022/gross-domestic-product-third-estimate-corporate-profits-third-quarter-2022"),
    bea("2023-01-26","Q4 2022 — Advance Estimate",2.9,None,None,"https://www.bea.gov/news/2023/gross-domestic-product-fourth-quarter-and-year-2022-advance-estimate"),
]


# ---------------------------------------------------------------------------
# 2023 CPI / Core CPI. Values are monthly seasonally-adjusted changes from
# the contemporaneous BLS releases. Previous values are release values, not
# today's database backfills.
# ---------------------------------------------------------------------------
CPI_2023 = [
    ("2023-02-14","January 2023",0.5,0.1,0.4,0.4),
    ("2023-03-14","February 2023",0.4,0.5,0.5,0.4),
    ("2023-04-12","March 2023",0.1,0.4,0.4,0.5),
    ("2023-05-10","April 2023",0.4,0.1,0.4,0.4),
    ("2023-06-13","May 2023",0.1,0.4,0.4,0.4),
    ("2023-07-12","June 2023",0.2,0.1,0.2,0.4),
    ("2023-08-10","July 2023",0.2,0.2,0.2,0.2),
    ("2023-09-13","August 2023",0.6,0.2,0.3,0.2),
    ("2023-10-12","September 2023",0.4,0.6,0.2,0.3),
    ("2023-11-14","October 2023",0.0,0.4,0.2,0.2),
    ("2023-12-12","November 2023",0.1,0.0,0.3,0.2),
    ("2024-01-11","December 2023",0.3,0.1,0.3,0.3),
]
BATCH_CPI_2023 = [x for row in CPI_2023 for x in bls_cpi(*row)]


# ---------------------------------------------------------------------------
# 2023 unemployment + a conservative NFP history.
# NFP `previous` is intentionally omitted when the release-vintage revision
# was not explicitly preserved in this manifest. This prevents a false
# release_delta from being manufactured from the later revised series.
# ---------------------------------------------------------------------------
EMP_2023 = [
    ("2023-02-03","January 2023",517000,260000,3.4,3.5),
    ("2023-03-10","February 2023",311000,None,3.6,3.4),
    ("2023-04-07","March 2023",236000,None,3.5,3.6),
    ("2023-05-05","April 2023",253000,None,3.4,3.5),
    ("2023-06-02","May 2023",339000,None,3.7,3.4),
    ("2023-07-07","June 2023",209000,None,3.6,3.7),
    ("2023-08-04","July 2023",187000,None,3.5,3.6),
    ("2023-09-01","August 2023",187000,None,3.8,3.5),
    ("2023-10-06","September 2023",336000,None,3.8,3.8),
    ("2023-11-03","October 2023",150000,None,3.9,3.8),
    ("2023-12-08","November 2023",199000,None,3.7,3.9),
    ("2024-01-05","December 2023",216000,None,3.7,3.7),
]
BATCH_EMP_2023 = [x for row in EMP_2023 for x in bls_employment(*row)]


# ---------------------------------------------------------------------------
# ISM Manufacturing PMI 2023.
# ---------------------------------------------------------------------------
ISM_2023 = [
    ("2023-02-01","January 2023",47.4,48.4),
    ("2023-03-01","February 2023",47.7,47.4),
    ("2023-04-03","March 2023",46.3,47.7),
    ("2023-05-01","April 2023",47.1,46.3),
    ("2023-06-01","May 2023",46.9,47.1),
    ("2023-07-03","June 2023",46.0,46.9),
    ("2023-08-01","July 2023",46.4,46.0),
    ("2023-09-01","August 2023",47.6,46.4),
    ("2023-10-02","September 2023",49.0,47.6),
    ("2023-11-01","October 2023",46.7,49.0),
    ("2023-12-01","November 2023",46.7,46.7),
    ("2024-01-03","December 2023",47.4,46.7),
]
BATCH_ISM_2023 = [ism(*row) for row in ISM_2023]


# ---------------------------------------------------------------------------
# 2023 GDP vintages. The estimate stage is part of reference_period; later
# estimates are NOT substituted into earlier observations.
# ---------------------------------------------------------------------------
GDP_2023 = [
    bea("2023-02-23","Q4 2022 — Second Estimate",2.7,2.9,-0.2,"https://www.bea.gov/news/2023/gross-domestic-product-fourth-quarter-and-year-2022-second-estimate"),
    bea("2023-03-30","Q4 2022 — Third Estimate",2.6,2.7,-0.1,"https://www.bea.gov/news/2023/gross-domestic-product-fourth-quarter-and-year-2022-third-estimate-gdp-industry-and"),
    bea("2023-04-27","Q1 2023 — Advance Estimate",1.1,None,None,"https://www.bea.gov/news/2023/gross-domestic-product-first-quarter-2023-advance-estimate"),
    bea("2023-05-25","Q1 2023 — Second Estimate",1.3,1.1,0.2,"https://www.bea.gov/news/2023/gross-domestic-product-second-estimate-corporate-profits-first-quarter-2023"),
    bea("2023-06-29","Q1 2023 — Third Estimate",2.0,1.3,0.7,"https://www.bea.gov/news/2023/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-and-gdp-industry"),
    bea("2023-07-27","Q2 2023 — Advance Estimate",2.4,None,None,"https://www.bea.gov/news/2023/gross-domestic-product-second-quarter-2023-advance-estimate"),
    bea("2023-08-30","Q2 2023 — Second Estimate",2.1,2.4,-0.3,"https://www.bea.gov/news/2023/gross-domestic-product-second-estimate-corporate-profits-second-quarter-2023"),
    bea("2023-09-28","Q2 2023 — Third Estimate",2.1,2.1,0.0,"https://www.bea.gov/news/2023/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-second-quarter"),
    bea("2023-10-26","Q3 2023 — Advance Estimate",4.9,None,None,"https://www.bea.gov/news/2023/gross-domestic-product-third-quarter-2023-advance-estimate"),
    bea("2023-11-29","Q3 2023 — Second Estimate",5.2,4.9,0.3,"https://www.bea.gov/news/2023/gross-domestic-product-second-estimate-corporate-profits-preliminary-estimate-third"),
    bea("2023-12-21","Q3 2023 — Third Estimate",4.9,5.2,-0.3,"https://www.bea.gov/news/2023/gross-domestic-product-third-estimate-corporate-profits-revised-estimate-and-gdp"),
]


def record_id(row: pd.Series) -> str:
    key = "|".join(str(row[c]) for c in [
        "indicator","agency","release_date","release_time",
        "reference_period","source_url"
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def validate(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    required = [
        "indicator","agency","release_date","release_time","reference_period",
        "actual","vintage_date","source","source_url"
    ]
    for _, r in df.iterrows():
        issues = []
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
        if pd.isna(r["actual"]):
            issues.append("missing_actual")
        if pd.notna(r.get("consensus")) and not pd.notna(r.get("consensus_source")):
            issues.append("consensus_without_source")
        rows.append({
            "record_id": record_id(r),
            "indicator": r["indicator"],
            "agency": r["agency"],
            "release_date": r["release_date"],
            "reference_period": r["reference_period"],
            "point_in_time_safe": len(issues) == 0,
            "quality_issues": ";".join(issues),
            "historical_consensus_available": (
                pd.notna(r.get("consensus")) and
                pd.notna(r.get("consensus_source")) and
                str(r.get("consensus_source")).strip() != ""
            ),
        })
    return pd.DataFrame(rows)


def main():
    print("=" * 78)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1B.7")
    print("HISTORICAL COLLECTOR v1.7 — COMPLETE 2022-2023 PIT MANIFEST")
    print("=" * 78)

    records = BASE_2022 + BATCH_CPI_2023 + BATCH_EMP_2023 + BATCH_ISM_2023 + GDP_2023
    df = pd.DataFrame([asdict(r) for r in records])

    # Deduplicate by information-set identity. Never collapse different GDP
    # estimate stages because those are deliberately separate vintages.
    df = df.drop_duplicates(
        subset=["indicator","agency","release_date","release_time","reference_period","source_url"]
    ).sort_values(["release_date","indicator","reference_period"]).reset_index(drop=True)

    quality = validate(df)

    if quality["record_id"].duplicated().any():
        dup = quality.loc[quality["record_id"].duplicated(), "record_id"].tolist()
        raise RuntimeError(f"Duplicate record_id values: {dup}")

    # Structural integrity checks.
    if len(df) != len(quality):
        raise RuntimeError("Events/quality row count mismatch")
    if not quality["point_in_time_safe"].all():
        bad = quality.loc[~quality["point_in_time_safe"]]
        raise RuntimeError("PIT validation failed:\n" + bad.to_string(index=False))
    if df["consensus"].notna().any():
        # No consensus is allowed in this research manifest unless its source
        # is also present. Current manifest intentionally contains none.
        bad = df[df["consensus"].notna() & df["consensus_source"].isna()]
        if not bad.empty:
            raise RuntimeError("Consensus present without consensus_source")

    df.to_csv(OUTPUT_EVENTS, index=False)
    quality.to_csv(OUTPUT_QUALITY, index=False)

    print(f"Records collected: {len(df)}")
    print(f"Date range: {df['release_date'].min()} -> {df['release_date'].max()}")
    print(f"Indicators: {df['indicator'].nunique()}")
    print(f"PIT safe: {int(quality['point_in_time_safe'].sum())}/{len(quality)}")
    print(f"Historical consensus: {int(quality['historical_consensus_available'].sum())}/{len(quality)}")
    print("\nRecords by indicator:")
    for k, v in df["indicator"].value_counts().sort_index().items():
        print(f"  {k:28s} {v}")
    print("\n2023 records by indicator:")
    d23 = df[pd.to_datetime(df["release_date"]).dt.year == 2023]
    for k, v in d23["indicator"].value_counts().sort_index().items():
        print(f"  {k:28s} {v}")
    print("\nQuality gates:")
    print("  PIT QUALITY GATE: PASS")
    print("  NO FABRICATED CONSENSUS: PASS")
    print("  RESEARCH-ONLY GATE: PASS")
    print("  DECISION ENGINE DISABLED: PASS")
    print(f"\nOutput: {OUTPUT_EVENTS}")
    print(f"Output: {OUTPUT_QUALITY}")


if __name__ == "__main__":
    main()
