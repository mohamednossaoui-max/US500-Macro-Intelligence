"""PIT-safe historical PCE/Core-PCE release backfill from BEA news releases.

The collector reads the archived *release pages*, not revised time-series APIs.
Each row is dated by the BEA embargo/release date and therefore represents
information that was actually published at that point in time.

Research-only. No consensus is fabricated. Ambiguous pages fail closed.
"""
from __future__ import annotations

import argparse
import calendar
import re
from pathlib import Path
from typing import Iterable

import pandas as pd
import requests
from bs4 import BeautifulSoup

EVENTS = Path("public_data/economic_historical_events_v1.csv")
QUALITY = Path("public_data/economic_historical_quality_v1.csv")
BASE = "https://www.bea.gov/news/{year}/personal-income-and-outlays-{month}-{year}"
UA = "US500-Macro-Intelligence/2.0 research collector"

MONTHS = {m.lower(): i for i, m in enumerate(calendar.month_name) if m}


def month_iter(start: str, end: str) -> Iterable[tuple[int, int]]:
    s = pd.Period(start, freq="M")
    e = pd.Period(end, freq="M")
    for p in pd.period_range(s, e, freq="M"):
        yield p.year, p.month


def _number(direction: str, token: str) -> float | None:
    token = token.strip().lower()
    # "less than 0.1" is intentionally not converted to a fabricated point estimate.
    if "less than" in token:
        return None
    m = re.search(r"\d+(?:\.\d+)?", token)
    if not m:
        return None
    value = float(m.group(0))
    return -value if direction.lower() == "decreased" else value


