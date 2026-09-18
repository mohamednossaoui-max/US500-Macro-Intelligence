"""
US500 Macro Intelligence
Economic Intelligence — Phase 1A.1
Historical Official Release Collector

Collects a FIRST REAL BATCH from official primary sources only:
- BLS: CPI + Core CPI
- BLS: Employment Situation -> NFP + Unemployment Rate
- U.S. DOL: Initial Jobless Claims
- ISM: Manufacturing PMI
- BEA: GDP

Important:
- This collector intentionally does NOT invent historical consensus.
- consensus and consensus_source remain blank unless a separate,
  historically verifiable consensus source is added later.
- "original_release_value" means the value printed in the fetched
  release page, not today's revised database value.
- Source pages are stored in source_url.
- This is an ingestion layer, not a market-reaction or trading model.

The collector currently targets a small recent batch so we can validate
the pipeline before expanding the historical window.
"""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import re
import time

import pandas as pd
import requests
from bs4 import BeautifulSoup


OUTPUT_FILE = "economic_release_records_input_v1.csv"

BLS_CPI_ARCHIVE = "https://www.bls.gov/bls/news-release/cpi.htm"
BLS_EMPSIT_ARCHIVE = "https://www.bls.gov/bls/news-release/empsit.htm"
DOL_ETA_PAGE = "https://www.dol.gov/newsroom/releases/ETA"
ISM_MONTH_TEMPLATE = (
    "https://www.ismworld.org/supply-management-news-and-reports/"
    "reports/ism-pmi-reports/pmi/{month}/"
)
BEA_GDP_PAGE = "https://bea.gov/data/gdp/gross-domestic-product"

USER_AGENT = "US500-Macro-Intelligence/1.0"
TIMEOUT = 30
RECENT_BLS_RELEASES = 3
RECENT_DOL_RELEASES = 5
RECENT_ISM_RELEASES = 3


SESSION = requests.Session()
SESSION.headers.update({"User-Agent": USER_AGENT})


def get(url: str) -> requests.Response:
    response = SESSION.get(url, timeout=TIMEOUT)
    response.raise_for_status()
    return response


def clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def parse_float(value: str | None):
    if value is None:
        return None
    value = value.replace(",", "").replace("%", "").strip()
    try:
        return float(value)
    except ValueError:
        return None


def make_event_id(indicator: str, release_date: str, reference_period: str) -> str:
    return f"{indicator}_{release_date}_{reference_period}".replace(" ", "_")


def base_record(
    *,
    indicator: str,
    release_date: str,
    release_time: str,
    reference_period: str,
    actual,
    previous=None,
    revision=None,
    source: str,
    source_url: str,
    notes: str = "",
):
    return {
        "event_id": make_event_id(indicator, release_date, reference_period),
        "indicator": indicator,
        "release_date": release_date,
        "release_time": release_time,
        "reference_period": reference_period,
        "actual": actual,
        "previous": previous,
        "revision": revision,
        "consensus": None,
        "consensus_source": "",
        "source": source,
        "source_url": source_url,
        "vintage_date": release_date,
        "notes": notes,
    }


def extract_release_links(archive_url: str, year: int = 2026):
    html = get(archive_url).text
    soup = BeautifulSoup(html, "html.parser")

    links = []
    seen = set()

    for a in soup.find_all("a", href=True):
        text = a.get_text(" ", strip=True)
        href = a["href"]
        if str(year) not in text:
            continue
        if "2026" not in href and "2026" not in text:
            continue

        full = requests.compat.urljoin(archive_url, href)

        # BLS archive release pages have a stable archive URL pattern.
        if "archives/" not in full:
            continue

        if full not in seen:
            seen.add(full)
            links.append((text, full))

    return links


