#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd


# ============================================================
# Event / News Intelligence v1
# ============================================================
#
# Research-only
# No Decision Engine
# No trading signals
# No forecasting
#
# Sources:
#   1. GDELT DOC 2.0 Article List
#   2. SEC EDGAR Submissions API
#
# ============================================================


GDELT_URL = (
    "https://api.gdeltproject.org/api/v2/doc/doc"
)

SEC_SUBMISSIONS = (
    "https://data.sec.gov/submissions/CIK{cik}.json"
)


# ============================================================
# Configuration
# ============================================================

HTTP_TIMEOUT_SECONDS = 30

# GDELT rate limiting / retry configuration
GDELT_RETRIES = 7
GDELT_BACKOFF_SECONDS = 5.0
GDELT_MAX_BACKOFF_SECONDS = 90.0

# Delay between GDELT topic requests
GDELT_PACING_SECONDS = 8.0

# SEC pacing
SEC_PACING_SECONDS = 1.0
SEC_RETRIES = 4

# GDELT article list
GDELT_MAX_RECORDS = 100
GDELT_TIMESPAN = "3months"

# Minimum GDELT topic coverage required for PASS.
# SEC is supplementary and does not determine PASS.
MIN_GDELT_TOPICS = 4

# Minimum title relevance among returned GDELT rows.
MIN_GDELT_TITLE_RELEVANCE = 0.30


# ============================================================
# SEC universe
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


# ============================================================
# GDELT research topics
# ============================================================

GDELT_QUERIES = {
    "fed": (
        '("Federal Reserve" OR FOMC OR "Fed Chair" OR Powell) '
        "(rates OR policy OR inflation OR meeting)"
    ),

    "inflation": (
        '(CPI OR "consumer price index" OR PPI '
        'OR "producer price index") '
        "(inflation OR prices OR Federal Reserve)"
    ),

    "labor": (
        '("nonfarm payrolls" OR "jobless claims" '
        'OR unemployment OR employment) '
        '(US OR U.S. OR "United States")'
    ),

    "growth": (
        '(GDP OR "economic growth" OR PMI OR ISM OR recession) '
        '("United States" OR US OR U.S.)'
    ),

    "market": (
        '("S&P 500" OR SP500 OR "US stocks" OR equities) '
        "(market OR index OR trading OR earnings)"
    ),

    "geopolitical": (
        '(tariff OR tariffs OR sanctions OR "trade war" '
        'OR conflict OR ceasefire) '
        '(US OR U.S. OR America)'
    ),

    "energy": (
        '(oil OR crude OR OPEC OR gasoline OR energy) '
        '(US OR U.S. OR prices OR supply)'
    ),
}


TOPIC_TERMS = {
    "fed": [
        "federal reserve",
        "fomc",
        "powell",
        "interest rate",
        "interest rates",
    ],

    "inflation": [
        "inflation",
        "cpi",
        "ppi",
        "consumer prices",
        "producer prices",
    ],

    "labor": [
        "nonfarm payrolls",
        "employment",
        "unemployment",
        "jobless claims",
        "jobs",
    ],

    "growth": [
        "gdp",
        "recession",
        "economic growth",
        "pmi",
        "ism",
    ],

    "market": [
        "s&p 500",
        "sp500",
        "equities",
        "stocks",
        "volatility",
        "wall street",
    ],

    "geopolitical": [
        "war",
        "sanctions",
        "tariff",
        "tariffs",
        "conflict",
        "ceasefire",
    ],

    "energy": [
        "oil",
        "crude oil",
        "opec",
        "gasoline",
        "energy",
        "fuel",
    ],
}


# ============================================================
# Time / ID helpers
# ============================================================

def sha_id(*parts: str, length: int = 24) -> str:
    raw = "|".join(str(x or "") for x in parts)
    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:length]


# ============================================================
# HTTP helpers
# ============================================================

def base_headers(user_agent: str) -> dict:
    return {
        "User-Agent": user_agent,
        "Accept": "application/json",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "close",
    }


def calculate_backoff(
    attempt: int,
    retry_after: str | None = None,
    base: float = GDELT_BACKOFF_SECONDS,
) -> float:
    """
    Exponential backoff + jitter.

    Retry-After is preferred when supplied by the server.
    """

    if retry_after:
        try:
            seconds = float(retry_after)
            return min(
                max(seconds, 1.0),
                GDELT_MAX_BACKOFF_SECONDS,
            )
        except (TypeError, ValueError):
            pass

    delay = base * (2 ** attempt)

    jitter = random.uniform(
        0.0,
        2.0,
    )

    return min(
        delay + jitter,
        GDELT_MAX_BACKOFF_SECONDS,
    )


