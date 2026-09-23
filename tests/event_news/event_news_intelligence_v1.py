#!/usr/bin/env python3
"""
US500 Macro Intelligence
Event / News Intelligence v2.1

Research-only module.

IMPORTANT:
- No trading signals
- No forecasting
- No execution
- No Decision Engine integration
- No investment recommendation
- Descriptive event/news intelligence only
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
# VERSION / GLOBAL CONFIG
# ============================================================

VERSION = "2.1"

HTTP_TIMEOUT_SECONDS = 25

GDELT_RETRIES = 3
GDELT_BACKOFF_SECONDS = 4.0

RSS_RETRIES = 2
RSS_BACKOFF_SECONDS = 2.0

SEC_RETRIES = 2
SEC_BACKOFF_SECONDS = 2.0

GDELT_MAX_RECORDS = 100
GDELT_TIMESPAN = "3days"

MIN_TOTAL_ROWS = 10

CORE_TOPICS = {
    "fed",
    "inflation",
    "labor",
    "growth",
}

MIN_TOPIC_FAMILIES_FOR_FULL_COVERAGE = 3


# ============================================================
# RESEARCH-ONLY SAFETY FLAGS
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
# REQUIRED OUTPUT COLUMNS
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


# ============================================================
# GDELT
# ============================================================

GDELT_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
)

GDELT_QUERY = """
(
    "Federal Reserve"
    OR FOMC
    OR Powell
    OR CPI
    OR PPI
    OR inflation
    OR "nonfarm payrolls"
    OR unemployment
    OR "jobless claims"
    OR employment
    OR GDP
    OR "economic growth"
    OR PMI
    OR ISM
    OR recession
    OR "S&P 500"
    OR SP500
    OR equities
    OR tariff
    OR tariffs
    OR sanctions
    OR "trade war"
    OR conflict
    OR oil
    OR crude
    OR OPEC
    OR energy
)
(
    US
    OR U.S.
    OR "United States"
    OR America
)
""".replace("\n", " ")


# ============================================================
# OFFICIAL RSS SOURCES
# ============================================================

OFFICIAL_RSS_FEEDS = {
    "fed_monetary_policy": {
        "url": (
            "https://www.federalreserve.gov/"
            "feeds/press_monetary.xml"
        ),
        "source": "Federal Reserve",
        "fallback_topic": "fed",
    },

    "fed_all_press": {
        "url": (
            "https://www.federalreserve.gov/"
            "feeds/press_all.xml"
        ),
        "source": "Federal Reserve",
        "fallback_topic": "fed",
    },

    "bea_news": {
        "url": (
            "https://apps.bea.gov/rss/rss.xml"
        ),
        "source": "BEA",
        "fallback_topic": "growth",
    },

    "census_economic_indicators": {
        "url": (
            "https://www.census.gov/"
            "economic-indicators/indicator.xml"
        ),
        "source": "U.S. Census Bureau",
        "fallback_topic": "growth",
    },
}


# ============================================================
# OPTIONAL SEC
# ============================================================

SEC_SUBMISSIONS = (
    "https://data.sec.gov/submissions/CIK{cik}.json"
)

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
# UTILITY FUNCTIONS
# ============================================================

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any) -> str:
    if value is None:
        return ""

    text = str(value)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_url(url: Any) -> str:
    """
    Normalize URLs coming from RSS/XML feeds.

    Handles:
    - https://example.com
    - http://example.com
    - //example.com
    - www.example.com
    - example.com/path

    This is a structural normalization only.
    It does NOT fetch or verify the URL.
    """

    value = clean(url)

    if not value:
        return ""

    # Remove surrounding whitespace
    value = value.strip()

    # Scheme-relative URL
    if value.startswith("//"):
        return "https:" + value

    # Already valid
    if value.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return value

    # www.example.com
    if value.lower().startswith("www."):
        return "https://" + value

    # Relative URL
    if value.startswith("/"):
        return "https://" + value.lstrip("/")

    # Bare domain/path
    return "https://" + value


def make_id(*parts: Any) -> str:
    raw = "||".join(
        clean(x)
        for x in parts
    )

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:32]


def parse_datetime(
    value: Any,
) -> Optional[str]:

    if value is None:
        return None

    text = clean(value)

    if not text:
        return None

    # ISO 8601
    try:
        dt = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        ).isoformat()

    except Exception:
        pass

    # RFC 2822 / RSS
    try:
        dt = parsedate_to_datetime(
            text
        )

        if dt.tzinfo is None:
            dt = dt.replace(
                tzinfo=timezone.utc
            )

        return dt.astimezone(
            timezone.utc
        ).isoformat()

    except Exception:
        pass

    return None


# ============================================================
# TOPIC CLASSIFICATION
# ============================================================

def classify_topic(
    title: str,
    description: str = "",
    fallback: str = "market",
) -> str:

    text = (
        f"{clean(title)} "
        f"{clean(description)}"
    ).lower()

    rules = [

        (
            "fed",
            [
                "federal reserve",
                "fomc",
                "fed chair",
                "powell",
                "interest rate",
                "monetary policy",
                "policy rate",
            ],
        ),

        (
            "inflation",
            [
                "cpi",
                "consumer price",
                "ppi",
                "producer price",
                "inflation",
                "prices",
            ],
        ),

        (
            "labor",
            [
                "nonfarm payroll",
                "payrolls",
                "unemployment",
                "employment",
                "jobless claims",
                "initial claims",
                "labor market",
                "labour market",
                "wages",
            ],
        ),

        (
            "growth",
            [
                "gdp",
                "economic growth",
                "economic activity",
                "personal income",
                "consumer spending",
                "retail sales",
                "manufacturing",
                "construction",
                "housing",
                "trade",
                "productivity",
                "pmi",
                "ism",
            ],
        ),

        (
            "energy",
            [
                "oil",
                "crude",
                "opec",
                "energy",
                "natural gas",
            ],
        ),

        (
            "geopolitical",
            [
                "tariff",
                "tariffs",
                "sanctions",
                "trade war",
                "conflict",
                "war",
                "geopolitical",
            ],
        ),

        (
            "market",
            [
                "s&p 500",
                "sp500",
                "equity",
                "equities",
                "stock market",
                "stocks",
                "nasdaq",
                "dow jones",
            ],
        ),
    ]

    for topic, keywords in rules:

        for keyword in keywords:

            if keyword in text:
                return topic

    return fallback


def title_relevance(
    title: str,
) -> float:

    text = clean(title).lower()

    if not text:
        return 0.0

    keywords = [
        "federal reserve",
        "fomc",
        "powell",
        "inflation",
        "cpi",
        "ppi",
        "employment",
        "unemployment",
        "payroll",
        "jobless claims",
        "gdp",
        "economic growth",
        "pmi",
        "ism",
        "retail sales",
        "personal income",
        "consumer spending",
        "trade",
        "tariff",
        "energy",
        "oil",
        "s&p 500",
        "sp500",
    ]

    hits = sum(
        1
        for keyword in keywords
        if keyword in text
    )

    return round(
        min(
            1.0,
            hits / 4.0,
        ),
        4,
    )


def infer_tone(
    title: str,
) -> float:

    text = clean(title).lower()

    positive_words = [
        "increase",
        "increased",
        "growth",
        "strong",
        "improve",
        "improved",
        "rise",
        "rises",
        "higher",
        "surge",
        "record",
    ]

    negative_words = [
        "decline",
        "declined",
        "fall",
        "falls",
        "lower",
        "weak",
        "weakness",
        "recession",
        "crisis",
        "loss",
        "losses",
    ]

    positive = sum(
        1
        for word in positive_words
        if word in text
    )

    negative = sum(
        1
        for word in negative_words
        if word in text
    )

    if positive == negative:
        return 0.0

    if positive > negative:
        return 1.0

    return -1.0


# ============================================================
# HTTP
# ============================================================

def http_get(
    url: str,
    *,
    retries: int = 2,
    backoff_seconds: float = 2.0,
    user_agent: Optional[str] = None,
) -> Tuple[
    Optional[bytes],
    Optional[str],
]:

    headers = {
        "User-Agent": (
            user_agent
            or (
                "US500-Macro-Intelligence/2.1 "
                "(research-only)"
            )
        ),

        "Accept": (
            "application/rss+xml, "
            "application/xml, "
            "text/xml, "
            "application/json, "
            "*/*"
        ),

        "Accept-Language": (
            "en-US,en;q=0.8"
        ),

        "Cache-Control": "no-cache",
    }

    last_error = None

    for attempt in range(
        retries + 1
    ):

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

                status = getattr(
                    response,
                    "status",
                    200,
                )

                body = response.read()

                if status != 200:
                    return (
                        None,
                        f"HTTP {status}",
                    )

                return (
                    body,
                    None,
                )

        except urllib.error.HTTPError as exc:

            last_error = (
                f"HTTP {exc.code}"
            )

            # Don't repeatedly retry permanent errors.
            if exc.code in {
                400,
                401,
                403,
                404,
            }:
                return (
                    None,
                    last_error,
                )

        except Exception as exc:

            last_error = repr(exc)

        if attempt < retries:

            delay = min(
                backoff_seconds
                * (2 ** attempt),
                20.0,
            )

            delay += random.uniform(
                0,
                0.5,
            )

            time.sleep(delay)

    return (
        None,
        last_error
        or "unknown_http_error",
    )


# ============================================================
# XML / RSS HELPERS
# ============================================================

def local_tag(
    tag: str,
) -> str:

    if not tag:
        return ""

    if "}" in tag:
        tag = tag.split(
            "}",
            1,
        )[1]

    return tag.lower()


def child_text(
    element: ET.Element,
    names: List[str],
) -> str:

    wanted = {
        name.lower()
        for name in names
    }

    for child in list(element):

        tag = local_tag(
            child.tag
        )

        if tag in wanted:

            return clean(
                child.text
            )

    return ""


def element_link(
    element: ET.Element,
) -> str:
    """
    Extract and normalize an RSS/Atom link.

    Fixes the exact issue found in the current
    Event News run where BEA returned:

        www.bea.gov/...

    instead of:

        https://www.bea.gov/...
    """

    link = ""

    # --------------------------------------------------------
    # RSS / Atom child <link>
    # --------------------------------------------------------

    for child in list(element):

        if local_tag(
            child.tag
        ) != "link":
            continue

        href = child.attrib.get(
            "href"
        )

        if href:
            link = clean(href)
            break

        if child.text:
            link = clean(
                child.text
            )
            break

    # --------------------------------------------------------
    # Normalize URL
    # --------------------------------------------------------

    return normalize_url(
        link
    )


def parse_rss(
    body: bytes,
    fallback_topic: str,
) -> List[
    Dict[str, Any]
]:

    root = ET.fromstring(
        body
    )

    items = []

    for element in root.iter():

        tag = local_tag(
            element.tag
        )

        if tag not in {
            "item",
            "entry",
        }:
            continue

        title = child_text(
            element,
            [
                "title",
            ],
        )

        description = child_text(
            element,
            [
                "description",
                "summary",
                "content",
            ],
        )

        published_raw = child_text(
            element,
            [
                "pubdate",
                "published",
                "updated",
                "date",
                "dc:date",
            ],
        )

        url = element_link(
            element
        )

        published_at = parse_datetime(
            published_raw
        )

        if not title:
            continue

        if not url:
            continue

        topic = classify_topic(
            title,
            description,
            fallback_topic,
        )

        items.append(
            {
                "title": title,
                "description": description,
                "published_at": published_at,
                "url": url,
                "topic": topic,
            }
        )

    return items


# ============================================================
# GDELT
# ============================================================

def collect_gdelt() -> Dict[str, Any]:

    print(
        "\n"
        + "=" * 72
    )

    print(
        "GDELT COLLECTION"
    )

    print(
        "=" * 72
    )

    params = {
        "query": GDELT_QUERY,
        "mode": "artlist",
        "format": "rss",
        "maxrecords": str(
            GDELT_MAX_RECORDS
        ),
        "timespan": GDELT_TIMESPAN,
        "sort": "HybridRel",
    }

    url = (
        GDELT_URL
        + "?"
        + urllib.parse.urlencode(
            params
        )
    )

    body, error = http_get(
        url,
        retries=GDELT_RETRIES,
        backoff_seconds=GDELT_BACKOFF_SECONDS,
    )

    if error:

        print(
            f"GDELT unavailable: {error}"
        )

        return {
            "ok": False,
            "rows": [],
            "error": error,
            "query_requests": 1,
            "fallback_required": True,
        }

    try:

        rows = parse_rss(
            body,
            fallback_topic="market",
        )

        print(
            "GDELT RSS: "
            f"OK rows={len(rows)}"
        )

        return {
            "ok": True,
            "rows": rows,
            "error": None,
            "query_requests": 1,
            "fallback_required": False,
        }

    except Exception as exc:

        preview = (
            body[:200]
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        print(
            "GDELT RSS parse failure:",
            repr(exc),
        )

        print(
            "GDELT response preview:",
            repr(preview),
        )

        return {
            "ok": False,
            "rows": [],
            "error": repr(exc),
            "query_requests": 1,
            "fallback_required": True,
        }


# ============================================================
# OFFICIAL RSS
# ============================================================

def collect_official_rss() -> Dict[str, Any]:

    print(
        "\n"
        + "=" * 72
    )

    print(
        "OFFICIAL RSS COLLECTION"
    )

    print(
        "=" * 72
    )

    all_rows = []

    feed_results = {}

    for name, config in (
        OFFICIAL_RSS_FEEDS.items()
    ):

        url = config["url"]

        source = config["source"]

        fallback_topic = (
            config["fallback_topic"]
        )

        body, error = http_get(
            url,
            retries=RSS_RETRIES,
            backoff_seconds=RSS_BACKOFF_SECONDS,
        )

        if error:

            print(
                f"{name}: FAILED {error}"
            )

            feed_results[name] = {
                "ok": False,
                "rows": 0,
                "error": error,
            }

            continue

        try:

            rows = parse_rss(
                body,
                fallback_topic=fallback_topic,
            )

            for row in rows:

                row["source"] = source

                row["source_type"] = (
                    "OFFICIAL_RSS"
                )

            all_rows.extend(
                rows
            )

            print(
                f"{name}: "
                f"OK rows={len(rows)}"
            )

            feed_results[name] = {
                "ok": True,
                "rows": len(rows),
                "error": None,
            }

        except Exception as exc:

            print(
                f"{name}: "
                f"FAILED parse {repr(exc)}"
            )

            feed_results[name] = {
                "ok": False,
                "rows": 0,
                "error": repr(exc),
            }

    return {
        "ok": len(all_rows) > 0,
        "rows": all_rows,
        "feeds": feed_results,
    }


# ============================================================
# SEC
# ============================================================

def collect_sec() -> Dict[str, Any]:

    print(
        "\n"
        + "=" * 72
    )

    print(
        "SEC COLLECTION"
    )

    print(
        "=" * 72
    )

    sec_user_agent = clean(
        os.environ.get(
            "SEC_USER_AGENT"
        )
    )

    if not sec_user_agent:

        print(
            "SEC_USER_AGENT is missing; "
            "SEC collection skipped intentionally."
        )

        return {
            "ok": False,
            "rows": [],
            "skipped": True,
            "error": (
                "SEC_USER_AGENT missing"
            ),
        }

    rows = []

    for ticker, cik in (
        SEC_UNIVERSE.items()
    ):

        url = SEC_SUBMISSIONS.format(
            cik=int(cik)
        )

        body, error = http_get(
            url,
            retries=SEC_RETRIES,
            backoff_seconds=SEC_BACKOFF_SECONDS,
            user_agent=sec_user_agent,
        )

        if error:

            print(
                f"{ticker}: FAILED {error}"
            )

            continue

        try:

            data = json.loads(
                body.decode(
                    "utf-8"
                )
            )

            recent = (
                data
                .get(
                    "filings",
                    {}
                )
                .get(
                    "recent",
                    {}
                )
            )

            forms = recent.get(
                "form",
                []
            )

            accession_numbers = (
                recent.get(
                    "accessionNumber",
                    []
                )
            )

            filing_dates = (
                recent.get(
                    "filingDate",
                    []
                )
            )

            primary_documents = (
                recent.get(
                    "primaryDocument",
                    []
                )
            )

            for i, form in enumerate(
                forms
            ):

                if form not in (
                    SEC_ALLOWED_FORMS
                ):
                    continue

                filing_date = (
                    filing_dates[i]
                    if i < len(
                        filing_dates
                    )
                    else ""
                )

                accession = (
                    accession_numbers[i]
                    if i < len(
                        accession_numbers
                    )
                    else ""
                )

                document = (
                    primary_documents[i]
                    if i < len(
                        primary_documents
                    )
                    else ""
                )

                if (
                    not filing_date
                    or not accession
                ):
                    continue

                accession_clean = (
                    accession.replace(
                        "-",
                        "",
                    )
                )

                filing_url = (
                    "https://www.sec.gov/"
                    "Archives/edgar/data/"
                    f"{int(cik)}/"
                    f"{accession_clean}/"
                    f"{document}"
                )

                title = (
                    f"{ticker} {form} filing "
                    f"dated {filing_date}"
                )

                rows.append(
                    {
                        "title": title,
                        "description": (
                            f"SEC {form} filing "
                            f"for {ticker}"
                        ),
                        "published_at": (
                            parse_datetime(
                                filing_date
                            )
                        ),
                        "url": filing_url,
                        "topic": "market",
                        "source": "SEC",
                        "source_type": "SEC",
                    }
                )

        except Exception as exc:

            print(
                f"{ticker}: parse failure "
                f"{repr(exc)}"
            )

    print(
        f"SEC rows collected: "
        f"{len(rows)}"
    )

    return {
        "ok": len(rows) > 0,
        "rows": rows,
        "skipped": False,
        "error": None,
    }


# ============================================================
# NORMALIZATION
# ============================================================

def normalize_dataset(
    rows: List[
        Dict[str, Any]
    ],
) -> pd.DataFrame:

    normalized = []

    for row in rows:

        title = clean(
            row.get("title")
        )

        description = clean(
            row.get("description")
        )

        # IMPORTANT:
        # Normalize URLs before creating IDs.
        url = normalize_url(
            row.get("url")
        )

        published_at = parse_datetime(
            row.get("published_at")
        )

        if not title:
            continue

        if not url:
            continue

        if not published_at:
            continue

        source = clean(
            row.get("source")
        ) or "UNKNOWN"

        source_type = clean(
            row.get("source_type")
        ) or "UNKNOWN"

        topic = clean(
            row.get("topic")
        )

        if topic not in {
            "fed",
            "inflation",
            "labor",
            "growth",
            "market",
            "energy",
            "geopolitical",
        }:

            topic = classify_topic(
                title,
                description,
                "market",
            )

        event_id = make_id(
            source,
            published_at,
            title,
            url,
        )

        normalized.append(
            {
                "event_id": event_id,
                "source_type": source_type,
                "source": source,
                "topic": topic,
                "published_at": published_at,
                "availability_date": (
                    published_at
                ),
                "title": title,
                "url": url,
                "language": "en",
                "country": "US",
                "tone": infer_tone(
                    title
                ),
                "topic_relevance_title": (
                    title_relevance(
                        title
                    )
                ),
                "point_in_time_safe": True,
            }
        )

    if not normalized:

        return pd.DataFrame(
            columns=REQUIRED_COLUMNS
        )

    df = pd.DataFrame(
        normalized
    )

    # Remove exact duplicate event IDs.
    df = df.drop_duplicates(
        subset=[
            "event_id"
        ]
    )

    # Final URL normalization safety pass.
    df["url"] = (
        df["url"]
        .apply(normalize_url)
    )

    df = df.sort_values(
        by=[
            "published_at",
            "source",
            "title",
        ],
        ascending=[
            False,
            True,
            True,
        ],
    )

    return df.reset_index(
        drop=True
    )


# ============================================================
# VALIDATION
# ============================================================

def validate(
    df: pd.DataFrame,
    gdelt_result: Dict[str, Any],
    rss_result: Dict[str, Any],
    sec_result: Dict[str, Any],
) -> Dict[str, Any]:

    errors = []
    warnings = []

    # --------------------------------------------------------
    # Required columns
    # --------------------------------------------------------

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing_columns:

        errors.append(
            {
                "check": (
                    "required_columns"
                ),
                "pass": False,
                "detail": (
                    f"missing="
                    f"{missing_columns}"
                ),
            }
        )

    else:

        errors.append(
            {
                "check": (
                    "required_columns"
                ),
                "pass": True,
                "detail": (
                    "all_required_columns_present"
                ),
            }
        )

    # --------------------------------------------------------
    # Minimum rows
    # --------------------------------------------------------

    row_count = len(df)

    if row_count < MIN_TOTAL_ROWS:

        errors.append(
            {
                "check": (
                    "minimum_dataset_rows"
                ),
                "pass": False,
                "detail": (
                    f"rows={row_count}; "
                    f"minimum="
                    f"{MIN_TOTAL_ROWS}"
                ),
            }
        )

    else:

        errors.append(
            {
                "check": (
                    "minimum_dataset_rows"
                ),
                "pass": True,
                "detail": (
                    f"rows={row_count}"
                ),
            }
        )

    # --------------------------------------------------------
    # Unique IDs
    # --------------------------------------------------------

    if "event_id" in df.columns:

        unique_ids = (
            df["event_id"]
            .astype(str)
            .nunique()
        )

        if unique_ids != row_count:

            errors.append(
                {
                    "check": (
                        "unique_event_ids"
                    ),
                    "pass": False,
                    "detail": (
                        f"rows={row_count}; "
                        f"unique_ids="
                        f"{unique_ids}"
                    ),
                }
            )

        else:

            errors.append(
                {
                    "check": (
                        "unique_event_ids"
                    ),
                    "pass": True,
                    "detail": (
                        f"unique_ids="
                        f"{unique_ids}"
                    ),
                }
            )

    # --------------------------------------------------------
    # Timestamps
    # --------------------------------------------------------

    if "published_at" in df.columns:

        parsed = pd.to_datetime(
            df["published_at"],
            utc=True,
            errors="coerce",
        )

        bad = int(
            parsed.isna().sum()
        )

        if bad:

            errors.append(
                {
                    "check": "timestamps",
                    "pass": False,
                    "detail": (
                        f"invalid_timestamps="
                        f"{bad}"
                    ),
                }
            )

        else:

            errors.append(
                {
                    "check": "timestamps",
                    "pass": True,
                    "detail": (
                        "all_timestamps_parseable"
                    ),
                }
            )

    # --------------------------------------------------------
    # URLs
    # --------------------------------------------------------

    if "url" in df.columns:

        normalized_urls = (
            df["url"]
            .astype(str)
            .apply(normalize_url)
        )

        bad_urls = int(
            (
                ~normalized_urls.str.startswith(
                    (
                        "http://",
                        "https://",
                    )
                )
            ).sum()
        )

        if bad_urls:

            errors.append(
                {
                    "check": "urls",
                    "pass": False,
                    "detail": (
                        f"invalid_urls="
                        f"{bad_urls}"
                    ),
                }
            )

        else:

            errors.append(
                {
                    "check": "urls",
                    "pass": True,
                    "detail": (
                        "all_urls_valid"
                    ),
                }
            )

    # --------------------------------------------------------
    # PIT safety
    # --------------------------------------------------------

    if "point_in_time_safe" in df.columns:

        invalid_pit = int(
            (
                df[
                    "point_in_time_safe"
                ]
                != True
            ).sum()
        )

        if invalid_pit:

            errors.append(
                {
                    "check": (
                        "point_in_time_safe"
                    ),
                    "pass": False,
                    "detail": (
                        f"invalid_rows="
                        f"{invalid_pit}"
                    ),
                }
            )

        else:

            errors.append(
                {
                    "check": (
                        "point_in_time_safe"
                    ),
                    "pass": True,
                    "detail": (
                        "all_rows_marked_"
                        "point_in_time_safe"
                    ),
                }
            )

    # --------------------------------------------------------
    # Topic coverage
    # --------------------------------------------------------

    if "topic" in df.columns:

        covered = sorted(
            set(
                df["topic"]
                .dropna()
                .astype(str)
            ).intersection(
                CORE_TOPICS
            )
        )

    else:

        covered = []

    if (
        len(covered)
        >= MIN_TOPIC_FAMILIES_FOR_FULL_COVERAGE
    ):

        coverage_level = "FULL"

    else:

        coverage_level = "PARTIAL"

    warnings.append(
        {
            "check": (
                "core_topic_coverage"
            ),
            "detail": (
                f"covered={covered}; "
                f"level={coverage_level}; "
                f"minimum_for_full="
                f"{MIN_TOPIC_FAMILIES_FOR_FULL_COVERAGE}"
            ),
        }
    )

    # --------------------------------------------------------
    # GDELT availability
    # --------------------------------------------------------

    if not gdelt_result.get(
        "ok"
    ):

        warnings.append(
            {
                "check": (
                    "gdelt_collection"
                ),
                "detail": (
                    "GDELT unavailable; "
                    "official sources used "
                    "as fallback."
                ),
            }
        )

    # --------------------------------------------------------
    # Official RSS availability
    # --------------------------------------------------------

    if not rss_result.get(
        "ok"
    ):

        warnings.append(
            {
                "check": (
                    "official_rss_collection"
                ),
                "detail": (
                    "No official RSS source "
                    "returned data."
                ),
            }
        )

    else:

        failed_feeds = [
            name
            for name, result
            in rss_result.get(
                "feeds",
                {},
            ).items()
            if not result.get(
                "ok"
            )
        ]

        if failed_feeds:

            warnings.append(
                {
                    "check": (
                        "official_rss_partial"
                    ),
                    "detail": (
                        f"failed_feeds="
                        f"{failed_feeds}"
                    ),
                }
            )

    # --------------------------------------------------------
    # SEC
    # --------------------------------------------------------

    if sec_result.get(
        "skipped"
    ):

        warnings.append(
            {
                "check": (
                    "sec_collection"
                ),
                "detail": (
                    "SEC skipped because "
                    "SEC_USER_AGENT was "
                    "not configured."
                ),
            }
        )

    # --------------------------------------------------------
    # Structural status
    # --------------------------------------------------------

    hard_failures = [
        item
        for item in errors
        if item.get("pass") is False
    ]

    validation_pass = (
        len(hard_failures) == 0
    )

    status = (
        "PASS"
        if validation_pass
        else "FAIL"
    )

    # --------------------------------------------------------
    # Counts
    # --------------------------------------------------------

    topic_counts = {}

    if "topic" in df.columns:

        topic_counts = {
            str(k): int(v)
            for k, v in (
                df["topic"]
                .value_counts()
                .to_dict()
                .items()
            )
        }

    source_counts = {}

    if "source_type" in df.columns:

        source_counts = {
            str(k): int(v)
            for k, v in (
                df["source_type"]
                .value_counts()
                .to_dict()
                .items()
            )
        }

    return {
        "validator": (
            "Event / News Intelligence v2.1"
        ),
        "version": VERSION,
        "status": status,
        "validation_pass": validation_pass,
        "generated_at": utc_now_iso(),
        "rows": row_count,
        "source_counts": source_counts,
        "topic_counts": topic_counts,
        "coverage_level": coverage_level,
        "gdelt": {
            "ok": bool(
                gdelt_result.get(
                    "ok"
                )
            ),
            "rows": len(
                gdelt_result.get(
                    "rows",
                    [],
                )
            ),
            "error": gdelt_result.get(
                "error"
            ),
            "query_requests": (
                gdelt_result.get(
                    "query_requests",
                    0,
                )
            ),
            "fallback_required": (
                gdelt_result.get(
                    "fallback_required",
                    False,
                )
            ),
        },
        "official_rss": rss_result,
        "sec": {
            "ok": bool(
                sec_result.get(
                    "ok"
                )
            ),
            "rows": len(
                sec_result.get(
                    "rows",
                    [],
                )
            ),
            "skipped": bool(
                sec_result.get(
                    "skipped",
                    False,
                )
            ),
            "error": sec_result.get(
                "error"
            ),
        },
        "errors": errors,
        "warnings": warnings,
        **RESEARCH_ONLY_FLAGS,
        "interpretation": (
            "Validation is structural and "
            "data-quality validation only. "
            "Event/news coverage is descriptive "
            "and does not establish causality, "
            "predictiveness, trading usefulness, "
            "or investment preference."
        ),
    }


# ============================================================
# SUMMARY
# ============================================================

def build_summary(
    df: pd.DataFrame,
    validation: Dict[str, Any],
) -> Dict[str, Any]:

    return {
        "module": (
            "Event / News Intelligence"
        ),
        "version": VERSION,
        "generated_at": utc_now_iso(),
        "rows": int(
            len(df)
        ),
        "source_counts": (
            validation.get(
                "source_counts",
                {},
            )
        ),
        "topic_counts": (
            validation.get(
                "topic_counts",
                {},
            )
        ),
        "coverage_level": (
            validation.get(
                "coverage_level"
            )
        ),
        **RESEARCH_ONLY_FLAGS,
    }


# ============================================================
# MAIN
# ============================================================

def main() -> int:

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default=(
            "event_news_intelligence_v1"
        ),
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

    print(
        "\n"
        + "=" * 72
    )

    print(
        "EVENT / NEWS INTELLIGENCE v2.1"
    )

    print(
        "=" * 72
    )

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

    print(
        f"Version: {VERSION}"
    )

    # --------------------------------------------------------
    # GDELT
    # --------------------------------------------------------

    gdelt_result = collect_gdelt()

    # --------------------------------------------------------
    # Official RSS
    # --------------------------------------------------------

    rss_result = collect_official_rss()

    # --------------------------------------------------------
    # SEC
    # --------------------------------------------------------

    sec_result = collect_sec()

    # --------------------------------------------------------
    # Merge
    # --------------------------------------------------------

    raw_rows = []

    raw_rows.extend(
        gdelt_result.get(
            "rows",
            [],
        )
    )

    raw_rows.extend(
        rss_result.get(
            "rows",
            [],
        )
    )

    raw_rows.extend(
        sec_result.get(
            "rows",
            [],
        )
    )

    print(
        "\n"
        + "=" * 72
    )

    print(
        "NORMALIZATION"
    )

    print(
        "=" * 72
    )

    df = normalize_dataset(
        raw_rows
    )

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    validation = validate(
        df,
        gdelt_result,
        rss_result,
        sec_result,
    )

    summary = build_summary(
        df,
        validation,
    )

    # --------------------------------------------------------
    # Output paths
    # --------------------------------------------------------

    dataset_path = (
        output_dir
        / "event_news_research_v2.csv"
    )

    validation_path = (
        output_dir
        / "event_news_validation_v2.json"
    )

    summary_path = (
        output_dir
        / "event_news_research_summary_v2.json"
    )

    # --------------------------------------------------------
    # Save CSV
    # --------------------------------------------------------

    df.to_csv(
        dataset_path,
        index=False,
    )

    # --------------------------------------------------------
    # Save validation
    # --------------------------------------------------------

    validation_path.write_text(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Save summary
    # --------------------------------------------------------

    summary_path.write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # Validation report
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 72
    )

    print(
        "VALIDATION RESULT"
    )

    print(
        "=" * 72
    )

    print(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        )
    )

    # --------------------------------------------------------
    # Dataset summary
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 72
    )

    print(
        "DATASET SUMMARY"
    )

    print(
        "=" * 72
    )

    print(
        f"rows={len(df)}"
    )

    print(
        "source_counts="
        + json.dumps(
            validation.get(
                "source_counts",
                {},
            ),
            sort_keys=True,
        )
    )

    print(
        "topic_counts="
        + json.dumps(
            validation.get(
                "topic_counts",
                {},
            ),
            sort_keys=True,
        )
    )

    print(
        f"coverage_level="
        f"{validation.get('coverage_level')}"
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

    # --------------------------------------------------------
    # Execution summary
    # --------------------------------------------------------

    print(
        "\n"
        + "=" * 72
    )

    print(
        "EXECUTION SUMMARY"
    )

    print(
        "=" * 72
    )

    print(
        "GDELT rows:",
        len(
            gdelt_result.get(
                "rows",
                [],
            )
        ),
    )

    print(
        "Official RSS rows:",
        len(
            rss_result.get(
                "rows",
                [],
            )
        ),
    )

    print(
        "SEC rows:",
        len(
            sec_result.get(
                "rows",
                [],
            )
        ),
    )

    print(
        "Total rows:",
        len(df),
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
    # Final status
    # --------------------------------------------------------

    if validation[
        "validation_pass"
    ]:

        print(
            "\n"
            "EVENT / NEWS INTELLIGENCE "
            "v2.1 VALIDATION: PASS"
        )

        return 0

    print(
        "\n"
        "EVENT / NEWS INTELLIGENCE "
        "v2.1 VALIDATION: FAIL"
    )

    return 1


if __name__ == "__main__":
    sys.exit(
        main()
    )