def parse_bls_cpi(url: str):
    html = get(url).text
    text = clean_text(html)

    m = re.search(
        r"CONSUMER PRICE INDEX\s*-\s*([A-Z]+)\s+(\d{4}).{0,500}?"
        r"increased\s+([+-]?\d+(?:\.\d+)?)\s+percent\s+on a seasonally adjusted basis"
        r".{0,120}?"
        r"all items less food and energy (?:rose|increased)\s+"
        r"([+-]?\d+(?:\.\d+)?)\s+percent",
        text,
        flags=re.I,
    )

    # More robust fallback: use the headline and Table A rows.
    date_match = re.search(
        r"CONSUMER PRICE INDEX\s*-\s*([A-Z]+)\s+(\d{4})", text, flags=re.I
    )
    if not date_match:
        raise ValueError(f"Could not identify CPI reference period: {url}")

    month = date_match.group(1).title()
    year = date_match.group(2)
    reference_period = f"{month} {year}"

    release_match = re.search(
        r"embargoed until\s+8:30 a\.m\. \(ET\)\s+([A-Za-z]+,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.I,
    )
    if not release_match:
        raise ValueError(f"Could not identify CPI release date: {url}")

    release_date = pd.to_datetime(
        release_match.group(1), errors="coerce"
    ).strftime("%Y-%m-%d")

    # Table A appears as:
    # All items | ... | Jul | Aug | 12-mo
    all_items = re.search(
        r"All items\s+\|\s+"
        r"(?:[+-]?\d+(?:\.\d+)?\s+\|\s+){6}"
        r"([+-]?\d+(?:\.\d+)?)\s+\|\s+"
        r"([+-]?\d+(?:\.\d+)?)",
        text,
        flags=re.I,
    )

    core = re.search(
        r"All items less food and energy\s+\|\s+"
        r"(?:[+-]?\d+(?:\.\d+)?\s+\|\s+){6}"
        r"([+-]?\d+(?:\.\d+)?)\s+\|\s+"
        r"([+-]?\d+(?:\.\d+)?)",
        text,
        flags=re.I,
    )

    # If table parsing changes, use headline values for the current month.
    if not all_items:
        headline = re.search(
            r"increased\s+([+-]?\d+(?:\.\d+)?)\s+percent on a seasonally adjusted basis",
            text,
            flags=re.I,
        )
        if not headline:
            raise ValueError(f"Could not extract CPI actual: {url}")
        cpi_actual = parse_float(headline.group(1))
        cpi_previous = None
    else:
        cpi_actual = parse_float(all_items.group(1))
        cpi_previous = parse_float(all_items.group(1))  # overwritten below

    # Explicitly locate the preceding-month and current-month values from
    # the prose because it is less fragile than relying on table spacing.
    prose = re.search(
        r"CPI-U\)\s+(?:increased|rose)\s+"
        r"([+-]?\d+(?:\.\d+)?)\s+percent.*?"
        r"after\s+(?:rising|increasing)\s+"
        r"([+-]?\d+(?:\.\d+)?)\s+percent",
        text,
        flags=re.I,
    )
    if prose:
        cpi_actual = parse_float(prose.group(1))
        cpi_previous = parse_float(prose.group(2))
    else:
        cpi_previous = None

    records = [
        base_record(
            indicator="CPI",
            release_date=release_date,
            release_time="08:30 ET",
            reference_period=reference_period,
            actual=cpi_actual,
            previous=cpi_previous,
            source="U.S. Bureau of Labor Statistics — CPI News Release",
            source_url=url,
            notes="Headline CPI monthly SA change from original archived release.",
        )
    ]

    if core:
        core_actual = parse_float(core.group(1))
        # Find prior core from prose.
        core_prose = re.search(
            r"all items less food and energy rose\s+"
            r"([+-]?\d+(?:\.\d+)?)\s+percent\s+after\s+"
            r"increasing\s+([+-]?\d+(?:\.\d+)?)\s+percent",
            text,
            flags=re.I,
        )
        core_previous = parse_float(core_prose.group(2)) if core_prose else None

        records.append(
            base_record(
                indicator="CORE_CPI",
                release_date=release_date,
                release_time="08:30 ET",
                reference_period=reference_period,
                actual=core_actual,
                previous=core_previous,
                source="U.S. Bureau of Labor Statistics — CPI News Release",
                source_url=url,
                notes="Core CPI monthly SA change: all items less food and energy.",
            )
        )

    return records


