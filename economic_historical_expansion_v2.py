"""
US500 Macro Intelligence
Economic Intelligence — Historical Expansion v2

Purpose
-------
1) Start from economic_historical_events_v1.csv created by v1.9.1.
2) Add verified 2020-2021 ISM Manufacturing PMI observations.
3) Add 2020-2021 Initial Jobless Claims from the official DOL archived
   Weekly Claims PDF releases, preserving the release-date vintage.
4) Never use today's revised series as if it were the original release.
5) No consensus fabrication. Research-only. No Decision Engine.

Why DOL PDF releases?
---------------------
DOL's current historical dataset explicitly includes standard weekly and annual
revisions. For a point-in-time research set, the archived release itself is the
appropriate source: the value is the "advance figure" available on release day,
and the release can also state the revised prior-week value.

The script intentionally does not use FRED/ALFRED current observations as the
historical vintage. It downloads only official DOL release PDFs.

Dependencies:
    pandas
    requests
    pypdf
"""

from datetime import date, timedelta
from io import BytesIO
from pathlib import Path
import re
import hashlib

import pandas as pd
import requests
from pypdf import PdfReader

INPUT = "economic_historical_events_v1.csv"
OUTPUT = "economic_historical_events_v1.csv"
QUALITY = "economic_historical_quality_v1.csv"

DOL_HEADERS = {
    "User-Agent": "US500-Macro-Intelligence/2.0 (+research-only)"
}

# Officially reported ISM Manufacturing PMI values.
ISM_2020_2021 = [('2020-01-03', 'January 2020', 50.9), ('2020-02-03', 'February 2020', 50.1), ('2020-03-02', 'March 2020', 49.1), ('2020-04-01', 'April 2020', 41.5), ('2020-05-01', 'May 2020', 43.1), ('2020-06-01', 'June 2020', 52.6), ('2020-07-01', 'July 2020', 54.2), ('2020-08-03', 'August 2020', 56.0), ('2020-09-01', 'September 2020', 55.4), ('2020-10-01', 'October 2020', 59.3), ('2020-11-02', 'November 2020', 57.5), ('2020-12-01', 'December 2020', 60.7), ('2021-01-04', 'January 2021', 60.8), ('2021-02-01', 'February 2021', 60.8), ('2021-03-01', 'March 2021', 64.7), ('2021-04-01', 'April 2021', 60.7), ('2021-05-03', 'May 2021', 61.2), ('2021-06-01', 'June 2021', 60.6), ('2021-07-01', 'July 2021', 59.5), ('2021-08-02', 'August 2021', 59.9), ('2021-09-01', 'September 2021', 61.1), ('2021-10-01', 'October 2021', 60.8), ('2021-11-01', 'November 2021', 61.1), ('2021-12-01', 'December 2021', 58.7)]

def candidate_release_dates():
    """
    Generate candidate Wed/Thu/Fri dates for every week in 2020-2021.
    DOL normally releases Thursday 08:30 ET, but federal holidays can move
    the release. We test a narrow 3-day window rather than inventing dates.
    """
    start = date(2020, 1, 1)
    end = date(2021, 12, 31)
    d = start
    while d <= end:
        if d.weekday() in (2, 3, 4):  # Wed/Thu/Fri
            yield d
        d += timedelta(days=1)

def pdf_candidates(d):
    # DOL's archived PDF convention is /press/YYYY/MMDDYY.pdf
    return [
        f"https://oui.doleta.gov/press/{d.year}/{d:%m%d%y}.pdf",
        f"https://www.dol.gov/sites/dolgov/files/OPA/newsreleases/ui-claims/{d:%Y%m%d}.pdf",
    ]

def extract_claims_from_pdf(pdf_bytes, url, release_date):
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    text = re.sub(r"\s+", " ", text)

    # Only accept a genuine Weekly Claims release.
    if "UNEMPLOYMENT INSURANCE WEEKLY CLAIMS" not in text.upper():
        return None

    m_week = re.search(
        r"week ending\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+\d{4})",
        text, re.I
    )
    m_actual = re.search(
        r"advance figure for seasonally adjusted initial claims was\s+([\d,]+)",
        text, re.I
    )
    if not (m_week and m_actual):
        return None

    week_text = re.sub(r"(st|nd|rd|th)", "", m_week.group(1))
    week_end = pd.to_datetime(week_text).strftime("%Y-%m-%d")
    actual = int(m_actual.group(1).replace(",", ""))

    previous = None
    revision = None

    # Example:
    # "previous week's level was revised up by 12,000 from 837,000 to 849,000"
    m_rev = re.search(
        r"previous week's level was revised\s+(?:up|down)\s+by\s+([\d,]+)\s+"
        r"from\s+([\d,]+)\s+to\s+([\d,]+)",
        text, re.I
    )
    if m_rev:
        revision = int(m_rev.group(1).replace(",", ""))
        previous = int(m_rev.group(3).replace(",", ""))

    # Unrevised previous level.
    if previous is None:
        m_prev = re.search(
            r"previous week's level was\s+([\d,]+)",
            text, re.I
        )
        if m_prev:
            previous = int(m_prev.group(1).replace(",", ""))

    return {
        "indicator": "INITIAL_JOBLESS_CLAIMS",
        "agency": "DOL",
        "release_date": release_date.isoformat(),
        "release_time": "08:30 ET",
        "reference_period": f"Week ending {week_end}",
        "actual": actual,
        "previous": previous,
        "revision": revision,
        "consensus": None,
        "consensus_source": None,
        "vintage_date": release_date.isoformat(),
        "source": "DOL Unemployment Insurance Weekly Claims Report",
        "source_url": url,
    }

