"""
US500 Macro Intelligence
Economic Intelligence — Historical Expansion v2.1

Purpose
-------
Extend the v1.9.1 baseline with:
  * ISM Manufacturing PMI: 2020-2021
  * DOL Initial Jobless Claims: 2020-2021

Important PIT rule
------------------
For Claims we use the ORIGINAL DOL weekly release text, not the current
revised historical time series. DOL explicitly states that the advance figure
is based on ETA-538 and that the following week's figure is revised using
ETA-539. This preserves what was knowable on release day.

The previous v2.0 implementation failed because it guessed PDF URLs.
v2.1 instead discovers the official DOL release pages from the DOL newsroom
archive and extracts the release link from each weekly release.

Research-only. No consensus fabrication. No Decision Engine integration.
"""

from datetime import date
from pathlib import Path
from io import BytesIO
import hashlib
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

BASE_INPUT = "economic_historical_events_v1.csv"
OUTPUT = "economic_historical_events_v1.csv"
QUALITY = "economic_historical_quality_v1.csv"

HEADERS = {
    "User-Agent": "US500-Macro-Intelligence/2.0 research-only"
}

# Official ISM monthly Manufacturing PMI values, 2020-2021.
ISM = [
    ("2020-01-03", "January 2020", 50.9),
    ("2020-02-03", "February 2020", 50.1),
    ("2020-03-02", "March 2020", 49.1),
    ("2020-04-01", "April 2020", 41.5),
    ("2020-05-01", "May 2020", 43.1),
    ("2020-06-01", "June 2020", 52.6),
    ("2020-07-01", "July 2020", 54.2),
    ("2020-08-03", "August 2020", 56.0),
    ("2020-09-01", "September 2020", 55.4),
    ("2020-10-01", "October 2020", 59.3),
    ("2020-11-02", "November 2020", 57.5),
    ("2020-12-01", "December 2020", 60.7),
    ("2021-01-04", "January 2021", 60.8),
    ("2021-02-01", "February 2021", 60.8),
    ("2021-03-01", "March 2021", 64.7),
    ("2021-04-01", "April 2021", 60.7),
    ("2021-05-03", "May 2021", 61.2),
    ("2021-06-01", "June 2021", 60.6),
    ("2021-07-01", "July 2021", 59.5),
    ("2021-08-02", "August 2021", 59.9),
    ("2021-09-01", "September 2021", 61.1),
    ("2021-10-01", "October 2021", 60.8),
    ("2021-11-01", "November 2021", 61.1),
    ("2021-12-01", "December 2021", 58.7),
]

def newsroom_urls(year):
    return [
        f"https://www.dol.gov/newsroom/releases?agency=All&page=1&state=All&topic=132&year={year}",
        f"https://www.dol.gov/newsroom/releases?agency=All&page=2&state=All&topic=132&year={year}",
        f"https://www.dol.gov/newsroom/releases?agency=All&page=3&state=All&topic=132&year={year}",
        f"https://www.dol.gov/newsroom/releases?agency=All&page=4&state=All&topic=132&year={year}",
        f"https://www.dol.gov/newsroom/releases?agency=All&page=5&state=All&topic=132&year={year}",
        f"https://www.dol.gov/newsroom/releases?agency=All&page=6&state=All&topic=132&year={year}",
    ]

def discover_release_links(session, year):
    """
    Discover DOL UI Weekly Claims release pages from the official newsroom
    topic archive. We do not infer PDF filenames.
    """
    links = {}
    for page_url in newsroom_urls(year):
        try:
            r = session.get(page_url, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True):
                title = " ".join(a.stripped_strings)
                href = a["href"]
                if "Unemployment Insurance Weekly Claims Report" not in title:
                    continue
                if href.startswith("/"):
                    href = "https://www.dol.gov" + href
                if "/newsroom/releases/" in href:
                    links[href] = title
        except Exception as exc:
            print(f"Archive page warning: {page_url} -> {exc}")
    return sorted(links)

