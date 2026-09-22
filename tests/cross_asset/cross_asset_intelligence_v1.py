import json
import os
import time
import hashlib
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import pandas as pd
# ============================================================
# Event / News Intelligence v1
# Research-only
# No Decision Engine
# No trading signals
# No forecasting
# ============================================================
API_URL = "https://gnews.io/api/v4/search"
API_KEY = os.getenv("GNEWS_API_KEY", "").strip()
LOOKBACK_DAYS = 30
# GNews free plans can be restrictive.
MAX_ARTICLES = 10
# Retry configuration
RETRIES = 6
RETRY_BASE_SECONDS = 3
RETRY_MAX_SECONDS = 60
# Delay between different topic queries
BETWEEN_QUERIES_SECONDS = 5
# Conservative availability delay
AVAILABILITY_DELAY_HOURS = 12
# Minimum successful topics required for validation
MIN_SUCCESSFUL_TOPICS = 5
# HTTP timeout
HTTP_TIMEOUT_SECONDS = 30
QUERIES = {
    "fed": '"Federal Reserve" OR FOMC OR "Fed Chair" OR Powell',
    "inflation": 'CPI OR "consumer price index" OR PPI OR "producer price index"',
    "labor": '"nonfarm payrolls" OR "jobless claims" OR unemployment OR employment',
    "growth": 'GDP OR "economic growth" OR PMI OR ISM OR recession',
    "market": '"S&P 500" OR SP500 OR "US stocks" OR equities',
    "geopolitical": 'tariff OR tariffs OR sanctions OR "trade war" OR conflict OR ceasefire',
    "energy": 'oil OR crude OR OPEC OR gasoline OR energy',
}
TERMS = {
    "fed": [
        "federal reserve",
        "fomc",
        "fed chair",
        "powell",
        "interest rate",
        "central bank",
    ],
    "inflation": [
        "cpi",
        "consumer price",
        "ppi",
        "producer price",
        "inflation",
    ],
    "labor": [
        "nonfarm payroll",
        "jobless claim",
        "unemployment",
        "employment",
        "jobs",
        "labor",
    ],
    "growth": [
        "gdp",
        "economic growth",
        "pmi",
        "ism",
        "recession",
        "economic activity",
    ],
    "market": [
        "s&p 500",
        "sp500",
        "us stocks",
        "equities",
        "stock market",
        "wall street",
    ],
    "geopolitical": [
        "tariff",
        "sanction",
        "trade war",
        "conflict",
        "ceasefire",
        "geopolitical",
    ],
    "energy": [
        "oil",
        "crude",
        "opec",
        "gasoline",
        "energy",
        "fuel",
    ],
}
def now():
    return datetime.now(timezone.utc)
