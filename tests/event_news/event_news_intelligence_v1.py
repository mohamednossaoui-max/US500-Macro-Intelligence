#!/usr/bin/env python3
"""
Event / News Intelligence v1
Research-only. No trading signals, forecasts, or Decision Engine integration.

Sources:
- GDELT DOC 2.0: rolling news coverage, max 3 months via API.
- SEC EDGAR submissions API: official corporate filing events for a small US500 research universe.

The module intentionally does NOT claim causal, predictive, or trading usefulness.
"""

from __future__ import annotations
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

# Research universe: liquid, broad-market representatives rather than a claim
# about the full historical S&P 500 membership.
SEC_UNIVERSE = {
    "MSFT": "0000789019",
    "AAPL": "0000320193",
    "NVDA": "0001045810",
    "AMZN": "0001018724",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "JPM": "0000019617",
    "JNJ": "0000200406",
    "XOM": "0000034088",
    "WMT": "0000104169",
}

GDELT_QUERIES = {
    "fed": '("Federal Reserve" OR Fed OR FOMC OR Powell OR "interest rates")',
    "inflation": '(inflation OR CPI OR PPI OR "consumer prices" OR "producer prices")',
    "labor": '("nonfarm payrolls" OR jobs OR employment OR unemployment OR "jobless claims")',
    "growth": '(GDP OR recession OR "economic growth" OR PMI OR "ISM")',
    "market": '("S&P 500" OR SP500 OR equities OR stocks OR volatility)',
    "geopolitical": '(war OR sanctions OR tariff OR tariffs OR conflict OR ceasefire)',
    "energy": '(oil OR crude OR OPEC OR gasoline OR energy)',
}

def http_json(url: str, headers: dict | None = None) -> dict:
    h = {"User-Agent": "US500-Macro-Intelligence/1.0 research-only"}
    if headers:
        h.update(headers)
    req = Request(url, headers=h)
    with urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def fetch_gdelt(query_name: str, query: str, maxrecords: int = 250) -> list[dict]:
    params = {
        "query": query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": maxrecords,
        "timespan": "3months",
        "sort": "datedesc",
    }
    data = http_json(GDELT_URL + "?" + urlencode(params))
    return data.get("articles", [])

def normalize_gdelt(rows: list[dict], topic: str) -> list[dict]:
    out = []
    for r in rows:
        url = str(r.get("url") or "").strip()
        title = str(r.get("title") or "").strip()
        published = str(r.get("seendate") or "").strip()
        if not (url and published):
            continue
        try:
            dt = pd.to_datetime(published, format="%Y%m%dT%H%M%SZ", utc=True)
        except Exception:
            dt = pd.to_datetime(published, utc=True, errors="coerce")
        if pd.isna(dt):
            continue
        article_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:20]
        out.append({
            "event_id": article_id,
            "source_type": "GDELT",
            "source": str(r.get("domain") or ""),
            "topic": topic,
            "published_at": dt.isoformat(),
            "availability_date": dt.date().isoformat(),
            "title": title,
            "url": url,
            "language": str(r.get("language") or ""),
            "country": str(r.get("sourcecountry") or ""),
            "tone": pd.to_numeric(r.get("tone"), errors="coerce"),
            "point_in_time_safe": True,
        })
    return out

def fetch_sec(ticker: str, cik: str) -> list[dict]:
    data = http_json(SEC_SUBMISSIONS.format(cik=cik), {"Accept-Encoding": "gzip"})
    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    filing_dates = recent.get("filingDate", [])
    accession = recent.get("accessionNumber", [])
    primary = recent.get("primaryDocument", [])
    acceptance = recent.get("acceptanceDateTime", [])
    out = []
    for i, form in enumerate(forms):
        if form not in {"8-K", "10-Q", "10-K", "10-Q/A", "10-K/A"}:
            continue
        acc = accession[i] if i < len(accession) else ""
        acc_clean = acc.replace("-", "")
        doc = primary[i] if i < len(primary) else ""
        cik_int = str(int(cik))
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_int}/{acc_clean}/{doc}" if doc else ""
        accepted = acceptance[i] if i < len(acceptance) else ""
        availability = accepted[:10] if accepted else (filing_dates[i] if i < len(filing_dates) else "")
        event_id = hashlib.sha256((ticker + acc + form).encode()).hexdigest()[:20]
        out.append({
            "event_id": event_id,
            "source_type": "SEC",
            "source": "SEC EDGAR",
            "topic": "corporate_filing",
            "published_at": accepted,
            "availability_date": availability,
            "title": f"{ticker} {form}",
            "url": url,
            "language": "en",
            "country": "US",
            "tone": None,
            "ticker": ticker,
            "form": form,
            "point_in_time_safe": bool(availability),
        })
    return out

