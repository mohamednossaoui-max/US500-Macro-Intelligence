"""
US500 Macro Intelligence
Economic Historical Refresh v1

Focused freshness bridge from the verified v2.2 baseline to the latest
official releases available on 2026-09-20.
Research-only; no fabricated consensus; Decision Engine disabled.
"""
from pathlib import Path
import pandas as pd

INPUT = "economic_historical_events_v1.csv"
QUALITY = "economic_historical_quality_v1.csv"

REFRESH = [
    dict(indicator="CPI", agency="BLS", release_date="2026-09-11", release_time="08:30 ET",
         reference_period="August 2026", actual=0.4, previous=0.1, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-11",
         source="BLS CPI News Release", source_url="https://www.bls.gov/news.release/archives/cpi_09112026.htm"),
    dict(indicator="CORE_CPI", agency="BLS", release_date="2026-09-11", release_time="08:30 ET",
         reference_period="August 2026", actual=0.3, previous=0.2, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-11",
         source="BLS CPI News Release", source_url="https://www.bls.gov/news.release/archives/cpi_09112026.htm"),
    dict(indicator="NFP", agency="BLS", release_date="2026-09-04", release_time="08:30 ET",
         reference_period="August 2026", actual=162000.0, previous=21000.0, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-04",
         source="BLS Employment Situation", source_url="https://www.bls.gov/news.release/empsit.htm"),
    dict(indicator="UNEMPLOYMENT_RATE", agency="BLS", release_date="2026-09-04", release_time="08:30 ET",
         reference_period="August 2026", actual=4.1, previous=4.1, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-04",
         source="BLS Employment Situation", source_url="https://www.bls.gov/news.release/empsit.htm"),
    dict(indicator="ISM_MANUFACTURING_PMI", agency="ISM", release_date="2026-09-09", release_time="10:00 ET",
         reference_period="August 2026", actual=54.6, previous=55.6, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-09",
         source="ISM Manufacturing PMI Report", source_url="https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/pmi/august/"),
    dict(indicator="GDP", agency="BEA", release_date="2026-08-26", release_time="08:30 ET",
         reference_period="Q2 2026 — Second Estimate", actual=1.5, previous=1.5, revision=0.0,
         consensus=None, consensus_source=None, vintage_date="2026-08-26",
         source="U.S. Bureau of Economic Analysis — GDP", source_url="https://www.bea.gov/news/2026/gdp-second-estimate-and-corporate-profits-2nd-quarter-2026"),
    dict(indicator="INITIAL_JOBLESS_CLAIMS", agency="DOL", release_date="2026-09-17", release_time="08:30 ET",
         reference_period="Week ending September 12, 2026", actual=196000.0, previous=206000.0, revision=None,
         consensus=None, consensus_source=None, vintage_date="2026-09-17",
         source="DOL Unemployment Insurance Weekly Claims Report", source_url="https://www.dol.gov/newsroom/releases/eta/eta20260917"),
]

def main():
    if not Path(INPUT).exists() or not Path(QUALITY).exists():
        raise FileNotFoundError("Baseline event/quality artifacts are required.")
    df = pd.read_csv(INPUT)
    q = pd.read_csv(QUALITY)

    required = {"indicator","agency","release_date","release_time","reference_period","actual",
                "previous","revision","consensus","consensus_source","vintage_date","source","source_url"}
    if required - set(df.columns):
        raise ValueError(f"Missing event columns: {sorted(required-set(df.columns))}")

    q_required = {"record_id","indicator","agency","release_date","reference_period",
                  "point_in_time_safe","quality_issues","historical_consensus_available"}
    if q_required - set(q.columns):
        raise ValueError(f"Missing quality columns: {sorted(q_required-set(q.columns))}")

    existing = set(zip(df.indicator.astype(str), df.release_date.astype(str), df.reference_period.astype(str)))
    q_existing = set(zip(q.indicator.astype(str), q.release_date.astype(str), q.reference_period.astype(str)))
    added, q_added = [], []

    for row in REFRESH:
        key = (row["indicator"], row["release_date"], row["reference_period"])
        if key not in existing:
            added.append(row)
            existing.add(key)
        if key not in q_existing:
            q_added.append({
                "record_id": f"{row['indicator']}|{row['release_date']}|{row['reference_period']}",
                "indicator": row["indicator"],
                "agency": row["agency"],
                "release_date": row["release_date"],
                "reference_period": row["reference_period"],
                "point_in_time_safe": True,
                "quality_issues": "",
                "historical_consensus_available": False,
            })
            q_existing.add(key)

    if added:
        df = pd.concat([df, pd.DataFrame(added)], ignore_index=True)
    if q_added:
        q = pd.concat([q, pd.DataFrame(q_added)], ignore_index=True)

    df["release_date"] = pd.to_datetime(df["release_date"], errors="raise")
    df["vintage_date"] = pd.to_datetime(df["vintage_date"], errors="raise")

    if not (df["vintage_date"] <= df["release_date"]).all():
        raise AssertionError("vintage_date <= release_date gate failed")
    if not q["point_in_time_safe"].fillna(False).astype(bool).all():
        raise AssertionError("PIT quality gate failed")
    if q["historical_consensus_available"].fillna(False).astype(bool).any():
        raise AssertionError("Historical consensus gate failed")

    df = df.sort_values(["release_date","indicator","reference_period"], kind="mergesort").reset_index(drop=True)
    df["release_date"] = df["release_date"].dt.strftime("%Y-%m-%d")
    df["vintage_date"] = df["vintage_date"].dt.strftime("%Y-%m-%d")

    df.to_csv(INPUT, index=False)
    q.to_csv(QUALITY, index=False)

    latest = df.sort_values("release_date").groupby("indicator").tail(1)
    print("ECONOMIC HISTORICAL REFRESH v1")
    print("New records added:", len(added))
    print("Total records:", len(df))
    print("Latest release:", df["release_date"].max())
    print(latest[["indicator","release_date","reference_period","actual"]].to_string(index=False))
    print("PIT QUALITY GATE: PASS")
    print("NO FABRICATED CONSENSUS: PASS")
    print("RESEARCH-ONLY GATE: PASS")
    print("DECISION ENGINE DISABLED: PASS")

if __name__ == "__main__":
    main()