def http_json(
    url: str,
    *,
    user_agent: str,
    retries: int,
    backoff_base: float,
    max_backoff: float,
    source_name: str,
):
    """
    Robust JSON HTTP client.

    Specifically handles:
      - HTTP 429
      - HTTP 5xx
      - HTTP 408
      - network failures
      - empty response
      - non-JSON response
    """

    headers = base_headers(user_agent)

    last_error = None
    last_status = None

    for attempt in range(retries):

        try:

            request = Request(
                url,
                headers=headers,
                method="GET",
            )

            with urlopen(
                request,
                timeout=HTTP_TIMEOUT_SECONDS,
            ) as response:

                status_code = getattr(
                    response,
                    "status",
                    200,
                )

                body = response.read()

                if not body:
                    raise ValueError(
                        f"{source_name}: empty response body"
                    )

                text = body.decode(
                    "utf-8",
                    errors="replace",
                ).strip()

                if not text:
                    raise ValueError(
                        f"{source_name}: empty response text"
                    )

                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{source_name}: invalid JSON response: "
                        f"{exc}"
                    ) from exc

                return payload, {
                    "ok": True,
                    "status": status_code,
                    "attempts": attempt + 1,
                    "error": None,
                }

        except HTTPError as exc:

            last_status = exc.code
            last_error = (
                f"HTTP {exc.code}: {exc.reason}"
            )

            retryable = exc.code in {
                408,
                429,
                500,
                502,
                503,
                504,
            }

            if not retryable:
                return None, {
                    "ok": False,
                    "status": exc.code,
                    "attempts": attempt + 1,
                    "error": last_error,
                }

            if attempt >= retries - 1:
                break

            retry_after = None

            try:
                retry_after = exc.headers.get(
                    "Retry-After"
                )
            except Exception:
                pass

            delay = calculate_backoff(
                attempt,
                retry_after,
                backoff_base,
            )

            # Respect configured maximum.
            delay = min(
                delay,
                max_backoff,
            )

            print(
                f"[WARN] {source_name}: "
                f"{last_error}; "
                f"retry {attempt + 1}/{retries - 1} "
                f"in {delay:.1f}s"
            )

            time.sleep(delay)

        except (
            URLError,
            TimeoutError,
            ValueError,
        ) as exc:

            last_error = str(exc)

            if attempt >= retries - 1:
                break

            delay = min(
                calculate_backoff(
                    attempt,
                    None,
                    backoff_base,
                ),
                max_backoff,
            )

            print(
                f"[WARN] {source_name}: "
                f"temporary error; "
                f"retry {attempt + 1}/{retries - 1} "
                f"in {delay:.1f}s: "
                f"{last_error}"
            )

            time.sleep(delay)

    return None, {
        "ok": False,
        "status": last_status,
        "attempts": retries,
        "error": last_error or "request failed",
    }


# ============================================================
# GDELT
# ============================================================

def gdelt_articles(
    topic: str,
    query: str,
):
    params = {
        "query": f"({query})",
        "mode": "artlist",
        "format": "json",
        "maxrecords": GDELT_MAX_RECORDS,
        "timespan": GDELT_TIMESPAN,
        "sort": "datedesc",
    }

    url = (
        GDELT_URL
        + "?"
        + urlencode(params)
    )

    data, status = http_json(
        url,
        user_agent=(
            "US500-Macro-Intelligence/1.0 "
            "research-only; "
            "https://github.com/"
            "mohamednossaoui-max/"
            "US500-Macro-Intelligence"
        ),
        retries=GDELT_RETRIES,
        backoff_base=GDELT_BACKOFF_SECONDS,
        max_backoff=GDELT_MAX_BACKOFF_SECONDS,
        source_name=f"GDELT:{topic}",
    )

    if not status["ok"]:
        return [], status

    if not isinstance(data, dict):
        return [], {
            **status,
            "ok": False,
            "error": (
                "GDELT response is not a JSON object"
            ),
        }

    articles = data.get(
        "articles",
        [],
    )

    if not isinstance(articles, list):
        return [], {
            **status,
            "ok": False,
            "error": (
                "GDELT 'articles' field is not a list"
            ),
        }

    return articles, {
        **status,
        "raw_rows": len(articles),
    }