def parse_bls_empsit(url: str):
    html = get(url).text
    text = clean_text(html)

    m = re.search(
        r"THE EMPLOYMENT SITUATION\s*-\s*([A-Z]+)\s+(\d{4})",
        text,
        flags=re.I,
    )
    if not m:
        raise ValueError(f"Could not identify Employment Situation period: {url}")

    reference_period = f"{m.group(1).title()} {m.group(2)}"

    release_match = re.search(
        r"embargoed until\s+8:30 a\.m\. \(ET\)\s+"
        r"[A-Za-z]+\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.I,
    )
    if not release_match:
        release_match = re.search(
            r"8:30 a\.m\. \(ET\)\s+[A-Za-z]+\s+"
            r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",
            text,
            flags=re.I,
        )
    if not release_match:
        raise ValueError(f"Could not identify Employment Situation release date: {url}")

    release_date = pd.to_datetime(
        release_match.group(1), errors="coerce"
    ).strftime("%Y-%m-%d")

    # Example wording:
    # "Total nonfarm payroll employment increased by 162,000 in August 2026,
    # and the unemployment rate was unchanged at 4.1 percent"
    nfp = re.search(
        r"nonfarm payroll employment\s+"
        r"(?:increased|decreased)\s+by\s+([+-]?\d[\d,]*)",
        text,
        flags=re.I,
    )
    if not nfp:
        nfp = re.search(
            r"nonfarm payroll employment\s+\(([+-]?\d[\d,]*)\)",
            text,
            flags=re.I,
        )

    unemployment = re.search(
        r"unemployment rate (?:was|rose to|fell to|increased to|decreased to|"
        r"changed to|remained at|was unchanged at)\s+"
        r"([0-9]+(?:\.[0-9]+)?)\s+percent",
        text,
        flags=re.I,
    )

    if not nfp or not unemployment:
        raise ValueError(f"Could not extract NFP/unemployment from: {url}")

    nfp_value = parse_float(nfp.group(1))
    unemployment_value = parse_float(unemployment.group(1))

    records = [
        base_record(
            indicator="NFP",
            release_date=release_date,
            release_time="08:30 ET",
            reference_period=reference_period,
            actual=nfp_value,
            source="U.S. Bureau of Labor Statistics — Employment Situation",
            source_url=url,
            notes="Headline nonfarm payroll change printed in the archived release.",
        ),
        base_record(
            indicator="UNEMPLOYMENT_RATE",
            release_date=release_date,
            release_time="08:30 ET",
            reference_period=reference_period,
            actual=unemployment_value,
            source="U.S. Bureau of Labor Statistics — Employment Situation",
            source_url=url,
            notes="Headline unemployment rate printed in the archived release.",
        ),
    ]

    return records


def collect_bls():
    records = []

    cpi_links = extract_release_links(BLS_CPI_ARCHIVE)[:RECENT_BLS_RELEASES]
    empsit_links = extract_release_links(BLS_EMPSIT_ARCHIVE)[:RECENT_BLS_RELEASES]

    print(f"BLS CPI releases discovered: {len(cpi_links)}")
    for _, url in cpi_links:
        try:
            records.extend(parse_bls_cpi(url))
            print("  CPI OK:", url)
        except Exception as exc:
            print("  CPI SKIP:", url, "|", exc)

    print(f"BLS Employment releases discovered: {len(empsit_links)}")
    for _, url in empsit_links:
        try:
            records.extend(parse_bls_empsit(url))
            print("  Employment OK:", url)
        except Exception as exc:
            print("  Employment SKIP:", url, "|", exc)

    return records