def iso(dt):
    return (
        dt.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
def parse_dt(value):
    try:
        if value is None:
            return None
        value = str(value).strip()
        if not value:
            return None
        return (
            datetime.fromisoformat(
                value.replace("Z", "+00:00")
            )
            .astimezone(timezone.utc)
        )
    except Exception:
        return None
def retry_delay(attempt, retry_after=None):
    """
    Exponential backoff with jitter.
    If the server provides Retry-After, respect it.
    """
    if retry_after:
        try:
            seconds = float(retry_after)
            return min(max(seconds, 1), RETRY_MAX_SECONDS)
        except Exception:
            pass
    base = RETRY_BASE_SECONDS * (2 ** attempt)
    jitter = random.uniform(0, 1.5)
    return min(base + jitter, RETRY_MAX_SECONDS)
def get_json(params):
    """
    Robust GNews HTTP request.
    Handles:
      - missing API key
      - HTTP 429
      - HTTP 5xx
      - temporary network failures
      - invalid/non-JSON responses
    """
    if not API_KEY:
        return None, {
            "ok": False,
            "status": None,
            "error": "GNEWS_API_KEY is missing",
            "attempts": 0,
        }
    query_params = dict(params)
    query_params["token"] = API_KEY
    url = API_URL + "?" + urlencode(query_params)
    last_error = ""
    last_status = None
    for attempt in range(RETRIES):
        try:
            request = Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "US500-Macro-Intelligence/1.0 "
                        "(research-only)"
                    ),
                },
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
                raw = response.read()
                text = raw.decode(
                    "utf-8",
                    errors="replace",
                ).strip()
                if not text:
                    raise ValueError(
                        "GNews returned an empty response body"
                    )
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"GNews returned non-JSON response: "
                        f"{exc}"
                    ) from exc
                if not isinstance(payload, dict):
                    raise ValueError(
                        "GNews JSON response is not an object"
                    )
                # GNews may return an API-level error inside JSON.
                if payload.get("errors"):
                    raise ValueError(
                        f"GNews API error: "
                        f"{payload.get('errors')}"
                    )
                return payload, {
                    "ok": True,
                    "status": status_code,
                    "error": None,
                    "attempts": attempt + 1,
                }
        except HTTPError as exc:
            last_status = exc.code
            last_error = (
                f"HTTP {exc.code}: {exc.reason}"
            )
            # Capture Retry-After when available.
            retry_after = None
            try:
                retry_after = exc.headers.get(
                    "Retry-After"
                )
            except Exception:
                pass
            # Permanent/client errors.
            if exc.code not in (
                408,
                429,
                500,
                502,
                503,
                504,
            ):
                return None, {
                    "ok": False,
                    "status": exc.code,
                    "error": last_error,
                    "attempts": attempt + 1,
                }
            # Retryable error.
            if attempt < RETRIES - 1:
                delay = retry_delay(
                    attempt,
                    retry_after,
                )
                print(
                    f"[WARN] HTTP {exc.code}; "
                    f"retry {attempt + 1}/{RETRIES - 1} "
                    f"in {delay:.1f}s"
                )
                time.sleep(delay)
        except (
            URLError,
            TimeoutError,
            ValueError,
        ) as exc:
            last_error = str(exc)
            if attempt < RETRIES - 1:
                delay = retry_delay(attempt)
                print(
                    f"[WARN] temporary request error; "
                    f"retry {attempt + 1}/{RETRIES - 1} "
                    f"in {delay:.1f}s: "
                    f"{last_error}"
                )
                time.sleep(delay)
    return None, {
        "ok": False,
        "status": last_status,
        "error": last_error or "request failed",
        "attempts": RETRIES,
    }
def relevant(topic, article):
    blob = " ".join(
        str(article.get(key) or "")
        for key in (
            "title",
            "description",
            "content",
        )
    ).lower()
    return any(
        term in blob
        for term in TERMS[topic]
    )
def make_id(topic, article):
    raw = "|".join(
        [
            topic,
            str(article.get("url") or ""),
            str(article.get("publishedAt") or ""),
            str(article.get("title") or ""),
        ]
    )
    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:24]
def fetch(topic, query, start, end):
    data, status = get_json(
        {
            "q": query,
            "lang": "en",
            "country": "us",
            "max": MAX_ARTICLES,
            "from": iso(start),
            "to": iso(end),
            "sortby": "publishedAt",
        }
    )
    if not status["ok"]:
        status["raw_rows"] = 0
        status["normalized_rows"] = 0
        return [], status
    articles = (
        data.get("articles", [])
        if isinstance(data, dict)
        else []
    )
    if not isinstance(articles, list):
        status["ok"] = False
        status["error"] = (
            "GNews 'articles' field is not a list"
        )
        status["raw_rows"] = 0
        status["normalized_rows"] = 0
        return [], status
    rows = []
    for article in articles:
        published = parse_dt(
            article.get("publishedAt")
        )
        url = str(
            article.get("url") or ""
        ).strip()
        title = str(
            article.get("title") or ""
        ).strip()
        if not published:
            continue
        if not url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue
        if not title:
            continue
        available = (
            published
            + timedelta(
                hours=AVAILABILITY_DELAY_HOURS
            )
        )
        rows.append(
            {
                "event_id": make_id(
                    topic,
                    article,
                ),
                "published_at": iso(
                    published
                ),
                "available_at": iso(
                    available
                ),
                "availability_date": (
                    available.date().isoformat()
                ),
                "source": "GNEWS",
                "topic": topic,
                "language": "en",
                "country": "US",
                "title": title,
                "description": str(
                    article.get("description")
                    or ""
                ).strip(),
                "url": url,
                "source_name": str(
                    (
                        article.get("source")
                        or {}
                    ).get("name")
                    or ""
                ).strip(),
                "query": query,
                "topic_relevant": relevant(
                    topic,
                    article,
                ),
                "pit_safe": (
                    available <= now()
                ),
                "research_only": True,
                "decision_engine_ready": False,
                "trading_signal": False,
                "forecast": False,
            }
        )
    status["raw_rows"] = len(articles)
    status["normalized_rows"] = len(rows)
    return rows, status