def parse_gdelt_datetime(value):
    if value is None:
        return pd.NaT

    text = str(value).strip()

    if not text:
        return pd.NaT

    # Standard GDELT seendate:
    # YYYYMMDDTHHMMSSZ
    dt = pd.to_datetime(
        text,
        format="%Y%m%dT%H%M%SZ",
        utc=True,
        errors="coerce",
    )

    if pd.notna(dt):
        return dt

    return pd.to_datetime(
        text,
        utc=True,
        errors="coerce",
    )


def title_relevant(
    title: str,
    topic: str,
) -> bool:

    text = str(title).lower()

    return any(
        term in text
        for term in TOPIC_TERMS[topic]
    )


def normalize_gdelt(
    rows: list,
    topic: str,
):
    output = []

    for row in rows:

        url = str(
            row.get("url") or ""
        ).strip()

        title = str(
            row.get("title") or ""
        ).strip()

        if not url:
            continue

        if not title:
            continue

        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        published = parse_gdelt_datetime(
            row.get("seendate")
        )

        if pd.isna(published):
            continue

        event_id = sha_id(
            "GDELT",
            url,
        )

        output.append(
            {
                "event_id": event_id,
                "source_type": "GDELT",
                "source": str(
                    row.get("domain") or ""
                ).strip(),
                "topic": topic,
                "published_at": published.isoformat(),
                "availability_date": (
                    published.date().isoformat()
                ),
                "title": title,
                "url": url,
                "language": str(
                    row.get("language") or ""
                ).strip(),
                "country": str(
                    row.get("sourcecountry") or ""
                ).strip(),
                "tone": pd.to_numeric(
                    row.get("tone"),
                    errors="coerce",
                ),
                "topic_relevance_title": (
                    title_relevant(
                        title,
                        topic,
                    )
                ),
                "point_in_time_safe": True,
            }
        )

    return output


# ============================================================
# SEC
# ============================================================

def get_sec_user_agent() -> tuple[str, bool]:
    """
    SEC recommends a declared User-Agent with contact information.

    Prefer the GitHub secret SEC_USER_AGENT.

    If absent, use a clearly identified research client string.
    The absence of the secret is reported as a warning, not a
    pipeline failure.
    """

    configured = os.getenv(
        "SEC_USER_AGENT",
        "",
    ).strip()

    if configured:
        return configured, True

    return (
        "US500-Macro-Intelligence/1.0 "
        "(research-only; "
        "github.com/mohamednossaoui-max/"
        "US500-Macro-Intelligence)",
        False,
    )


def fetch_sec(
    ticker: str,
    cik: str,
):
    user_agent, declared = get_sec_user_agent()

    data, status = http_json(
        SEC_SUBMISSIONS.format(
            cik=cik
        ),
        user_agent=user_agent,
        retries=SEC_RETRIES,
        backoff_base=3.0,
        max_backoff=30.0,
        source_name=f"SEC:{ticker}",
    )

    if not status["ok"]:
        return [], {
            **status,
            "user_agent_configured": declared,
            "rows": 0,
        }

    if not isinstance(data, dict):
        return [], {
            **status,
            "ok": False,
            "error": (
                "SEC response is not a JSON object"
            ),
            "user_agent_configured": declared,
            "rows": 0,
        }

    recent = (
        data.get("filings", {})
        .get("recent", {})
    )

    if not isinstance(recent, dict):
        return [], {
            **status,
            "ok": False,
            "error": (
                "SEC recent filings object missing"
            ),
            "user_agent_configured": declared,
            "rows": 0,
        }

    forms = recent.get(
        "form",
        [],
    )

    filing_dates = recent.get(
        "filingDate",
        [],
    )

    accessions = recent.get(
        "accessionNumber",
        [],
    )

    documents = recent.get(
        "primaryDocument",
        [],
    )

    acceptance_times = recent.get(
        "acceptanceDateTime",
        [],
    )

    n = len(forms)

    output = []

    allowed_forms = {
        "8-K",
        "10-Q",
        "10-K",
        "10-Q/A",
        "10-K/A",
    }

    for i in range(n):

        form = (
            forms[i]
            if i < len(forms)
            else ""
        )

        if form not in allowed_forms:
            continue

        accession = (
            accessions[i]
            if i < len(accessions)
            else ""
        ) or ""

        document = (
            documents[i]
            if i < len(documents)
            else ""
        ) or ""

        acceptance = (
            acceptance_times[i]
            if i < len(acceptance_times)
            else ""
        ) or ""

        filing_date = (
            filing_dates[i]
            if i < len(filing_dates)
            else ""
        ) or ""

        published = (
            acceptance
            or filing_date
        )

        if not published:
            continue

        accession_clean = (
            str(accession)
            .replace("-", "")
        )

        document_url = ""

        if document and accession_clean:
            try:
                cik_int = str(
                    int(cik)
                )
                document_url = (
                    "https://www.sec.gov/"
                    "Archives/edgar/data/"
                    f"{cik_int}/"
                    f"{accession_clean}/"
                    f"{document}"
                )
            except ValueError:
                document_url = ""

        event_id = sha_id(
            "SEC",
            ticker,
            accession,
            form,
        )

        output.append(
            {
                "event_id": event_id,
                "source_type": "SEC",
                "source": "SEC EDGAR",
                "topic": "corporate_filing",
                "published_at": published,
                "availability_date": (
                    str(published)[:10]
                ),
                "title": (
                    f"{ticker} {form}"
                ),
                "url": document_url,
                "language": "en",
                "country": "US",
                "tone": np.nan,
                "ticker": ticker,
                "form": form,
                "topic_relevance_title": True,
                "point_in_time_safe": True,
            }
        )

    return output, {
        **status,
        "user_agent_configured": declared,
        "rows": len(output),
    }