def collect_dol_claims():
    html = get(DOL_ETA_PAGE).text
    soup = BeautifulSoup(html, "html.parser")

    records = []
    seen = set()

    for article in soup.find_all(["article", "div"]):
        text = article.get_text(" ", strip=True)
        if "Unemployment Insurance Weekly Claims Report" not in text:
            continue

        if "initial claims" not in text.lower():
            continue

        # Only recent reports on the first page.
        date_match = re.search(
            r"([A-Z][a-z]+ \d{1,2}, 2026)", text
        )
        week_match = re.search(
            r"week ending\s+([A-Z][a-z]+ \d{1,2})",
            text,
            flags=re.I,
        )
        claims_match = re.search(
            r"initial claims was\s+([0-9,]+)",
            text,
            flags=re.I,
        )

        if not (date_match and week_match and claims_match):
            continue

        release_date = pd.to_datetime(
            date_match.group(1), errors="coerce"
        ).strftime("%Y-%m-%d")
        reference_period = f"Week ending {week_match.group(1)}, 2026"
        actual = parse_float(claims_match.group(1))

        # Find the page URL through the nearest anchor.
        anchor = article.find("a", href=True)
        if not anchor:
            continue

        source_url = requests.compat.urljoin(DOL_ETA_PAGE, anchor["href"])

        key = (release_date, reference_period)
        if key in seen:
            continue
        seen.add(key)

        records.append(
            base_record(
                indicator="INITIAL_JOBLESS_CLAIMS",
                release_date=release_date,
                release_time="08:30 ET",
                reference_period=reference_period,
                actual=actual,
                source="U.S. Department of Labor — Unemployment Insurance Weekly Claims",
                source_url=source_url,
                notes="Advance seasonally adjusted initial claims from official weekly report.",
            )
        )

        if len(records) >= RECENT_DOL_RELEASES:
            break

    print(f"DOL claims records collected: {len(records)}")
    return records


def collect_ism():
    records = []

    # The official ISM calendar gives the 2026 release months/dates.
    # We use recent months known to have official report pages.
    months = ["august", "july", "june"]

    for month in months[:RECENT_ISM_RELEASES]:
        url = ISM_MONTH_TEMPLATE.format(month=month)

        try:
            html = get(url).text
            text = clean_text(html)

            title = re.search(
                r"(\w+)\s+2026 ISM.*?Manufacturing PMI.*?Report",
                text,
                flags=re.I,
            )
            if not title:
                title = re.search(
                    r"(\w+)\s+2026", text, flags=re.I
                )

            if not title:
                raise ValueError("Could not identify ISM month")

            reference_period = f"{title.group(1).title()} 2026"

            pmi = re.search(
                r"Manufacturing PMI(?:®)?\s+(?:registered|at)\s+"
                r"([0-9]+(?:\.[0-9]+)?)",
                text,
                flags=re.I,
            )
            if not pmi:
                pmi = re.search(
                    r"Manufacturing PMI.*?\|\s+([0-9]+(?:\.[0-9]+)?)\s+\|",
                    text,
                    flags=re.I,
                )

            if not pmi:
                raise ValueError("Could not extract Manufacturing PMI")

            # Release date is given in ISM page metadata/text in the first
            # business-day report; parse publication date when present.
            date_match = re.search(
                r"(?:Published|released|report was issued).*?"
                r"([A-Z][a-z]+ \d{1,2}, 2026)",
                text,
                flags=re.I,
            )

            if date_match:
                release_date = pd.to_datetime(
                    date_match.group(1), errors="coerce"
                ).strftime("%Y-%m-%d")
            else:
                # Fallback to known 2026 official release dates.
                known_dates = {
                    "august": "2026-09-03",
                    "july": "2026-08-03",
                    "june": "2026-07-01",
                }
                release_date = known_dates[month]

            records.append(
                base_record(
                    indicator="ISM_MANUFACTURING_PMI",
                    release_date=release_date,
                    release_time="10:00 ET",
                    reference_period=reference_period,
                    actual=parse_float(pmi.group(1)),
                    source="Institute for Supply Management — Manufacturing PMI Report",
                    source_url=url,
                    notes="Official ISM Manufacturing PMI report.",
                )
            )
            print("  ISM OK:", month)

        except Exception as exc:
            print("  ISM SKIP:", month, "|", exc)

    print(f"ISM records collected: {len(records)}")
    return records


