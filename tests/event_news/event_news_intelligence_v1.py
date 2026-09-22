#!/usr/bin/env python3

"""
US500 Macro Intelligence
Event / News Intelligence v2

Research-only.
No trading signals.
No forecasting.
No Decision Engine integration.
No execution.

Architecture:

1. GDELT DOC 2.0
   - ONE combined query
   - limited retries
   - fast failure on persistent rate limiting

2. Official U.S. government RSS fallback
   - Federal Reserve
   - BLS Employment
   - BLS CPI
   - BLS PPI
   - BLS Productivity

3. SEC EDGAR
   - supplementary only
   - skipped if SEC_USER_AGENT is missing
   - never allowed to invalidate the news dataset

The objective is robust descriptive event/news collection,
not prediction or trading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


# ============================================================
# CONFIGURATION
# ============================================================

VERSION = "2.0"

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"

HTTP_TIMEOUT_SECONDS = 25

# GDELT:
# Keep this intentionally small.
# The previous version spent ~10 minutes retrying 7 queries.
GDELT_RETRIES = 3
GDELT_BACKOFF_SECONDS = 5.0
GDELT_MAX_BACKOFF_SECONDS = 30.0

# One combined request instead of 7 separate topic requests.
GDELT_MAX_RECORDS = 250
GDELT_TIMESPAN = "3days"

# Official RSS:
RSS_TIMEOUT_SECONDS = 20
RSS_RETRIES = 2
RSS_PACING_SECONDS = 0.75

# SEC:
SEC_RETRIES = 2
SEC_PACING_SECONDS = 0.75

# Validation thresholds.
MIN_TOTAL_ROWS = 10
MIN_CORE_TOPIC_FAMILIES = 3
MIN_GDELT_TITLE_RELEVANCE = 0.30

# ============================================================
# GDELT QUERY
# ============================================================

GDELT_COMBINED_QUERY = (
    '("Federal Reserve" OR FOMC OR Powell '
    'OR CPI OR PPI OR inflation '
    'OR "nonfarm payrolls" OR unemployment OR "jobless claims" '
    'OR GDP OR PMI OR ISM OR recession '
    'OR "S&P 500" OR SP500 OR equities '
    'OR tariff OR tariffs OR sanctions OR "trade war" '
    'OR oil OR crude OR OPEC OR energy) '
    '(US OR U.S. OR "United States" OR America)'
)


# ============================================================
# OFFICIAL RSS SOURCES
# ============================================================

OFFICIAL_RSS_FEEDS = {
    "fed_monetary_policy": {
        "url": "https://www.federalreserve.gov/feeds/press_monetary.xml",
        "default_topic": "fed",
        "source": "Federal Reserve",
    },
    "fed_all_press": {
        "url": "https://www.federalreserve.gov/feeds/press_all.xml",
        "default_topic": "fed",
        "source": "Federal Reserve",
    },
    "bls_employment": {
        "url": "https://www.bls.gov/feed/empsit.rss",
        "default_topic": "labor",
        "source": "BLS",
    },
    "bls_cpi": {
        "url": "https://www.bls.gov/feed/cpi.rss",
        "default_topic": "inflation",
        "source": "BLS",
    },
    "bls_ppi": {
        "url": "https://www.bls.gov/feed/ppi.rss",
        "default_topic": "inflation",
        "source": "BLS",
    },
    "bls_productivity": {
        "url": "https://www.bls.gov/feed/prod2.rss",
        "default_topic": "growth",
        "source": "BLS",
    },
}


# ============================================================
# SEC UNIVERSE
# ============================================================

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

SEC_ALLOWED_FORMS = {
    "8-K",
    "8-K/A",
    "10-Q",
    "10-Q/A",
    "10-K",
    "10-K/A",
}


# ============================================================
# RESEARCH-ONLY FLAGS
# ============================================================

RESEARCH_ONLY_FLAGS = {
    "research_only": True,
    "decision_engine_ready": False,
    "trading_signal": False,
    "forecast": False,
    "pit_perfect": False,
    "point_in_time_reconstructed": False,
}


# ============================================================
# HELPERS
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_text(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def parse_datetime(value: Any) -> Optional[datetime]:
    """
    Robust parser for:
    - GDELT seendate
    - RSS pubDate
    - ISO timestamps
    """

    if value is None:
        return None

    text = normalize_text(value)

    if not text:
        return None

    # GDELT:
    # 20260922T143000Z
    if re.fullmatch(r"\d{8}T\d{6}Z", text):
        try:
            dt = datetime.strptime(
                text,
                "%Y%m%dT%H%M%SZ",
            )

            return dt.replace(tzinfo=timezone.utc)

        except ValueError:
            pass

    # RFC 2822 / RSS
    try:
        dt = parsedate_to_datetime(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        pass

    # ISO fallback
    try:
        normalized = text.replace("Z", "+00:00")

        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(timezone.utc)

    except Exception:
        return None


def sha256_id(*parts: Any) -> str:
    raw = "||".join(normalize_text(x) for x in parts)

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()


def classify_topic(title: str, fallback: str = "market") -> str:
    """
    Conservative title-based topic classification.

    This is descriptive metadata only.
    It does NOT infer market impact.
    """

    text = normalize_text(title).lower()

    # FED
    if any(
        term in text
        for term in [
            "federal reserve",
            "fomc",
            "fed chair",
            "fed governor",
            "monetary policy",
            "interest rate",
            "policy rate",
            "powell",
        ]
    ):
        return "fed"

    # INFLATION
    if any(
        term in text
        for term in [
            "consumer price",
            "cpi",
            "producer price",
            "ppi",
            "inflation",
            "prices",
        ]
    ):
        return "inflation"

    # LABOR
    if any(
        term in text
        for term in [
            "employment",
            "unemployment",
            "nonfarm payroll",
            "payroll",
            "jobless claims",
            "job openings",
            "labor market",
            "labour market",
        ]
    ):
        return "labor"

    # GROWTH
    if any(
        term in text
        for term in [
            "gdp",
            "economic growth",
            "economic activity",
            "pmi",
            "ism",
            "productivity",
            "recession",
            "personal income",
            "consumer spending",
        ]
    ):
        return "growth"

    # GEOPOLITICAL
    if any(
        term in text
        for term in [
            "tariff",
            "tariffs",
            "sanction",
            "sanctions",
            "trade war",
            "ceasefire",
            "conflict",
            "geopolitical",
            "iran",
            "russia",
            "ukraine",
            "china",
        ]
    ):
        return "geopolitical"

    # ENERGY
    if any(
        term in text
        for term in [
            "oil",
            "crude",
            "opec",
            "gasoline",
            "energy",
            "natural gas",
        ]
    ):
        return "energy"

    # MARKET
    if any(
        term in text
        for term in [
            "s&p 500",
            "sp500",
            "nasdaq",
            "equities",
            "stocks",
            "stock market",
            "financial markets",
        ]
    ):
        return "market"

    return fallback


def title_relevance(title: str) -> bool:
    """
    Conservative relevance test.

    A title is relevant when it contains at least one
    US macro / market event term.
    """

    text = normalize_text(title).lower()

    terms = [
        "federal reserve",
        "fomc",
        "powell",
        "interest rate",
        "inflation",
        "cpi",
        "ppi",
        "employment",
        "unemployment",
        "payroll",
        "jobless",
        "gdp",
        "pmi",
        "ism",
        "recession",
        "s&p 500",
        "sp500",
        "equities",
        "tariff",
        "sanction",
        "trade war",
        "oil",
        "crude",
        "opec",
        "energy",
    ]

    return any(term in text for term in terms)


# ============================================================
# HTTP
# ============================================================

def http_get(
    url: str,
    headers: Dict[str, str],
    retries: int,
    backoff: float,
    max_backoff: float,
    label: str,
) -> Tuple[Optional[bytes], Dict[str, Any]]:

    last_error = None

    for attempt in range(1, retries + 1):

        try:

            request = urllib.request.Request(
                url,
                headers=headers,
                method="GET",
            )

            with urllib.request.urlopen(
                request,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:

                body = response.read()

                status = getattr(
                    response,
                    "status",
                    200,
                )

                return body, {
                    "ok": True,
                    "status_code": status,
                    "attempt": attempt,
                    "error": None,
                }

        except urllib.error.HTTPError as exc:

            last_error = f"HTTP {exc.code}"

            retryable = (
                exc.code == 408
                or exc.code == 429
                or 500 <= exc.code <= 599
            )

            if not retryable:
                break

            retry_after = exc.headers.get("Retry-After")

            if retry_after:
                try:
                    sleep_seconds = min(
                        float(retry_after),
                        max_backoff,
                    )
                except Exception:
                    sleep_seconds = backoff * (2 ** (attempt - 1))
            else:
                sleep_seconds = backoff * (
                    2 ** (attempt - 1)
                )

            sleep_seconds = min(
                sleep_seconds,
                max_backoff,
            )

            sleep_seconds += random.uniform(
                0.0,
                1.5,
            )

            print(
                f"[{label}] attempt={attempt} "
                f"HTTP={exc.code} "
                f"sleep={sleep_seconds:.1f}s",
                flush=True,
            )

            if attempt < retries:
                time.sleep(sleep_seconds)

        except (
            urllib.error.URLError,
            TimeoutError,
            OSError,
        ) as exc:

            last_error = repr(exc)

            sleep_seconds = min(
                backoff * (2 ** (attempt - 1)),
                max_backoff,
            )

            sleep_seconds += random.uniform(
                0.0,
                1.0,
            )

            print(
                f"[{label}] attempt={attempt} "
                f"network_error={repr(exc)} "
                f"sleep={sleep_seconds:.1f}s",
                flush=True,
            )

            if attempt < retries:
                time.sleep(sleep_seconds)

        except Exception as exc:

            last_error = repr(exc)
            break

    return None, {
        "ok": False,
        "status_code": None,
        "attempt": retries,
        "error": last_error,
    }


# ============================================================
# GDELT
# ============================================================

def collect_gdelt() -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:

    print("\n" + "=" * 72)
    print("GDELT COLLECTION")
    print("=" * 72)

    params = {
        "query": GDELT_COMBINED_QUERY,
        "mode": "artlist",
        "maxrecords": str(GDELT_MAX_RECORDS),
        "timespan": GDELT_TIMESPAN,
        "sort": "datedesc",
        "format": "json",
    }

    url = (
        GDELT_URL
        + "?"
        + urllib.parse.urlencode(
            params,
            quote_via=urllib.parse.quote,
        )
    )

    headers = {
        "User-Agent": (
            "US500-Macro-Intelligence/2.0 "
            "https://github.com/"
            "mohamednossaoui-max/US500-Macro-Intelligence"
        ),
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    body, status = http_get(
        url=url,
        headers=headers,
        retries=GDELT_RETRIES,
        backoff=GDELT_BACKOFF_SECONDS,
        max_backoff=GDELT_MAX_BACKOFF_SECONDS,
        label="GDELT",
    )

    if body is None:

        print(
            f"GDELT unavailable: {status.get('error')}",
            flush=True,
        )

        return [], {
            "ok": False,
            "rows": 0,
            "error": status.get("error"),
            "query_requests": 1,
            "fallback_required": True,
        }

    try:

        text = body.decode(
            "utf-8",
            errors="replace",
        ).strip()

        if not text:
            raise ValueError(
                "empty GDELT response"
            )

        payload = json.loads(text)

    except Exception as exc:

        print(
            f"GDELT JSON parse failure: {repr(exc)}",
            flush=True,
        )

        return [], {
            "ok": False,
            "rows": 0,
            "error": repr(exc),
            "query_requests": 1,
            "fallback_required": True,
        }

    articles = payload.get(
        "articles",
        [],
    )

    rows: List[Dict[str, Any]] = []

    for article in articles:

        title = normalize_text(
            article.get("title")
        )

        article_url = normalize_text(
            article.get("url")
        )

        if not title or not article_url:
            continue

        published_dt = parse_datetime(
            article.get("seendate")
        )

        if published_dt is None:
            continue

        domain = normalize_text(
            article.get("domain")
        )

        topic = classify_topic(
            title,
            fallback="market",
        )

        relevant = title_relevance(
            title
        )

        event_id = sha256_id(
            "GDELT",
            article_url,
            title,
            published_dt.isoformat(),
        )

        rows.append(
            {
                "event_id": event_id,
                "source_type": "GDELT",
                "source": domain or "GDELT",
                "topic": topic,
                "published_at": published_dt.isoformat(),
                "availability_date": published_dt.isoformat(),
                "title": title,
                "url": article_url,
                "language": normalize_text(
                    article.get("language")
                ),
                "country": normalize_text(
                    article.get("sourcecountry")
                ),
                "tone": normalize_text(
                    article.get("tone")
                ),
                "topic_relevance_title": bool(
                    relevant
                ),
                "point_in_time_safe": True,
            }
        )

    print(
        f"GDELT status=OK rows={len(rows)}",
        flush=True,
    )

    return rows, {
        "ok": True,
        "rows": len(rows),
        "error": None,
        "query_requests": 1,
        "fallback_required": len(rows) == 0,
    }


# ============================================================
# RSS
# ============================================================

def xml_child_text(
    element: ET.Element,
    names: List[str],
) -> str:

    wanted = {
        name.lower()
        for name in names
    }

    for child in list(element):

        tag = child.tag

        if "}" in tag:
            tag = tag.split(
                "}",
                1
            )[1]

        if tag.lower() in wanted:

            text = normalize_text(
                "".join(
                    child.itertext()
                )
            )

            if text:
                return text

    return ""


def xml_link(element: ET.Element) -> str:

    # RSS <link>
    value = xml_child_text(
        element,
        ["link"],
    )

    if value.startswith(
        "http://"
    ) or value.startswith(
        "https://"
    ):
        return value

    # Atom <link href="...">
    for child in list(element):

        tag = child.tag

        if "}" in tag:
            tag = tag.split(
                "}",
                1
            )[1]

        if tag.lower() == "link":

            href = child.attrib.get(
                "href",
                "",
            )

            href = normalize_text(
                href
            )

            if href:
                return href

    return ""


def parse_rss_feed(
    body: bytes,
    feed_name: str,
    feed_config: Dict[str, str],
) -> List[Dict[str, Any]]:

    root = ET.fromstring(body)

    items: List[ET.Element] = []

    for element in root.iter():

        tag = element.tag

        if "}" in tag:
            tag = tag.split(
                "}",
                1
            )[1]

        if tag.lower() in {
            "item",
            "entry",
        }:
            items.append(element)

    rows: List[Dict[str, Any]] = []

    for item in items:

        title = xml_child_text(
            item,
            ["title"],
        )

        link = xml_link(item)

        date_text = xml_child_text(
            item,
            [
                "pubDate",
                "published",
                "updated",
                "date",
            ],
        )

        published_dt = parse_datetime(
            date_text
        )

        if not title or not link:
            continue

        if published_dt is None:
            continue

        default_topic = feed_config[
            "default_topic"
        ]

        topic = classify_topic(
            title,
            fallback=default_topic,
        )

        event_id = sha256_id(
            feed_config["source"],
            feed_name,
            link,
            title,
            published_dt.isoformat(),
        )

        rows.append(
            {
                "event_id": event_id,
                "source_type": "OFFICIAL_RSS",
                "source": feed_config["source"],
                "topic": topic,
                "published_at": published_dt.isoformat(),
                "availability_date": published_dt.isoformat(),
                "title": title,
                "url": link,
                "language": "en",
                "country": "US",
                "tone": "",
                "topic_relevance_title": bool(
                    title_relevance(title)
                    or topic in {
                        "fed",
                        "labor",
                        "inflation",
                        "growth",
                    }
                ),
                "point_in_time_safe": True,
            }
        )

    return rows


def collect_official_rss() -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
]:

    print("\n" + "=" * 72)
    print("OFFICIAL RSS FALLBACK")
    print("=" * 72)

    all_rows: List[Dict[str, Any]] = []

    statuses: Dict[str, Any] = {}

    for feed_name, config in OFFICIAL_RSS_FEEDS.items():

        url = config["url"]

        headers = {
            "User-Agent": (
                "US500-Macro-Intelligence/2.0 "
                "https://github.com/"
                "mohamednossaoui-max/US500-Macro-Intelligence"
            ),
            "Accept": (
                "application/rss+xml, "
                "application/xml, "
                "text/xml, "
                "*/*"
            ),
        }

        body, status = http_get(
            url=url,
            headers=headers,
            retries=RSS_RETRIES,
            backoff=2.0,
            max_backoff=8.0,
            label=f"RSS:{feed_name}",
        )

        if body is None:

            statuses[feed_name] = {
                "ok": False,
                "rows": 0,
                "error": status.get(
                    "error"
                ),
            }

            print(
                f"{feed_name}: FAILED "
                f"{status.get('error')}",
                flush=True,
            )

            continue

        try:

            rows = parse_rss_feed(
                body,
                feed_name,
                config,
            )

            all_rows.extend(rows)

            statuses[feed_name] = {
                "ok": True,
                "rows": len(rows),
                "error": None,
            }

            print(
                f"{feed_name}: OK "
                f"rows={len(rows)}",
                flush=True,
            )

        except Exception as exc:

            statuses[feed_name] = {
                "ok": False,
                "rows": 0,
                "error": repr(exc),
            }

            print(
                f"{feed_name}: PARSE ERROR "
                f"{repr(exc)}",
                flush=True,
            )

        time.sleep(
            RSS_PACING_SECONDS
        )

    return all_rows, {
        "ok": len(all_rows) > 0,
        "rows": len(all_rows),
        "feeds": statuses,
    }


# ============================================================
# SEC
# ============================================================

def collect_sec() -> Tuple[
    List[Dict[str, Any]],
    Dict[str, Any],
]:

    print("\n" + "=" * 72)
    print("SEC COLLECTION")
    print("=" * 72)

    user_agent = normalize_text(
        os.getenv(
            "SEC_USER_AGENT",
            "",
        )
    )

    if not user_agent:

        message = (
            "SEC_USER_AGENT is missing; "
            "SEC collection skipped intentionally."
        )

        print(message)

        return [], {
            "ok": False,
            "skipped": True,
            "rows": 0,
            "error": "missing SEC_USER_AGENT",
            "companies": {},
        }

    rows: List[Dict[str, Any]] = []

    company_status: Dict[str, Any] = {}

    headers = {
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
    }

    for ticker, cik in SEC_UNIVERSE.items():

        url = SEC_SUBMISSIONS.format(
            cik=cik
        )

        body, status = http_get(
            url=url,
            headers=headers,
            retries=SEC_RETRIES,
            backoff=2.0,
            max_backoff=10.0,
            label=f"SEC:{ticker}",
        )

        if body is None:

            company_status[ticker] = {
                "ok": False,
                "rows": 0,
                "error": status.get(
                    "error"
                ),
            }

            print(
                f"{ticker}: FAILED "
                f"{status.get('error')}",
                flush=True,
            )

            time.sleep(
                SEC_PACING_SECONDS
            )

            continue

        try:

            payload = json.loads(
                body.decode(
                    "utf-8",
                    errors="replace",
                )
            )

            recent = payload.get(
                "filings",
                {}
            ).get(
                "recent",
                {}
            )

            forms = recent.get(
                "form",
                []
            )

            filing_dates = recent.get(
                "filingDate",
                []
            )

            acceptance_times = recent.get(
                "acceptanceDateTime",
                []
            )

            accessions = recent.get(
                "accessionNumber",
                []
            )

            primary_documents = recent.get(
                "primaryDocument",
                []
            )

            local_count = 0

            for i, form in enumerate(forms):

                form = normalize_text(
                    form
                )

                if form not in SEC_ALLOWED_FORMS:
                    continue

                filing_date = (
                    filing_dates[i]
                    if i < len(filing_dates)
                    else ""
                )

                acceptance = (
                    acceptance_times[i]
                    if i < len(acceptance_times)
                    else ""
                )

                accession = (
                    accessions[i]
                    if i < len(accessions)
                    else ""
                )

                primary_doc = (
                    primary_documents[i]
                    if i < len(primary_documents)
                    else ""
                )

                published_dt = (
                    parse_datetime(
                        acceptance
                    )
                    or parse_datetime(
                        filing_date
                    )
                )

                if published_dt is None:
                    continue

                accession_no_dash = (
                    accession.replace(
                        "-",
                        "",
                    )
                )

                if (
                    accession_no_dash
                    and primary_doc
                ):

                    filing_url = (
                        "https://www.sec.gov/Archives/"
                        f"edgar/data/"
                        f"{int(cik)}/"
                        f"{accession_no_dash}/"
                        f"{primary_doc}"
                    )

                else:

                    filing_url = (
                        "https://www.sec.gov/"
                        "edgar/browse/"
                        f"?CIK={cik}"
                        "&owner=exclude"
                    )

                title = (
                    f"{ticker} {form}"
                )

                event_id = sha256_id(
                    "SEC",
                    ticker,
                    accession,
                    form,
                    published_dt.isoformat(),
                )

                rows.append(
                    {
                        "event_id": event_id,
                        "source_type": "SEC",
                        "source": "SEC EDGAR",
                        "topic": "corporate_filing",
                        "published_at": published_dt.isoformat(),
                        "availability_date": published_dt.isoformat(),
                        "title": title,
                        "url": filing_url,
                        "language": "en",
                        "country": "US",
                        "tone": "",
                        "topic_relevance_title": True,
                        "point_in_time_safe": True,
                        "ticker": ticker,
                        "form": form,
                    }
                )

                local_count += 1

            company_status[ticker] = {
                "ok": True,
                "rows": local_count,
                "error": None,
            }

            print(
                f"{ticker}: OK rows={local_count}",
                flush=True,
            )

        except Exception as exc:

            company_status[ticker] = {
                "ok": False,
                "rows": 0,
                "error": repr(exc),
            }

            print(
                f"{ticker}: PARSE ERROR "
                f"{repr(exc)}",
                flush=True,
            )

        time.sleep(
            SEC_PACING_SECONDS
        )

    return rows, {
        "ok": len(rows) > 0,
        "skipped": False,
        "rows": len(rows),
        "error": None,
        "companies": company_status,
    }


# ============================================================
# DATASET NORMALIZATION
# ============================================================

REQUIRED_COLUMNS = [
    "event_id",
    "source_type",
    "source",
    "topic",
    "published_at",
    "availability_date",
    "title",
    "url",
    "language",
    "country",
    "tone",
    "topic_relevance_title",
    "point_in_time_safe",
]


def normalize_dataset(
    rows: List[Dict[str, Any]]
) -> pd.DataFrame:

    if not rows:

        return pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    df = pd.DataFrame(
        rows
    )

    for column in REQUIRED_COLUMNS:

        if column not in df.columns:

            df[column] = ""

    # Remove exact duplicate event IDs.
    df = df.drop_duplicates(
        subset=["event_id"],
        keep="first",
    )

    # Parse timestamps.
    df["published_at"] = pd.to_datetime(
        df["published_at"],
        errors="coerce",
        utc=True,
    )

    df["availability_date"] = pd.to_datetime(
        df["availability_date"],
        errors="coerce",
        utc=True,
    )

    # Sort newest first.
    df = df.sort_values(
        "published_at",
        ascending=False,
    )

    # Serialize timestamps as ISO strings.
    df["published_at"] = (
        df["published_at"]
        .dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )

    df["availability_date"] = (
        df["availability_date"]
        .dt.strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
    )

    return df


# ============================================================
# VALIDATION
# ============================================================

def validation_check(
    check: str,
    passed: bool,
    detail: str,
) -> Dict[str, Any]:

    return {
        "check": check,
        "pass": bool(passed),
        "detail": detail,
    }


def validate(
    df: pd.DataFrame,
    gdelt_status: Dict[str, Any],
    rss_status: Dict[str, Any],
    sec_status: Dict[str, Any],
) -> Dict[str, Any]:

    errors: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = [
        c
        for c in REQUIRED_COLUMNS
        if c not in df.columns
    ]

    required_columns_pass = (
        len(missing_columns) == 0
    )

    if not required_columns_pass:

        errors.append(
            validation_check(
                "required_columns",
                False,
                str(missing_columns),
            )
        )

    # --------------------------------------------------------
    # Rows
    # --------------------------------------------------------

    row_count = len(df)

    if row_count < MIN_TOTAL_ROWS:

        errors.append(
            validation_check(
                "minimum_dataset_rows",
                False,
                f"rows={row_count}; "
                f"minimum={MIN_TOTAL_ROWS}",
            )
        )

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    if row_count == 0:

        errors.append(
            validation_check(
                "unique_event_ids",
                False,
                "rows=0",
            )
        )

    else:

        unique_pass = (
            df["event_id"]
            .notna()
            .all()
            and
            df["event_id"]
            .astype(str)
            .str.len()
            .gt(0)
            .all()
            and
            df["event_id"]
            .is_unique
        )

        if not unique_pass:

            errors.append(
                validation_check(
                    "unique_event_ids",
                    False,
                    "duplicate_or_empty_ids",
                )
            )

    # --------------------------------------------------------
    # Published timestamps
    # --------------------------------------------------------

    if row_count == 0:

        errors.append(
            validation_check(
                "published_timestamps_parse",
                False,
                "",
            )
        )

    else:

        parsed = pd.to_datetime(
            df["published_at"],
            errors="coerce",
            utc=True,
        )

        timestamp_pass = (
            parsed.notna().all()
        )

        if not timestamp_pass:

            errors.append(
                validation_check(
                    "published_timestamps_parse",
                    False,
                    (
                        "invalid="
                        f"{int(parsed.isna().sum())}"
                    ),
                )
            )

    # --------------------------------------------------------
    # Point-in-time structural flag
    # --------------------------------------------------------

    if row_count == 0:

        errors.append(
            validation_check(
                "point_in_time_safe",
                False,
                "",
            )
        )

    else:

        pit_pass = (
            df["point_in_time_safe"]
            .fillna(False)
            .astype(bool)
            .all()
        )

        if not pit_pass:

            errors.append(
                validation_check(
                    "point_in_time_safe",
                    False,
                    "one_or_more_false",
                )
            )

    # --------------------------------------------------------
    # URLs
    # --------------------------------------------------------

    if row_count == 0:

        errors.append(
            validation_check(
                "urls_valid",
                False,
                "",
            )
        )

    else:

        urls = (
            df["url"]
            .fillna("")
            .astype(str)
        )

        urls_pass = (
            urls.str.startswith(
                (
                    "http://",
                    "https://",
                )
            )
            .all()
        )

        if not urls_pass:

            errors.append(
                validation_check(
                    "urls_valid",
                    False,
                    "invalid_url_present",
                )
            )

    # --------------------------------------------------------
    # Topic coverage
    # --------------------------------------------------------

    topic_counts = {}

    if row_count > 0:

        topic_counts = (
            df["topic"]
            .fillna("unknown")
            .value_counts()
            .to_dict()
        )

    core_topics = {
        "fed",
        "inflation",
        "labor",
        "growth",
    }

    covered_core_topics = (
        set(topic_counts.keys())
        & core_topics
    )

    core_topic_pass = (
        len(covered_core_topics)
        >= MIN_CORE_TOPIC_FAMILIES
    )

    if not core_topic_pass:

        errors.append(
            validation_check(
                "core_topic_coverage",
                False,
                (
                    f"covered="
                    f"{sorted(covered_core_topics)}; "
                    f"minimum="
                    f"{MIN_CORE_TOPIC_FAMILIES}"
                ),
            )
        )

    # --------------------------------------------------------
    # GDELT
    # --------------------------------------------------------

    gdelt_rows = int(
        gdelt_status.get(
            "rows",
            0,
        )
    )

    if gdelt_rows == 0:

        warnings.append(
            {
                "check": "gdelt_collection",
                "detail": (
                    "GDELT unavailable or "
                    "rate-limited; official "
                    "RSS fallback used."
                ),
            }
        )

        gdelt_title_relevance_pass = True

        gdelt_detail = (
            "not_applicable_gdelt_unavailable"
        )

        gdelt_execution_pass = True

    else:

        gdelt_df = df[
            df["source_type"] == "GDELT"
        ]

        gdelt_relevance = (
            gdelt_df[
                "topic_relevance_title"
            ]
            .fillna(False)
            .astype(bool)
            .mean()
        )

        gdelt_title_relevance_pass = (
            gdelt_relevance
            >= MIN_GDELT_TITLE_RELEVANCE
        )

        gdelt_detail = (
            f"relevant_pct="
            f"{gdelt_relevance:.2%}"
        )

        gdelt_execution_pass = True

        if not gdelt_title_relevance_pass:

            errors.append(
                validation_check(
                    "gdelt_title_relevance",
                    False,
                    gdelt_detail,
                )
            )

    if gdelt_rows == 0:

        gdelt_topics = {}

    else:

        gdelt_topics = (
            df[
                df["source_type"]
                == "GDELT"
            ]["topic"]
            .value_counts()
            .to_dict()
        )

    # GDELT is supplementary to the official fallback.
    if gdelt_rows > 0:

        gdelt_topics_pass = (
            len(gdelt_topics) >= 3
        )

        if not gdelt_topics_pass:

            errors.append(
                validation_check(
                    "gdelt_topics_covered",
                    False,
                    json.dumps(
                        gdelt_topics,
                        sort_keys=True,
                    ),
                )
            )

    # --------------------------------------------------------
    # SEC
    # --------------------------------------------------------

    if sec_status.get(
        "skipped",
        False,
    ):

        warnings.append(
            {
                "check": "sec_collection",
                "detail": (
                    "SEC skipped because "
                    "SEC_USER_AGENT was not "
                    "configured."
                ),
            }
        )

    elif not sec_status.get(
        "ok",
        False,
    ):

        warnings.append(
            {
                "check": "sec_collection",
                "detail": (
                    "SEC supplementary "
                    "collection failed; "
                    "does not invalidate "
                    "Event / News dataset."
                ),
            }
        )

    # --------------------------------------------------------
    # Research-only guards
    # --------------------------------------------------------

    for key, expected in RESEARCH_ONLY_FLAGS.items():

        if expected is True:

            # These are written in summary below.
            pass

    # --------------------------------------------------------
    # Overall result
    # --------------------------------------------------------

    validation_pass = (
        len(errors) == 0
        and row_count >= MIN_TOTAL_ROWS
        and required_columns_pass
        and core_topic_pass
        and gdelt_title_relevance_pass
        and gdelt_execution_pass
    )

    checks = [
        validation_check(
            "required_columns",
            required_columns_pass,
            (
                "all_required_columns_present"
                if required_columns_pass
                else str(missing_columns)
            ),
        ),
        validation_check(
            "minimum_dataset_rows",
            row_count >= MIN_TOTAL_ROWS,
            f"rows={row_count}",
        ),
        validation_check(
            "unique_event_ids",
            row_count > 0
            and df["event_id"].is_unique,
            (
                f"rows={row_count}"
                if row_count > 0
                else "rows=0"
            ),
        ),
        validation_check(
            "published_timestamps_parse",
            (
                row_count > 0
                and pd.to_datetime(
                    df["published_at"],
                    errors="coerce",
                    utc=True,
                ).notna().all()
            ),
            "",
        ),
        validation_check(
            "point_in_time_safe",
            (
                row_count > 0
                and df["point_in_time_safe"]
                .fillna(False)
                .astype(bool)
                .all()
            ),
            "",
        ),
        validation_check(
            "urls_valid",
            (
                row_count > 0
                and df["url"]
                .fillna("")
                .astype(str)
                .str.startswith(
                    (
                        "http://",
                        "https://",
                    )
                )
                .all()
            ),
            "",
        ),
        validation_check(
            "core_topic_coverage",
            core_topic_pass,
            json.dumps(
                topic_counts,
                sort_keys=True,
            ),
        ),
        validation_check(
            "gdelt_query_execution",
            gdelt_execution_pass,
            (
                "GDELT rows="
                f"{gdelt_rows}"
                if gdelt_rows > 0
                else
                "GDELT unavailable; "
                "official RSS fallback active"
            ),
        ),
        validation_check(
            "gdelt_title_relevance",
            gdelt_title_relevance_pass,
            gdelt_detail,
        ),
    ]

    return {
        "validator": "Event / News Intelligence v2",
        "version": VERSION,
        "status": (
            "PASS"
            if validation_pass
            else "FAIL"
        ),
        "validation_pass": bool(
            validation_pass
        ),
        "generated_at": utc_now_iso(),
        "rows": row_count,
        "topic_counts": topic_counts,
        "gdelt": gdelt_status,
        "official_rss": rss_status,
        "sec": sec_status,
        "checks": checks,
        "errors": errors,
        "warnings": warnings,
        **RESEARCH_ONLY_FLAGS,
        "interpretation": (
            "PASS is structural/data-quality "
            "validation only. Event and news "
            "coverage is descriptive and does "
            "not establish causality, "
            "predictiveness, trading usefulness, "
            "or investment preference."
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "US500 Macro Intelligence "
            "Event / News Intelligence v2"
        )
    )

    parser.add_argument(
        "--output",
        default="event_news_intelligence_v2",
        help="Output directory",
    )

    args = parser.parse_args()

    output_dir = Path(
        args.output
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("\n" + "=" * 72)
    print(
        "EVENT / NEWS INTELLIGENCE v2"
    )
    print("=" * 72)

    print(
        "Research-only: YES"
    )

    print(
        "Decision Engine: DISABLED"
    )

    print(
        "Trading signals: DISABLED"
    )

    print(
        "Forecasting: DISABLED"
    )

    # --------------------------------------------------------
    # GDELT
    # --------------------------------------------------------

    gdelt_rows, gdelt_status = (
        collect_gdelt()
    )

    # --------------------------------------------------------
    # Official fallback
    # --------------------------------------------------------

    rss_rows, rss_status = (
        collect_official_rss()
    )

    # --------------------------------------------------------
    # SEC supplementary
    # --------------------------------------------------------

    sec_rows, sec_status = (
        collect_sec()
    )

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    all_rows = (
        gdelt_rows
        + rss_rows
        + sec_rows
    )

    df = normalize_dataset(
        all_rows
    )

    # --------------------------------------------------------
    # Save dataset
    # --------------------------------------------------------

    dataset_path = (
        output_dir
        / "event_news_research_v2.csv"
    )

    df.to_csv(
        dataset_path,
        index=False,
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    validation = validate(
        df=df,
        gdelt_status=gdelt_status,
        rss_status=rss_status,
        sec_status=sec_status,
    )

    validation_path = (
        output_dir
        / "event_news_validation_v2.json"
    )

    validation_path.write_text(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = {
        "collector": (
            "Event / News Intelligence v2"
        ),
        "version": VERSION,
        "generated_at": utc_now_iso(),
        "dataset": {
            "rows": len(df),
            "path": str(dataset_path),
            "source_counts": (
                df["source_type"]
                .value_counts()
                .to_dict()
                if len(df) > 0
                else {}
            ),
            "topic_counts": (
                df["topic"]
                .value_counts()
                .to_dict()
                if len(df) > 0
                else {}
            ),
        },
        "collection": {
            "gdelt": gdelt_status,
            "official_rss": rss_status,
            "sec": sec_status,
        },
        "research_only": RESEARCH_ONLY_FLAGS,
        "limitations": [
            (
                "GDELT DOC 2.0 is a rolling "
                "news search source and is "
                "subject to rate limiting."
            ),
            (
                "Official RSS feeds are used "
                "as a resilient descriptive "
                "fallback for core US macro "
                "topics."
            ),
            (
                "SEC is supplementary and "
                "requires a declared "
                "SEC_USER_AGENT."
            ),
            (
                "This dataset is not a "
                "perfect point-in-time "
                "reconstruction of all news."
            ),
            (
                "No causal inference, "
                "forecasting, ranking, or "
                "trading signal is produced."
            ),
        ],
    }

    summary_path = (
        output_dir
        / "event_news_research_summary_v2.json"
    )

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Console report
    # --------------------------------------------------------

    print("\n" + "=" * 72)
    print("VALIDATION RESULT")
    print("=" * 72)

    print(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        )
    )

    print("\n" + "=" * 72)
    print("DATASET SUMMARY")
    print("=" * 72)

    print(
        f"rows={len(df)}"
    )

    if len(df) > 0:

        print(
            "source_counts="
            + json.dumps(
                df["source_type"]
                .value_counts()
                .to_dict(),
                sort_keys=True,
            )
        )

        print(
            "topic_counts="
            + json.dumps(
                df["topic"]
                .value_counts()
                .to_dict(),
                sort_keys=True,
            )
        )

    print(
        f"dataset={dataset_path}"
    )

    print(
        f"validation={validation_path}"
    )

    print(
        f"summary={summary_path}"
    )

    print("\n" + "=" * 72)
    print("EXECUTION SUMMARY")
    print("=" * 72)

    print(
        f"GDELT rows: "
        f"{len(gdelt_rows)}"
    )

    print(
        f"Official RSS rows: "
        f"{len(rss_rows)}"
    )

    print(
        f"SEC rows: "
        f"{len(sec_rows)}"
    )

    print(
        f"Total rows: "
        f"{len(df)}"
    )

    print(
        "Research-only: TRUE"
    )

    print(
        "Decision Engine: FALSE"
    )

    print(
        "Trading Signal: FALSE"
    )

    print(
        "Forecast: FALSE"
    )

    # --------------------------------------------------------
    # Exit
    # --------------------------------------------------------

    if validation["validation_pass"]:

        print(
            "\nEVENT / NEWS INTELLIGENCE v2 "
            "VALIDATION: PASS"
        )

        return 0

    print(
        "\nEVENT / NEWS INTELLIGENCE v2 "
        "VALIDATION: FAIL"
    )

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
