"""
US500 Macro Intelligence
Economic Intelligence — Phase 1B
Historical Collector v1 — Batch 1 (2020-2022)

Purpose:
- Collect historical release snapshots from OFFICIAL source archives.
- Preserve release_date / release_time / vintage_date.
- Fail closed: no fabricated values, no current API revisions.
- Batch 1 currently implements BLS CPI/Core CPI and Employment Situation.
- DOL Claims, ISM PMI, and BEA GDP are deliberately left as explicit
  extension points until their official archives can be collected without
  bypassing access controls.

Outputs:
    economic_historical_events_v1.csv
    economic_historical_quality_v1.csv

Environment:
    Python 3.11+
    requests
    beautifulsoup4
    pandas
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime, date
from io import BytesIO
from typing import Optional
from urllib.parse import urljoin

import pandas as pd
import requests
from bs4 import BeautifulSoup


START_YEAR = 2020
END_YEAR = 2022

OUTPUT_EVENTS = "economic_historical_events_v1.csv"
OUTPUT_QUALITY = "economic_historical_quality_v1.csv"

HEADERS = {
    "User-Agent": (
        "US500-Macro-Intelligence/2.0 "
        "(historical-economic-research; official-source-archive)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/pdf;q=0.9,*/*;q=0.8",
}

TIMEOUT = 30
SLEEP_SECONDS = 0.25

BLS_CPI_ARCHIVE = "https://www.bls.gov/bls/news-release/cpi.htm"
BLS_EMPSIT_ARCHIVE = "https://www.bls.gov/bls/news-release/empsit.htm"


@dataclass
class Record:
    indicator: str
    agency: str
    release_date: str
    release_time: str
    reference_period: str
    actual: Optional[float]
    previous: Optional[float]
    revision: Optional[float]
    consensus: Optional[float]
    consensus_source: Optional[str]
    vintage_date: str
    source: str
    source_url: str


def session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def get(s: requests.Session, url: str) -> requests.Response:
    r = s.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    time.sleep(SLEEP_SECONDS)
    return r


def parse_release_datetime(text: str) -> tuple[str, str]:
    """
    Extract the BLS embargo timestamp, e.g.
    '8:30 a.m. (EDT) May 12, 2020'
    """
    m = re.search(
        r"(\d{1,2}:\d{2})\s*a\.m\.\s*\(([^)]+)\)\s*"
        r"([A-Z][a-z]+ \d{1,2}, \d{4})",
        text,
        flags=re.I,
    )
    if not m:
        raise ValueError("Could not identify official BLS release timestamp")

    hhmm = m.group(1)
    tz = m.group(2)
    d = datetime.strptime(m.group(3), "%B %d, %Y").date()

    # BLS releases are normally 08:30 ET. Keep the displayed timezone
    # abbreviation rather than converting it, so the source fact is preserved.
    return d.isoformat(), f"{hhmm} {tz}"


def month_from_heading(text: str) -> Optional[str]:
    m = re.search(
        r"(?:CPI|EMPLOYMENT SITUATION)\s*[–-]\s*"
        r"([A-Z][a-z]+)\s+(\d{4})",
        text,
        flags=re.I,
    )
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)}"


def archive_links(s: requests.Session, archive_url: str, pattern: str) -> list[str]:
    soup = BeautifulSoup(get(s, archive_url).text, "html.parser")
    urls = []
    for a in soup.find_all("a", href=True):
        href = urljoin(archive_url, a["href"])
        if re.search(pattern, href):
            urls.append(href)

    # Stable deterministic order and no duplicates.
    return sorted(set(urls))


def extract_number(text: str, pattern: str) -> Optional[float]:
    m = re.search(pattern, text, flags=re.I | re.S)
    if not m:
        return None
    raw = m.group(1).replace(",", "").strip()
    try:
        return float(raw)
    except ValueError:
        return None


def collect_cpi(s: requests.Session) -> list[Record]:
    records: list[Record] = []

    # BLS archive contains year/month links. We discover the official
    # release URLs from the archive instead of guessing dates.
    links = archive_links(
        s,
        BLS_CPI_ARCHIVE,
        r"/news\.release/archives/cpi_\d{8}\.(?:htm|pdf)$",
    )

    for url in links:
        try:
            if url.lower().endswith(".pdf"):
                # Prefer HTML when both HTML/PDF exist.
                continue

            text = BeautifulSoup(get(s, url).text, "html.parser").get_text(" ", strip=True)

            release_date, release_time = parse_release_datetime(text)
            year = int(release_date[:4])
            if not (START_YEAR <= year <= END_YEAR):
                continue

            reference = month_from_heading(text)
            if not reference:
                raise ValueError("CPI reference period not found")

            # CPI monthly SA change.
            actual = extract_number(
                text,
                r"rose\s+([+-]?\d+(?:\.\d+)?)\s+percent,\s+seasonally adjusted",
            )
            if actual is None:
                actual = extract_number(
                    text,
                    r"declined\s+([+-]?\d+(?:\.\d+)?)\s+percent,\s+seasonally adjusted",
                )
                if actual is not None:
                    actual = -actual

            if actual is None:
                raise ValueError("CPI monthly actual not found")

            # Previous monthly CPI is explicitly stated in the release.
            previous = extract_number(
                text,
                r"after\s+(?:rising|increasing|falling|declining|being unchanged at|"
                r"remaining unchanged at)\s+([+-]?\d+(?:\.\d+)?)\s+percent",
            )

            # If wording says unchanged, the previous value is normally 0.0.
            if previous is None and re.search(
                r"after\s+(?:being|remaining)\s+unchanged", text, flags=re.I
            ):
                previous = 0.0

            records.append(
                Record(
                    indicator="CPI",
                    agency="BLS",
                    release_date=release_date,
                    release_time=release_time,
                    reference_period=reference,
                    actual=actual,
                    previous=previous,
                    revision=None,
                    consensus=None,
                    consensus_source=None,
                    vintage_date=release_date,
                    source="U.S. Bureau of Labor Statistics — CPI News Release Archive",
                    source_url=url,
                )
            )

            # Core CPI: use the exact official sentence rather than deriving it.
            core = extract_number(
                text,
                r"index for all items less food and energy\s+"
                r"(?:rose|increased|advanced|declined|fell)\s+"
                r"([+-]?\d+(?:\.\d+)?)\s+percent",
            )

            if core is not None:
                records.append(
                    Record(
                        indicator="CORE_CPI",
                        agency="BLS",
                        release_date=release_date,
                        release_time=release_time,
                        reference_period=reference,
                        actual=core,
                        previous=None,
                        revision=None,
                        consensus=None,
                        consensus_source=None,
                        vintage_date=release_date,
                        source="U.S. Bureau of Labor Statistics — CPI News Release Archive",
                        source_url=url,
                    )
                )

        except Exception as exc:
            print(f"  CPI SKIP: {url} | {exc}")

    return records


def collect_employment(s: requests.Session) -> list[Record]:
    records: list[Record] = []

    links = archive_links(
        s,
        BLS_EMPSIT_ARCHIVE,
        r"/news\.release/archives/empsit_\d{8}\.(?:htm|pdf)$",
    )

    for url in links:
        try:
            if url.lower().endswith(".pdf"):
                continue

            text = BeautifulSoup(get(s, url).text, "html.parser").get_text(" ", strip=True)

            release_date, release_time = parse_release_datetime(text)
            year = int(release_date[:4])
            if not (START_YEAR <= year <= END_YEAR):
                continue

            # Employment Situation — first sentence normally states the
            # payroll change and unemployment rate.
            ref = month_from_heading(text)
            if not ref:
                # Employment releases use "MONTH YEAR" in the heading.
                m = re.search(
                    r"EMPLOYMENT SITUATION\s*[–-]\s*([A-Z][a-z]+)\s+(\d{4})",
                    text,
                    flags=re.I,
                )
                ref = f"{m.group(1)} {m.group(2)}" if m else None

            if not ref:
                raise ValueError("Employment reference period not found")

            nfp = extract_number(
                text,
                r"payroll employment\s+(?:rose|increased)\s+by\s+([0-9,]+)",
            )
            if nfp is None:
                nfp = extract_number(
                    text,
                    r"nonfarm payroll employment\s+(?:rose|increased)\s+by\s+([0-9,]+)",
                )

            unemployment = extract_number(
                text,
                r"unemployment rate\s+(?:rose|increased|edged up|fell|declined|"
                r"decreased|remained)\s+at\s+([0-9.]+)\s+percent",
            )

            if nfp is None or unemployment is None:
                raise ValueError(
                    f"Could not parse NFP/unemployment (nfp={nfp}, "
                    f"unemployment={unemployment})"
                )

            records.append(
                Record(
                    indicator="NFP",
                    agency="BLS",
                    release_date=release_date,
                    release_time=release_time,
                    reference_period=ref,
                    actual=nfp,
                    previous=None,
                    revision=None,
                    consensus=None,
                    consensus_source=None,
                    vintage_date=release_date,
                    source="U.S. Bureau of Labor Statistics — Employment Situation Archive",
                    source_url=url,
                )
            )

            records.append(
                Record(
                    indicator="UNEMPLOYMENT_RATE",
                    agency="BLS",
                    release_date=release_date,
                    release_time=release_time,
                    reference_period=ref,
                    actual=unemployment,
                    previous=None,
                    revision=None,
                    consensus=None,
                    consensus_source=None,
                    vintage_date=release_date,
                    source="U.S. Bureau of Labor Statistics — Employment Situation Archive",
                    source_url=url,
                )
            )

        except Exception as exc:
            print(f"  EMPSIT SKIP: {url} | {exc}")

    return records


def quality_check(df: pd.DataFrame) -> pd.DataFrame:
    rows = []

    for _, r in df.iterrows():
        issues = []

        if not r["release_date"]:
            issues.append("missing_release_date")
        if not r["release_time"]:
            issues.append("missing_release_time")
        if not r["vintage_date"]:
            issues.append("missing_vintage_date")
        if not r["actual"] == r["actual"]:  # NaN
            issues.append("missing_actual")
        if not r["source_url"]:
            issues.append("missing_source_url")

        try:
            release = pd.Timestamp(r["release_date"]).date()
            vintage = pd.Timestamp(r["vintage_date"]).date()
            if vintage > release:
                issues.append("vintage_after_release")
        except Exception:
            issues.append("invalid_date")

        rows.append(
            {
                "indicator": r["indicator"],
                "release_date": r["release_date"],
                "source_url": r["source_url"],
                "point_in_time_safe": len(issues) == 0,
                "quality_issues": ";".join(issues),
                "historical_consensus_available": bool(
                    pd.notna(r["consensus"]) and r["consensus_source"]
                ),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    print("=" * 72)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1B")
    print("HISTORICAL COLLECTOR v1 — BATCH 1 (2020-2022)")
    print("=" * 72)

    s = session()

    records: list[Record] = []

    print("\nBLS CPI / CORE CPI")
    records.extend(collect_cpi(s))

    print("\nBLS EMPLOYMENT SITUATION")
    records.extend(collect_employment(s))

    # Explicitly do NOT fake unsupported sources.
    print("\nEXTENSIONS NOT ENABLED IN THIS BATCH")
    print("- DOL Initial Jobless Claims: official archive adapter pending")
    print("- ISM Manufacturing PMI: official report adapter pending")
    print("- BEA GDP: vintage-history adapter pending")

    if not records:
        raise RuntimeError(
            "No official BLS historical records were collected. "
            "Do not fabricate input data."
        )

    df = pd.DataFrame([asdict(r) for r in records])

    # Deterministic deduplication.
    df = df.drop_duplicates(
        subset=["indicator", "release_date", "reference_period", "source_url"]
    ).sort_values(
        ["release_date", "indicator"]
    ).reset_index(drop=True)

    quality = quality_check(df)

    df.to_csv(OUTPUT_EVENTS, index=False)
    quality.to_csv(OUTPUT_QUALITY, index=False)

    print("\nSUMMARY")
    print("-" * 72)
    print(f"Records collected:          {len(df)}")
    print(f"PIT safe:                    {quality['point_in_time_safe'].sum()}/{len(quality)}")
    print(
        f"Historical consensus:        "
        f"{quality['historical_consensus_available'].sum()}/{len(quality)}"
    )
    print(f"Indicators:                  {df['indicator'].nunique()}")

    print("\nBY INDICATOR")
    print(df["indicator"].value_counts().sort_index().to_string())

    if not quality["point_in_time_safe"].all():
        print("\nQUALITY GATE: FAIL")
        print(quality.loc[~quality["point_in_time_safe"]].to_string(index=False))
        raise RuntimeError("Historical data quality gate failed.")

    print("\nOUTPUTS")
    print(f"- {OUTPUT_EVENTS}")
    print(f"- {OUTPUT_QUALITY}")
    print("\nPIT QUALITY GATE: PASS")
    print("Research-only. No Decision Engine integration.")


if __name__ == "__main__":
    main()