def parse_bea_release(html: str, url: str) -> list[dict]:
    text = " ".join(BeautifulSoup(html, "html.parser").stripped_strings)

    title = re.search(r"Personal Income and Outlays,\s+([A-Za-z]+)\s+(\d{4})", text, re.I)
    if not title:
        raise ValueError("reference month/year not found")
    ref_month, ref_year = title.group(1).title(), int(title.group(2))
    if ref_month.lower() not in MONTHS:
        raise ValueError("invalid reference month")

    # Prefer the embargo line because it is the actual public release timestamp.
    dm = re.search(
        r"EMBARGOED UNTIL RELEASE AT\s+(\d{1,2}:\d{2})\s+(a\.m\.|p\.m\.)\s+([A-Z]{3}),?\s+"
        r"(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
        r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", text, re.I)
    if not dm:
        raise ValueError("BEA release timestamp not found")
    release_date = pd.Timestamp(f"{dm.group(4)} {dm.group(5)} {dm.group(6)}").strftime("%Y-%m-%d")
    release_time = f"{dm.group(1)} {dm.group(3).upper()}"

    # Restrict matching to the canonical BEA wording.  This deliberately fails
    # closed if the release format changes.
    headline = re.search(
        rf"From the preceding month, the PCE price index for {ref_month}\s+(increased|decreased)\s+([^.%]*?\d+(?:\.\d+)?|less than\s+0\.1)\s+percent",
        text, re.I,
    )
    if not headline:
        # Some releases omit "for <month>" in the lead paragraph.
        headline = re.search(
            r"From the preceding month, the PCE price index\s+(?:for\s+[A-Za-z]+\s+)?(increased|decreased)\s+([^.%]*?\d+(?:\.\d+)?|less than\s+0\.1)\s+percent",
            text, re.I,
        )
    core = re.search(
        r"Excluding food and energy, the PCE price index\s+(?:also\s+)?(increased|decreased)\s+([^.%]*?\d+(?:\.\d+)?|less than\s+0\.1)\s+percent",
        text, re.I,
    )
    if not headline or not core:
        raise ValueError("PCE/core-PCE monthly changes not found")

    pce = _number(headline.group(1), headline.group(2))
    core_pce = _number(core.group(1), core.group(2))
    if pce is None or core_pce is None:
        raise ValueError("ambiguous sub-0.1 change; fail closed")

    common = dict(
        agency="BEA", release_date=release_date, release_time=release_time,
        reference_period=f"{ref_month} {ref_year}", previous=None, revision=None,
        consensus=None, consensus_source=None, vintage_date=release_date,
        source="U.S. Bureau of Economic Analysis — Personal Income and Outlays",
        source_url=url, notes="Original BEA Personal Income and Outlays release; monthly change as published.",
    )
    return [
        dict(indicator="PCE_PRICE_INDEX", actual=pce, mom=pce, **common),
        dict(indicator="CORE_PCE", actual=core_pce, mom=core_pce, **common),
    ]


def fetch_release(year: int, month: int, session: requests.Session) -> list[dict]:
    name = calendar.month_name[month].lower()
    url = BASE.format(year=year, month=name)
    r = session.get(url, timeout=25, headers={"User-Agent": UA})
    if r.status_code == 404:
        return []
    r.raise_for_status()
    return parse_bea_release(r.text, url)


def backfill(start="2024-01", end="2026-07", min_months=18, events_path=EVENTS, quality_path=QUALITY):
    events_path, quality_path = Path(events_path), Path(quality_path)
    events = pd.read_csv(events_path)
    quality = pd.read_csv(quality_path)
    existing = set(zip(events.indicator.astype(str), events.release_date.astype(str), events.reference_period.astype(str)))
    q_existing = set(zip(quality.indicator.astype(str), quality.release_date.astype(str), quality.reference_period.astype(str)))

    session = requests.Session()
    rows, qrows, successful_months, skipped = [], [], 0, []
    for year, month in month_iter(start, end):
        try:
            parsed = fetch_release(year, month, session)
        except Exception as exc:
            skipped.append(f"{year}-{month:02d}: {exc}")
            continue
        if not parsed:
            skipped.append(f"{year}-{month:02d}: no archived page")
            continue
        successful_months += 1
        for row in parsed:
            key = (row["indicator"], row["release_date"], row["reference_period"])
            if key not in existing:
                rows.append(row); existing.add(key)
            if key not in q_existing:
                qrows.append({
                    "record_id": "|".join(key), "indicator": row["indicator"], "agency": "BEA",
                    "release_date": row["release_date"], "reference_period": row["reference_period"],
                    "point_in_time_safe": True, "quality_issues": "",
                    "historical_consensus_available": False,
                }); q_existing.add(key)

    if successful_months < min_months:
        raise RuntimeError(f"BEA coverage gate failed: only {successful_months} months parsed; required {min_months}. Skipped={skipped[:8]}")

    if rows:
        events = pd.concat([events, pd.DataFrame(rows)], ignore_index=True, sort=False)
    if qrows:
        quality = pd.concat([quality, pd.DataFrame(qrows)], ignore_index=True, sort=False)

    rd = pd.to_datetime(events.release_date, errors="raise")
    vd = pd.to_datetime(events.vintage_date, errors="raise")
    if not (vd <= rd).all():
        raise AssertionError("PIT temporal order failed")
    if not quality.point_in_time_safe.fillna(False).astype(bool).all():
        raise AssertionError("PIT quality gate failed")
    if quality.historical_consensus_available.fillna(False).astype(bool).any():
        raise AssertionError("unsupported historical consensus detected")

    events = events.assign(_rd=rd).sort_values(["_rd", "indicator", "reference_period"], kind="mergesort").drop(columns="_rd")
    events.to_csv(events_path, index=False)
    quality.to_csv(quality_path, index=False)
    return {"months_parsed": successful_months, "rows_added": len(rows), "quality_rows_added": len(qrows), "skipped": skipped}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", default="2024-01")
    p.add_argument("--end", default="2026-07")
    p.add_argument("--min-months", type=int, default=18)
    a = p.parse_args()
    result = backfill(a.start, a.end, a.min_months)
    print("PCE HISTORICAL PIT BACKFILL: PASS")
    print(result)

if __name__ == "__main__":
    main()