def validate(df: pd.DataFrame, output: Path) -> dict:
    errors, warnings = [], []
    required = ["event_id","source_type","source","topic","published_at","availability_date","title","url"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        errors.append({"check":"required_columns","pass":False,"detail":str(missing)})
    else:
        errors.append({"check":"required_columns","pass":True,"detail":""})

    unique = int(df["event_id"].nunique()) == len(df) if len(df) else False
    errors.append({"check":"unique_event_ids","pass":unique,"detail":f"rows={len(df)}"})

    dates_ok = True
    if len(df):
        pub = pd.to_datetime(df["published_at"], utc=True, errors="coerce")
        dates_ok = bool(pub.notna().all())
    errors.append({"check":"published_timestamps_parse","pass":dates_ok,"detail":""})

    pit = bool(df["point_in_time_safe"].fillna(False).all()) if len(df) else False
    errors.append({"check":"point_in_time_safe","pass":pit,"detail":""})

    urls = bool(df["url"].astype(str).str.startswith(("http://","https://")).all()) if len(df) else False
    errors.append({"check":"urls_valid","pass":urls,"detail":""})

    source_ok = bool(set(df["source_type"].dropna().unique()).issubset({"GDELT","SEC"})) if len(df) else True
    errors.append({"check":"known_sources_only","pass":source_ok,"detail":""})

    if len(df) == 0:
        warnings.append("No events returned. This is a data-availability condition, not evidence of no news.")
    if "GDELT" in set(df.get("source_type", pd.Series(dtype=str))):
        warnings.append("GDELT coverage is rolling and limited to the API's documented historical window; it is not a full historical archive.")
    warnings.append("SEC universe is a fixed research sample, not a point-in-time reconstruction of all S&P 500 constituents.")

    passed = all(e["pass"] for e in errors)
    report = {
        "validator": "Event / News Intelligence v1",
        "status": "PASS" if passed else "FAIL",
        "validation_pass": passed,
        "errors": [e for e in errors if not e["pass"]],
        "warnings": warnings,
        "rows": int(len(df)),
        "date_start": str(df["availability_date"].min()) if len(df) else None,
        "date_end": str(df["availability_date"].max()) if len(df) else None,
        "source_counts": df["source_type"].value_counts().to_dict() if len(df) else {},
        "topic_counts": df["topic"].value_counts().to_dict() if len(df) else {},
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "point_in_time_reconstructed": False,
        "interpretation": "PASS is structural/data-quality validation only. News coverage, tone, and filing frequency are descriptive and do not establish causality, predictiveness, trading usefulness, or preference.",
        "checks": errors,
    }
    (output / "event_news_validation_v1.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="event_news_intelligence_v1")
    args = ap.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)

    records = []
    for name, query in GDELT_QUERIES.items():
        try:
            records.extend(normalize_gdelt(fetch_gdelt(name, query), name))
        except Exception as exc:
            print(f"GDELT query {name} failed: {exc}")

    for ticker, cik in SEC_UNIVERSE.items():
        try:
            records.extend(fetch_sec(ticker, cik))
            time.sleep(0.2)
        except Exception as exc:
            print(f"SEC {ticker} failed: {exc}")

    df = pd.DataFrame(records)
    if len(df):
        df["event_id"] = df["event_id"].astype(str)
        df = df.drop_duplicates("event_id").sort_values(["availability_date","published_at"], kind="stable")
        df["research_only"] = True
        df["decision_engine_ready"] = False
        df["trading_signal"] = False
        df["forecast"] = False
        df["pit_perfect"] = False
        df["point_in_time_reconstructed"] = False
    else:
        df = pd.DataFrame(columns=[
            "event_id","source_type","source","topic","published_at","availability_date",
            "title","url","language","country","tone","ticker","form",
            "point_in_time_safe","research_only","decision_engine_ready",
            "trading_signal","forecast","pit_perfect","point_in_time_reconstructed"
        ])

    df.to_csv(output / "event_news_research_v1.csv", index=False)
    summary = {
        "rows": int(len(df)),
        "sources": df["source_type"].value_counts().to_dict() if len(df) else {},
        "topics": df["topic"].value_counts().to_dict() if len(df) else {},
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
    }
    (output / "event_news_research_summary_v1.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    report = validate(df, output)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["validation_pass"] else 1)

if __name__ == "__main__":
    main()