def validate(df, statuses):
    checks = []
    warnings = []
    # --------------------------------------------------------
    # Basic event validation
    # --------------------------------------------------------
    if df.empty:
        checks.append(
            {
                "check": "non_empty_events",
                "pass": False,
                "detail": (
                    "No GNews events collected."
                ),
            }
        )
    else:
        checks.extend(
            [
                {
                    "check": "unique_event_ids",
                    "pass": bool(
                        df.event_id.is_unique
                    ),
                    "detail": (
                        f"rows={len(df)} "
                        f"unique={df.event_id.nunique()}"
                    ),
                },
                {
                    "check": (
                        "published_timestamps_parse"
                    ),
                    "pass": bool(
                        pd.to_datetime(
                            df.published_at,
                            utc=True,
                            errors="coerce",
                        ).notna().all()
                    ),
                    "detail": "",
                },
                {
                    "check": "urls_valid",
                    "pass": bool(
                        df.url.astype(str)
                        .str.match(
                            r"^https?://",
                            na=False,
                        )
                        .all()
                    ),
                    "detail": "",
                },
            ]
        )
        published = pd.to_datetime(
            df.published_at,
            utc=True,
            errors="coerce",
        )
        available = pd.to_datetime(
            df.available_at,
            utc=True,
            errors="coerce",
        )
        pit = (
            available.notna().all()
            and (
                available
                >= published
                + pd.Timedelta(hours=12)
            ).all()
            and bool(df.pit_safe.all())
        )
        checks.append(
            {
                "check": "point_in_time_safe",
                "pass": bool(pit),
                "detail": (
                    "published_at + 12h "
                    "conservative availability"
                ),
            }
        )
        checks.append(
            {
                "check": "research_only_guards",
                "pass": bool(
                    df.research_only.all()
                    and (
                        ~df.decision_engine_ready
                    ).all()
                    and (
                        ~df.trading_signal
                    ).all()
                    and (~df.forecast).all()
                ),
                "detail": (
                    "research_only=true; "
                    "no signal/forecast/"
                    "Decision Engine"
                ),
            }
        )
    # --------------------------------------------------------
    # Topic coverage
    # --------------------------------------------------------
    counts = (
        df.topic.value_counts().to_dict()
        if not df.empty
        else {}
    )
    successful = sum(
        bool(status.get("ok"))
        for status in statuses.values()
    )
    checks.append(
        {
            "check": "gnews_topics_covered",
            "pass": successful >= MIN_SUCCESSFUL_TOPICS,
            "detail": (
                f"successful_topics="
                f"{successful}/{len(QUERIES)}; "
                f"{json.dumps(counts, sort_keys=True)}"
            ),
        }
    )
    # --------------------------------------------------------
    # Topic relevance
    # --------------------------------------------------------
    relevance_pct = (
        float(
            df.topic_relevant.mean() * 100
        )
        if not df.empty
        else 0.0
    )
    checks.append(
        {
            "check": "gnews_topic_relevance",
            "pass": relevance_pct >= 50,
            "detail": (
                f"relevant_pct="
                f"{relevance_pct:.2f}"
            ),
        }
    )
    # --------------------------------------------------------
    # Query execution
    # --------------------------------------------------------
    all_topics_present = (
        len(statuses) == len(QUERIES)
        and all(
            "ok" in status
            for status in statuses.values()
        )
    )
    checks.append(
        {
            "check": "query_execution_visible",
            "pass": bool(
                all_topics_present
                and successful >= MIN_SUCCESSFUL_TOPICS
            ),
            "detail": json.dumps(
                statuses,
                sort_keys=True,
            ),
        }
    )
    warnings.extend(
        [
            (
                "GNews free-tier news history is "
                "limited; this is not a complete "
                "historical news archive."
            ),
            (
                "Availability is conservatively "
                "delayed by 12 hours to reduce "
                "look-ahead risk."
            ),
            (
                "Topic labels are query-derived "
                "research categories, not trading "
                "signals."
            ),
        ]
    )
    failed = [
        check
        for check in checks
        if not check["pass"]
    ]
    return {
        "validator": "Event / News Intelligence v1",
        "status": (
            "FAIL"
            if failed
            else "PASS"
        ),
        "validation_pass": not bool(failed),
        "errors": failed,
        "checks": checks,
        "warnings": warnings,
        "rows": int(len(df)),
        "date_start": (
            None
            if df.empty
            else str(df.published_at.min())
        ),
        "date_end": (
            None
            if df.empty
            else str(df.published_at.max())
        ),
        "source_counts": (
            {}
            if df.empty
            else df.source.value_counts().to_dict()
        ),
        "topic_counts": counts,
        "query_status": statuses,
        "research_only": True,
        "decision_engine_ready": False,
        "trading_signal": False,
        "forecast": False,
        "pit_perfect": False,
        "point_in_time_reconstructed": False,
        "availability_method": (
            "published_at_plus_12h"
        ),
    }