# ============================================================
# Validation
# ============================================================

def validate(
    df: pd.DataFrame,
    output: Path,
    query_status: dict,
    sec_status: dict,
):
    checks = []

    def add(
        name: str,
        passed: bool,
        detail: str = "",
    ):
        checks.append(
            {
                "check": name,
                "pass": bool(passed),
                "detail": detail,
            }
        )

    required = [
        "event_id",
        "source_type",
        "source",
        "topic",
        "published_at",
        "availability_date",
        "title",
        "url",
    ]

    missing = [
        column
        for column in required
        if column not in df.columns
    ]

    add(
        "required_columns",
        not missing,
        str(missing),
    )

    add(
        "unique_event_ids",
        len(df) > 0
        and df.event_id.nunique()
        == len(df),
        f"rows={len(df)}",
    )

    if len(df):

        published = pd.to_datetime(
            df.published_at,
            utc=True,
            errors="coerce",
        )

        add(
            "published_timestamps_parse",
            bool(
                published.notna().all()
            ),
            "",
        )

        add(
            "point_in_time_safe",
            bool(
                df.point_in_time_safe
                .fillna(False)
                .all()
            ),
            "",
        )

        valid_urls = (
            df.url.astype(str)
            .str.startswith(
                (
                    "http://",
                    "https://",
                )
            )
        )

        # SEC can occasionally have no document URL
        # in the returned metadata. For GDELT, URLs are required.
        gdelt_df = df[
            df.source_type == "GDELT"
        ]

        gdelt_urls_valid = (
            len(gdelt_df) > 0
            and gdelt_df.url.astype(str)
            .str.startswith(
                (
                    "http://",
                    "https://",
                )
            )
            .all()
        )

        sec_df = df[
            df.source_type == "SEC"
        ]

        sec_url_ok = (
            len(sec_df) == 0
            or sec_df.url.astype(str)
            .str.startswith(
                (
                    "http://",
                    "https://",
                )
            )
            .all()
        )

        add(
            "urls_valid",
            bool(
                gdelt_urls_valid
                and sec_url_ok
            ),
            "",
        )

    else:

        add(
            "published_timestamps_parse",
            False,
            "",
        )

        add(
            "point_in_time_safe",
            False,
            "",
        )

        add(
            "urls_valid",
            False,
            "",
        )

    add(
        "known_sources_only",
        len(df) == 0
        or set(
            df.source_type
            .dropna()
            .unique()
        ).issubset(
            {
                "GDELT",
                "SEC",
            }
        ),
        "",
    )

    # --------------------------------------------------------
    # GDELT
    # --------------------------------------------------------

    gdelt = (
        df[
            df.source_type == "GDELT"
        ]
        if len(df)
        else df
    )

    topic_counts = (
        gdelt.topic
        .value_counts()
        .to_dict()
        if len(gdelt)
        else {}
    )

    topics_present = set(
        topic_counts
    )

    add(
        "gdelt_topics_covered",
        len(topics_present)
        >= MIN_GDELT_TOPICS,
        json.dumps(
            topic_counts,
            sort_keys=True,
        ),
    )

    if len(gdelt):
        relevance = float(
            gdelt.topic_relevance_title
            .fillna(False)
            .mean()
        )
    else:
        relevance = 0.0

    add(
        "gdelt_title_relevance",
        relevance
        >= MIN_GDELT_TITLE_RELEVANCE,
        (
            f"relevant_pct="
            f"{relevance * 100:.2f}"
        ),
    )

    successful_topics = sum(
        1
        for status in query_status.values()
        if status.get("ok", False)
    )

    add(
        "query_execution_visible",
        successful_topics
        >= MIN_GDELT_TOPICS,
        (
            f"successful_topics="
            f"{successful_topics}/"
            f"{len(GDELT_QUERIES)}; "
            f"{json.dumps(query_status, sort_keys=True)}"
        ),
    )

    # --------------------------------------------------------
    # SEC
    # --------------------------------------------------------

    sec = (
        df[
            df.source_type == "SEC"
        ]
        if len(df)
        else df
    )

    sec_successful = sum(
        1
        for status in sec_status.values()
        if status.get("ok", False)
    )

    # SEC is supplementary.
    # Its failure must be visible but does not fail validation.
    add(
        "sec_execution_visible",
        True,
        (
            f"successful_tickers="
            f"{sec_successful}/"
            f"{len(SEC_UNIVERSE)}; "
            "informational-only; "
            "SEC access failures do not invalidate "
            "the GDELT research dataset; "
            f"{json.dumps(sec_status, sort_keys=True)}"
        ),
    )

    add(
        "sec_events_present",
        True,
        (
            f"sec_rows={len(sec)}; "
            "informational-only"
        ),
    )

    # --------------------------------------------------------
    # Research-only guards
    # --------------------------------------------------------

    if len(df):

        research_columns = {
            "research_only": True,
            "decision_engine_ready": False,
            "trading_signal": False,
            "forecast": False,
            "pit_perfect": False,
            "point_in_time_reconstructed": False,
        }

        research_ok = True

        for column, expected in (
            research_columns.items()
        ):
            if column not in df.columns:
                research_ok = False
                break

            if expected:
                if not bool(
                    df[column].all()
                ):
                    research_ok = False
                    break
            else:
                if bool(
                    df[column].any()
                ):
                    research_ok = False
                    break

    else:
        research_ok = True

    add(
        "research_only_guards",
        research_ok,
        (
            "research_only=true; "
            "Decision Engine disabled; "
            "no trading signal; "
            "no forecast"
        ),
    )

    errors = [
        check
        for check in checks
        if not check["pass"]
    ]

    warnings = [
        (
            "GDELT DOC Article List coverage is "
            "rolling and is not a complete historical "
            "news archive."
        ),
        (
            "SEC universe is a fixed research sample; "
            "it is not point-in-time S&P 500 membership."
        ),
        (
            "SEC execution is supplementary. "
            "Hosted CI may receive 403 responses; "
            "such failures remain visible in sec_status "
            "and do not invalidate GDELT coverage."
        ),
        (
            "Title relevance is a conservative semantic "
            "sanity check and does not establish "
            "article-level factual relevance."
        ),
    ]

    report = {
        "validator": (
            "Event / News Intelligence v1"
        ),
        "status": (
            "PASS"
            if not errors
            else "FAIL"
        ),
        "validation_pass": not bool(
            errors
        ),
        "errors": errors,
        "warnings": warnings,
        "checks": checks,
        "rows": int(len(df)),
        "date_start": (
            str(
                df.availability_date.min()
            )
            if len(df)
            else None
        ),
        "date_end": (
            str(
                df.availability_date.max()
            )
            if len(df)
            else None
        ),
        "source_counts": (
            df.source_type
            .value_counts()
            .to_dict()
            if len(df)
            else {}
        ),
        "topic_counts": (
            df.topic
            .value_counts()
            .to_dict()
            if len(df)
            else {}
        ),
        "query_status": query_status,
        "sec_status": sec_status,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "point_in_time_reconstructed": False,
        "interpretation": (
            "PASS is structural/data-quality "
            "validation only. News coverage and "
            "filing activity are descriptive and "
            "do not establish causality, "
            "predictiveness, trading usefulness, "
            "or preference."
        ),
    }

    (
        output
        / "event_news_validation_v1.json"
    ).write_text(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return report


# ============================================================
# Main
# ============================================================

def main():

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--output",
        default="event_news_intelligence_v1",
    )

    args = parser.parse_args()

    output = Path(
        args.output
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "============================================================"
    )
    print(
        "Event / News Intelligence v1"
    )
    print(
        "GDELT + SEC"
    )
    print(
        "Research-only — No Decision Engine"
    )
    print(
        "============================================================"
    )

    records = []
    query_status = {}

    # ========================================================
    # GDELT
    # ========================================================

    print(
        "\n===== GDELT COLLECTION ====="
    )

    for index, (
        topic,
        query,
    ) in enumerate(
        GDELT_QUERIES.items()
    ):

        if index:
            print(
                f"[INFO] GDELT pacing: "
                f"{GDELT_PACING_SECONDS}s"
            )

            time.sleep(
                GDELT_PACING_SECONDS
            )

        print(
            f"[INFO] GDELT topic: {topic}"
        )

        try:

            rows, status = gdelt_articles(
                topic,
                query,
            )

            normalized = normalize_gdelt(
                rows,
                topic,
            )

            records.extend(
                normalized
            )

            query_status[topic] = {
                **status,
                "raw_rows": len(rows),
                "normalized_rows": len(
                    normalized
                ),
            }

            print(
                f"[INFO] {topic}: "
                f"ok={status.get('ok')} "
                f"raw={len(rows)} "
                f"normalized="
                f"{len(normalized)}"
            )

        except Exception as exc:

            query_status[topic] = {
                "ok": False,
                "raw_rows": 0,
                "normalized_rows": 0,
                "error": repr(exc),
            }

            print(
                f"[ERROR] GDELT {topic}: "
                f"{repr(exc)}"
            )

    # ========================================================
    # SEC
    # ========================================================

    print(
        "\n===== SEC COLLECTION ====="
    )

    sec_status = {}

    for index, (
        ticker,
        cik,
    ) in enumerate(
        SEC_UNIVERSE.items()
    ):

        if index:
            time.sleep(
                SEC_PACING_SECONDS
            )

        print(
            f"[INFO] SEC ticker: {ticker}"
        )

        try:

            rows, status = fetch_sec(
                ticker,
                cik,
            )

            records.extend(
                rows
            )

            sec_status[ticker] = status

            print(
                f"[INFO] SEC {ticker}: "
                f"ok={status.get('ok')} "
                f"rows={len(rows)} "
                f"status="
                f"{status.get('status')} "
                f"error="
                f"{status.get('error')}"
            )

        except Exception as exc:

            sec_status[ticker] = {
                "ok": False,
                "rows": 0,
                "error": repr(exc),
            }

            print(
                f"[ERROR] SEC {ticker}: "
                f"{repr(exc)}"
            )

    # ========================================================
    # Dataset
    # ========================================================

    df = pd.DataFrame(
        records
    )

    if len(df):

        df = (
            df.drop_duplicates(
                subset=["event_id"]
            )
            .sort_values(
                [
                    "availability_date",
                    "published_at",
                ],
                kind="stable",
            )
            .reset_index(
                drop=True
            )
        )

        # Explicit research-only guards
        df[
            "research_only"
        ] = True

        df[
            "decision_engine_ready"
        ] = False

        df[
            "trading_signal"
        ] = False

        df[
            "forecast"
        ] = False

        df[
            "pit_perfect"
        ] = False

        df[
            "point_in_time_reconstructed"
        ] = False

    else:

        df = pd.DataFrame(
            columns=[
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
                "ticker",
                "form",
                "topic_relevance_title",
                "point_in_time_safe",
                "research_only",
                "decision_engine_ready",
                "trading_signal",
                "forecast",
                "pit_perfect",
                "point_in_time_reconstructed",
            ]
        )

    # ========================================================
    # Artifacts
    # ========================================================

    research_csv = (
        output
        / "event_news_research_v1.csv"
    )

    df.to_csv(
        research_csv,
        index=False,
    )

    summary = {
        "rows": int(len(df)),
        "sources": (
            df.source_type
            .value_counts()
            .to_dict()
            if len(df)
            else {}
        ),
        "topics": (
            df.topic
            .value_counts()
            .to_dict()
            if len(df)
            else {}
        ),
        "query_status": query_status,
        "sec_status": sec_status,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "point_in_time_reconstructed": False,
    }

    (
        output
        / "event_news_research_summary_v1.json"
    ).write_text(
        json.dumps(
            summary,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # ========================================================
    # Validation
    # ========================================================

    report = validate(
        df,
        output,
        query_status,
        sec_status,
    )

    print(
        "\n===== VALIDATION RESULT ====="
    )

    print(
        json.dumps(
            report,
            indent=2,
            ensure_ascii=False,
        )
    )

    raise SystemExit(
        0
        if report["validation_pass"]
        else 1
    )


if __name__ == "__main__":
    main()