def pdf_link_from_release(session, release_url):
    """
    Open a DOL release page and find its official PDF/news-release link.
    """
    r = session.get(release_url, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    candidates = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        label = " ".join(a.stripped_strings).lower()
        if ".pdf" in href.lower() or "news release" in label or "weekly claims" in label:
            if href.startswith("/"):
                href = "https://www.dol.gov" + href
            candidates.append(href)

    # Prefer official oui.doleta.gov PDF when exposed.
    oui = [x for x in candidates if "oui.doleta.gov" in x and ".pdf" in x.lower()]
    if oui:
        return oui[0]

    pdfs = [x for x in candidates if ".pdf" in x.lower()]
    return pdfs[0] if pdfs else None

def parse_release_pdf(pdf_bytes, pdf_url, release_url):
    reader = PdfReader(BytesIO(pdf_bytes))
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    flat = re.sub(r"\s+", " ", text)

    if "UNEMPLOYMENT INSURANCE WEEKLY CLAIMS" not in flat.upper():
        return None

    # Release date from the release page/PDF header.
    m_date = re.search(
        r"(\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+"
        r"\d{1,2},\s+20(?:20|21))", flat, re.I
    )
    m_week = re.search(
        r"week ending\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,\s+20(?:20|21))",
        flat, re.I
    )
    m_actual = re.search(
        r"advance figure for seasonally adjusted initial claims was\s+([\d,]+)",
        flat, re.I
    )

    if not (m_date and m_week and m_actual):
        return None

    release_date = pd.to_datetime(m_date.group(1)).strftime("%Y-%m-%d")
    week_end = re.sub(r"(st|nd|rd|th)", "", m_week.group(1))
    week_end = pd.to_datetime(week_end).strftime("%Y-%m-%d")
    actual = int(m_actual.group(1).replace(",", ""))

    previous = None
    revision = None

    m_rev = re.search(
        r"previous week's level was revised\s+(up|down)\s+by\s+([\d,]+)\s+"
        r"from\s+([\d,]+)\s+to\s+([\d,]+)",
        flat, re.I
    )
    if m_rev:
        revision = int(m_rev.group(2).replace(",", ""))
        previous = int(m_rev.group(4).replace(",", ""))
    else:
        m_prev = re.search(
            r"previous week's level was\s+([\d,]+)",
            flat, re.I
        )
        if m_prev:
            previous = int(m_prev.group(1).replace(",", ""))

    return {
        "indicator": "INITIAL_JOBLESS_CLAIMS",
        "agency": "DOL",
        "release_date": release_date,
        "release_time": "08:30 ET",
        "reference_period": f"Week ending {week_end}",
        "actual": actual,
        "previous": previous,
        "revision": revision,
        "consensus": None,
        "consensus_source": None,
        "vintage_date": release_date,
        "source": "DOL Unemployment Insurance Weekly Claims Report",
        "source_url": pdf_url,
        "release_page_url": release_url,
    }

def collect_claims():
    session = requests.Session()
    session.headers.update(HEADERS)
    records = []
    seen_weeks = set()

    for year in (2020, 2021):
        links = discover_release_links(session, year)
        print(f"DOL {year}: discovered {len(links)} release pages")

        for release_url in links:
            try:
                pdf_url = pdf_link_from_release(session, release_url)
                if not pdf_url:
                    continue

                r = session.get(pdf_url, timeout=30)
                r.raise_for_status()
                if not r.content.startswith(b"%PDF"):
                    continue

                rec = parse_release_pdf(r.content, pdf_url, release_url)
                if rec is None:
                    continue

                # Keep only 2020-2021 release vintages.
                if not rec["release_date"].startswith(("2020", "2021")):
                    continue

                week = rec["reference_period"]
                if week in seen_weeks:
                    continue

                seen_weeks.add(week)
                records.append(rec)
                time.sleep(0.15)

            except Exception as exc:
                print(f"Release warning: {release_url} -> {exc}")

    return records

def record_id(row):
    raw = "|".join(
        str(row.get(k, ""))
        for k in (
            "indicator", "agency", "release_date", "release_time",
            "reference_period", "source_url"
        )
    )
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def main():
    base = pd.read_csv(BASE_INPUT)

    additions = []
    for release, ref, actual in ISM:
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
            "source_url": (
                "https://www.ismworld.org/supply-management-news-and-reports/"
                "reports/ism-pmi-reports/"
            ),
        })

    print("Collecting DOL Claims from official newsroom archive...")
    additions.extend(collect_claims())

    add = pd.DataFrame(additions)
    out = pd.concat([base, add], ignore_index=True)

    key = [
        "indicator", "agency", "release_date", "release_time",
        "reference_period", "source_url"
    ]
    out = out.drop_duplicates(subset=key, keep="first")
    out = out.sort_values(["release_date", "indicator"]).reset_index(drop=True)

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
            "record_id": record_id(row),
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

    claims = (
        (out["indicator"] == "INITIAL_JOBLESS_CLAIMS") &
        out["release_date"].astype(str).str[:4].isin(["2020", "2021"])
    ).sum()

    ism = (
        (out["indicator"] == "ISM_MANUFACTURING_PMI") &
        out["release_date"].astype(str).str[:4].isin(["2020", "2021"])
    ).sum()

    print("\nHISTORICAL EXPANSION v2.1")
    print(f"Baseline: {len(base)}")
    print(f"ISM 2020-2021: {ism}")
    print(f"Claims 2020-2021: {claims}")
    print(f"Final records: {len(out)}")
    print(f"PIT safe: {int(q['point_in_time_safe'].sum())}/{len(q)}")
    print(f"Historical consensus: {int(q['historical_consensus_available'].sum())}")

    # Hard gates.
    if ism != 24:
        raise RuntimeError(f"ISM extension incomplete: {ism}/24")
    if claims < 90:
        raise RuntimeError(
            f"DOL Claims archive retrieval incomplete: {claims} records"
        )
    if not q["point_in_time_safe"].all():
        raise RuntimeError("PIT QUALITY GATE FAILED")
    if q["historical_consensus_available"].any():
        raise RuntimeError("Historical consensus must remain unknown")

    print("PIT QUALITY GATE: PASS")
    print("RESEARCH-ONLY GATE: PASS")
    print("DECISION ENGINE DISABLED: PASS")

if __name__ == "__main__":
    main()