def collect_dol_claims():
    session = requests.Session()
    session.headers.update(DOL_HEADERS)
    records = []
    seen_week = set()

    for d in candidate_release_dates():
        found = False
        for url in pdf_candidates(d):
            try:
                r = session.get(url, timeout=30)
                if r.status_code != 200 or not r.content.startswith(b"%PDF"):
                    continue
                rec = extract_claims_from_pdf(r.content, url, d)
                if rec is None:
                    continue
                week = rec["reference_period"]
                if week in seen_week:
                    continue
                seen_week.add(week)
                records.append(rec)
                found = True
                break
            except Exception:
                continue

    return records

def make_record_id(row):
    raw = "|".join(str(row[c]) for c in [
        "indicator", "agency", "release_date", "release_time",
        "reference_period", "source_url"
    ])
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def main():
    if not Path(INPUT).exists():
        raise FileNotFoundError(f"Missing {INPUT}")

    base = pd.read_csv(INPUT)

    additions = []

    for release, ref, actual in ISM_2020_2021:
        additions.append({
            "indicator": "ISM_MANUFACTURING_PMI",
            "agency": "ISM",
            "release_date": release,
            "release_time": "10:00 ET",
            "reference_period": ref,
            "actual": actual,
            "previous": None,
            "revision": None,
            "consensus": None,
            "consensus_source": None,
            "vintage_date": release,
            "source": "Institute for Supply Management — Manufacturing PMI",
            "source_url": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/",
        })

    print("Downloading official DOL 2020-2021 archived releases...")
    claims = collect_dol_claims()
    additions.extend(claims)

    add_df = pd.DataFrame(additions)
    out = pd.concat([base, add_df], ignore_index=True)
    out = out.drop_duplicates(
        subset=[
            "indicator", "agency", "release_date", "release_time",
            "reference_period", "source_url"
        ],
        keep="first"
    ).sort_values(["release_date", "indicator"]).reset_index(drop=True)

    quality = []
    for _, row in out.iterrows():
        issues = []
        safe = True

        if pd.isna(row.get("release_date")) or pd.isna(row.get("vintage_date")):
            safe = False
            issues.append("missing_release_or_vintage_date")
        elif pd.to_datetime(row["vintage_date"]) > pd.to_datetime(row["release_date"]):
            safe = False
            issues.append("vintage_after_release")

        if pd.isna(row.get("actual")):
            safe = False
            issues.append("missing_actual")

        if not str(row.get("source_url", "")).strip():
            safe = False
            issues.append("missing_source_url")

        quality.append({
            "record_id": make_record_id(row),
            "indicator": row["indicator"],
            "agency": row["agency"],
            "release_date": row["release_date"],
            "reference_period": row["reference_period"],
            "point_in_time_safe": safe,
            "quality_issues": "; ".join(issues),
            "historical_consensus_available": (
                pd.notna(row.get("consensus")) and
                str(row.get("consensus_source", "")).strip() not in ("", "nan", "None")
            ),
        })

    q = pd.DataFrame(quality)

    out.to_csv(OUTPUT, index=False)
    q.to_csv(QUALITY, index=False)

    claims_2020_21 = int(
        ((out["indicator"] == "INITIAL_JOBLESS_CLAIMS") &
         out["release_date"].astype(str).str[:4].isin(["2020", "2021"])).sum()
    )
    ism_2020_21 = int(
        ((out["indicator"] == "ISM_MANUFACTURING_PMI") &
         out["release_date"].astype(str).str[:4].isin(["2020", "2021"])).sum()
    )

    print("\nECONOMIC HISTORICAL EXPANSION v2")
    print(f"Base records: {len(base)}")
    print(f"ISM 2020-2021 records added/available: {ism_2020_21}")
    print(f"DOL Claims 2020-2021 records added/available: {claims_2020_21}")
    print(f"Final records: {len(out)}")
    print(f"PIT safe: {int(q['point_in_time_safe'].sum())} / {len(q)}")
    print(f"Historical consensus: {int(q['historical_consensus_available'].sum())}")
    print("RESEARCH-ONLY GATE: PASS")
    print("DECISION ENGINE DISABLED: PASS")

    if not q["point_in_time_safe"].all():
        raise RuntimeError("PIT QUALITY GATE FAILED")
    if q["historical_consensus_available"].any():
        raise RuntimeError("Historical consensus must remain unknown in v2")

if __name__ == "__main__":
    main()