def main():
    print(
        "============================================================"
    )
    print(
        "Event / News Intelligence v1"
    )
    print(
        "Research-only — No Decision Engine"
    )
    print(
        "============================================================"
    )
    if not API_KEY:
        print(
            "[ERROR] GNEWS_API_KEY is not configured."
        )
        raise SystemExit(2)
    end = now()
    start = end - timedelta(
        days=LOOKBACK_DAYS
    )
    print(
        f"[INFO] Window: {iso(start)} -> {iso(end)}"
    )
    rows = []
    statuses = {}
    for index, (
        topic,
        query,
    ) in enumerate(QUERIES.items()):
        if index:
            print(
                f"[INFO] Waiting "
                f"{BETWEEN_QUERIES_SECONDS}s "
                f"before next topic..."
            )
            time.sleep(
                BETWEEN_QUERIES_SECONDS
            )
        print(
            f"[INFO] Querying topic: {topic}"
        )
        topic_rows, status = fetch(
            topic,
            query,
            start,
            end,
        )
        rows.extend(topic_rows)
        statuses[topic] = status
        print(
            f"[INFO] {topic}: "
            f"ok={status.get('ok')} "
            f"raw={status.get('raw_rows', 0)} "
            f"normalized="
            f"{status.get('normalized_rows', 0)} "
            f"error={status.get('error')}"
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = (
            df.drop_duplicates(
                subset=["event_id"]
            )
            .sort_values(
                [
                    "published_at",
                    "topic",
                ],
                ascending=[
                    False,
                    True,
                ],
            )
            .reset_index(drop=True)
        )
    validation = validate(
        df,
        statuses,
    )
    # --------------------------------------------------------
    # Output artifacts
    # --------------------------------------------------------
    df.to_csv(
        "event_news_events_v1.csv",
        index=False,
    )
    Path(
        "event_news_validation_v1.json"
    ).write_text(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        "\n===== VALIDATION RESULT ====="
    )
    print(
        json.dumps(
            validation,
            indent=2,
            ensure_ascii=False,
        )
    )
    if validation["status"] == "FAIL":
        raise SystemExit(1)
if __name__ == "__main__":
    main()