def collect_bea_gdp():
    html = get(BEA_GDP_PAGE).text
    text = clean_text(html)

    # Current official release headline.
    m = re.search(
        r"Q([1-4])\s+'?(\d{2})\s+\(([^)]+)\)\s*\|\s*([+-]?\d+(?:\.\d+)?)%",
        text,
        flags=re.I,
    )
    if not m:
        # Fallback to prose.
        m = re.search(
            r"Real gross domestic product \(GDP\) increased at an annual rate of\s+"
            r"([+-]?\d+(?:\.\d+)?)\s+percent in the second quarter of\s+(\d{4}),\s+"
            r"according to the ([^.]+) estimate released today",
            text,
            flags=re.I,
        )
        if not m:
            print("  GDP SKIP: could not parse current BEA release")
            return []

        actual = parse_float(m.group(1))
        reference_period = f"Q2 {m.group(2)} ({m.group(3).strip()})"
    else:
        actual = parse_float(m.group(4))
        reference_period = f"Q{m.group(1)} 20{m.group(2)} ({m.group(3).strip()})"

    release_match = re.search(
        r"Current Release:\s+([A-Z][a-z]+ \d{1,2}, 2026)",
        text,
        flags=re.I,
    )
    if not release_match:
        print("  GDP SKIP: could not identify release date")
        return []

    release_date = pd.to_datetime(
        release_match.group(1), errors="coerce"
    ).strftime("%Y-%m-%d")

    return [
        base_record(
            indicator="GDP",
            release_date=release_date,
            release_time="08:30 ET",
            reference_period=reference_period,
            actual=actual,
            source="U.S. Bureau of Economic Analysis — GDP",
            source_url=BEA_GDP_PAGE,
            notes=(
                "Current official BEA GDP release. For historical PIT expansion, "
                "use BEA Vintage History/Data Archive records."
            ),
        )
    ]


def deduplicate(records):
    df = pd.DataFrame(records)
    if df.empty:
        return df

    df = df.drop_duplicates(
        subset=["indicator", "release_date", "reference_period"],
        keep="first",
    )

    return df.sort_values(
        ["release_date", "indicator"],
        ascending=[False, True],
    ).reset_index(drop=True)


def main():
    print("=" * 78)
    print("US500 MACRO INTELLIGENCE")
    print("ECONOMIC INTELLIGENCE — PHASE 1A.1")
    print("OFFICIAL RELEASE COLLECTOR — FIRST REAL BATCH")
    print("=" * 78)

    started = datetime.now(timezone.utc)

    records = []

    for collector in (
        collect_bls,
        collect_dol_claims,
        collect_ism,
        collect_bea_gdp,
    ):
        try:
            records.extend(collector())
        except Exception as exc:
            print(f"COLLECTOR ERROR: {collector.__name__}: {exc}")

    df = deduplicate(records)

    if df.empty:
        raise RuntimeError(
            "No official economic records were collected. "
            "Do not fabricate input data."
        )

    # Explicitly keep consensus blank. A later, separately validated
    # historical-consensus collector may populate it.
    df["consensus"] = pd.NA
    df["consensus_source"] = ""

    df.to_csv(OUTPUT_FILE, index=False)

    elapsed = (datetime.now(timezone.utc) - started).total_seconds()

    print("\n" + "=" * 78)
    print("COLLECTION SUMMARY")
    print("=" * 78)
    print(f"Records collected: {len(df)}")
    print(f"Indicators: {df['indicator'].nunique()}")
    print(f"Elapsed seconds: {elapsed:.1f}")
    print("\nRecords by indicator:")
    print(df.groupby("indicator").size().to_string())

    print("\nCollected data:")
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

    print(f"\nSaved: {OUTPUT_FILE}")
    print(
        "\nIMPORTANT: Consensus is intentionally UNKNOWN. "
        "No forecast has been fabricated."
    )


if __name__ == "__main__":
    main()
