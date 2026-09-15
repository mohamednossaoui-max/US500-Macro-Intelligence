"""
Federal Reserve Intelligence Engine
Phase 2A + Phase 2B + Phase 2C

Analytical only.
No trade execution.
No Decision Engine integration.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Dict, Optional

import pandas as pd
import requests
from bs4 import BeautifulSoup

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# ============================================================
# CONFIG
# ============================================================

FED = "https://www.federalreserve.gov"
CALENDAR = f"{FED}/monetarypolicy/fomccalendars.htm"
BEIGE_BOOK = f"{FED}/monetarypolicy/publications/beige-book-default.htm"

HEADERS = {
    "User-Agent": "Mozilla/5.0 US500-Macro-Intelligence/2.0"
}

TIMEOUT = 30


# ============================================================
# HTTP HELPERS
# ============================================================

def get(url: str) -> Optional[requests.Response]:
    if not url:
        return None

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )
        r.raise_for_status()
        return r
    except Exception:
        return None


def absolute(href: str) -> str:
    if not href:
        return ""

    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("/"):
        return FED + href

    return FED + "/" + href.lstrip("./")


def clean_html(html: str) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for x in soup(["script", "style", "noscript", "svg"]):
        x.decompose()

    return re.sub(
        r"\s+",
        " ",
        soup.get_text(" ", strip=True)
    ).strip()


def pdf_text(url: str) -> str:
    if not url or PdfReader is None:
        return ""

    r = get(url)

    if r is None:
        return ""

    try:
        reader = PdfReader(io.BytesIO(r.content))

        text = " ".join(
            (page.extract_text() or "")
            for page in reader.pages
        )

        return re.sub(r"\s+", " ", text).strip()

    except Exception:
        return ""


def fetch_document(url: str) -> str:
    if not url:
        return ""

    if url.lower().endswith(".pdf"):
        return pdf_text(url)

    r = get(url)

    if r is None:
        return ""

    return clean_html(r.text)


# ============================================================
# DATE / LINK HELPERS
# ============================================================

def date_from_href(href: str) -> Optional[date]:
    if not href:
        return None

    m = re.search(r"(20\d{6})", href)

    if not m:
        return None

    try:
        return datetime.strptime(
            m.group(1),
            "%Y%m%d"
        ).date()

    except Exception:
        return None


def discover_links() -> Dict[str, Dict[date, str]]:
    """
    Discover official FOMC documents from the Fed calendar.
    """

    result = {
        "statement": {},
        "minutes": {},
        "press": {},
        "sep": {}
    }

    r = get(CALENDAR)

    if r is None:
        return result

    soup = BeautifulSoup(r.text, "html.parser")

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")
        url = absolute(href)

        d = date_from_href(href)

        if not d:
            continue

        h = href.lower()
        label = a.get_text(" ", strip=True).lower()

        # FOMC statement
        if (
            "fomcstmt" in h
            or re.search(r"monetary\d{8}a\.htm", h)
            or "statement" in label
        ):
            result["statement"][d] = url

        # FOMC minutes
        elif (
            "fomcminutes" in h
            or "minutes" in label
        ):
            result["minutes"][d] = url

        # Press conference
        elif (
            "fomcpresconf" in h
            or "press conference" in label
        ):
            result["press"][d] = url

        # SEP / projections
        elif (
            "fomcproj" in h
            or "projection materials" in label
        ):
            result["sep"][d] = url

    return result


def latest_completed_fomc(
    links: Dict[str, Dict[date, str]],
    as_of: Optional[date] = None
) -> Optional[date]:

    as_of = as_of or date.today()

    dates = (
        set(links.get("statement", {}))
        | set(links.get("minutes", {}))
        | set(links.get("press", {}))
    )

    done = [
        d for d in dates
        if d <= as_of
    ]

    return max(done) if done else None


def latest_sep(
    links: Dict[str, Dict[date, str]],
    as_of: Optional[date] = None
) -> Optional[date]:

    as_of = as_of or date.today()

    dates = [
        d for d in links.get("sep", {})
        if d <= as_of
    ]

    return max(dates) if dates else None


def previous_sep(
    links: Dict[str, Dict[date, str]],
    current: date
) -> Optional[date]:

    dates = [
        d for d in links.get("sep", {})
        if d < current
    ]

    return max(dates) if dates else None


# ============================================================
# DYNAMIC FED CHAIR
# ============================================================

def fed_chair_for_date(d: Optional[date]) -> str:
    """
    Current chair handling.

    Kevin Warsh became Fed Chair on May 22, 2026.
    Before that, Jerome Powell was Chair.
    """

    if not d:
        return "Unknown"

    warsh_start = date(2026, 5, 22)

    if d >= warsh_start:
        return "Kevin Warsh"

    return "Jerome Powell"


# ============================================================
# PRESS CONFERENCE
# ============================================================

def press_page_data(url: str) -> Dict:

    if not url:
        return {
            "page_url": None,
            "pdf_url": None,
            "text": ""
        }

    r = get(url)

    if r is None:
        return {
            "page_url": url,
            "pdf_url": None,
            "text": ""
        }

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    pdf = ""

    for a in soup.find_all("a", href=True):

        label = a.get_text(
            " ",
            strip=True
        ).lower()

        href = absolute(
            a.get("href", "")
        )

        if (
            href.lower().endswith(".pdf")
            and (
                "transcript" in label
                or "press conference" in label
            )
        ):
            pdf = href
            break

    text = (
        pdf_text(pdf)
        if pdf
        else clean_html(r.text)
    )

    return {
        "page_url": url,
        "pdf_url": pdf or None,
        "text": text
    }


# ============================================================
# SEP
# ============================================================

def _num(x):

    if x is None:
        return None

    text = str(x).replace("â", "-")

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    return float(m.group()) if m else None


def _norm(x):

    return re.sub(
        r"[^a-z0-9]",
        "",
        str(x).lower()
    )


def extract_sep(
    url: str,
    sep_date: date
) -> Dict:

    out = {
        "sep_date": sep_date.isoformat(),
        "url": url,
        "available": False,
        "year": sep_date.year,
        "gdp": None,
        "unemployment": None,
        "pce": None,
        "core_pce": None,
        "fed_funds": None
    }

    if not url:
        return out

    try:
        tables = pd.read_html(url)

    except Exception:
        tables = []

    targets = {
        "gdp": "changeinrealgdp",
        "unemployment": "unemploymentrate",
        "pce": "pceinflation",
        "core_pce": "corepceinflation",
        "fed_funds": "federalfundsrate"
    }

    for df in tables:

        if df.empty:
            continue

        for _, row in df.iterrows():

            first = _norm(row.iloc[0])

            for field, target in targets.items():

                if out[field] is not None:
                    continue

                if target in first:

                    vals = [
                        _num(v)
                        for v in row.iloc[1:].tolist()
                    ]

                    vals = [
                        v for v in vals
                        if v is not None
                    ]

                    if vals:
                        out[field] = vals[0]

    if any(
        out[k] is not None
        for k in targets
    ):
        out["available"] = True
        return out

    text = fetch_document(url)

    out["available"] = bool(text)

    if not text:
        return out

    patterns = {

        "gdp":
            r"Change in real GDP.{0,120}?\b(\d+\.\d)\b",

        "unemployment":
            r"Unemployment rate.{0,120}?\b(\d+\.\d)\b",

        "pce":
            r"PCE inflation.{0,120}?\b(\d+\.\d)\b",

        "core_pce":
            r"Core PCE inflation.{0,120}?\b(\d+\.\d)\b",

        "fed_funds":
            r"Federal funds rate.{0,120}?\b(\d+\.\d)\b"
    }

    for field, pattern in patterns.items():

        m = re.search(
            pattern,
            text,
            re.I
        )

        if m:
            out[field] = float(m.group(1))

    out["available"] = any(
        out[k] is not None
        for k in targets
    )

    return out


def sep_shift(
    current: Dict,
    previous: Dict
) -> Dict:

    fields = [
        "gdp",
        "unemployment",
        "pce",
        "core_pce",
        "fed_funds"
    ]

    result = {}

    hawkish = 0
    dovish = 0

    for f in fields:

        c = current.get(f)
        p = previous.get(f)

        change = (
            round(c - p, 2)
            if c is not None and p is not None
            else None
        )

        result[f] = {
            "current": c,
            "previous": p,
            "change": change
        }

        if change is None or change == 0:
            continue

        if f in (
            "pce",
            "core_pce",
            "fed_funds"
        ):

            if change > 0:
                hawkish += 1
            else:
                dovish += 1

        elif f == "gdp":

            if change > 0:
                hawkish += 1
            else:
                dovish += 1

        elif f == "unemployment":

            if change > 0:
                dovish += 1
            else:
                hawkish += 1

    if hawkish > dovish:
        classification = "HAWKISH SHIFT"

    elif dovish > hawkish:
        classification = "DOVISH SHIFT"

    else:
        classification = "MIXED / NEUTRAL SHIFT"

    return {
        "classification": classification,
        "hawkish_points": int(hawkish),
        "dovish_points": int(dovish),
        "fields": result
    }


# ============================================================
# DOCUMENT TONE
# ============================================================

HAWKISH = [
    "higher for longer",
    "restrictive",
    "inflation remains elevated",
    "persistent inflation",
    "upside risks to inflation",
    "additional tightening",
    "rate increase",
    "raise the target range",
    "higher policy rate",
    "inflation pressures",
    "price pressures"
]


DOVISH = [
    "rate cut",
    "rate cuts",
    "lower rates",
    "easing policy",
    "labor market has cooled",
    "economic activity slowed",
    "growth slowed",
    "downside risks",
    "inflation has eased",
    "inflation eased",
    "labor market weakened"
]


def count_terms(
    text: str,
    terms
) -> int:

    low = text.lower()

    return sum(
        low.count(t)
        for t in terms
    )


def tone_score(text: str) -> int:

    if not text:
        return 0

    score = (
        count_terms(text, HAWKISH)
        - count_terms(text, DOVISH)
    )

    return max(
        -20,
        min(20, score)
    )


def tone(score: int) -> str:

    if score >= 8:
        return "HAWKISH"

    if score >= 3:
        return "MODERATELY HAWKISH"

    if score <= -8:
        return "DOVISH"

    if score <= -3:
        return "MODERATELY DOVISH"

    return "NEUTRAL"


def analyze(
    name: str,
    text: str
) -> Dict:

    if not text:

        return {
            "name": name,
            "available": False,
            "tone": "UNAVAILABLE",
            "tone_score": None
        }

    s = tone_score(text)

    return {
        "name": name,
        "available": True,
        "tone": tone(s),
        "tone_score": s,

        "inflation_mentions": count_terms(
            text,
            [
                "inflation",
                "prices",
                "price pressures"
            ]
        ),

        "labor_mentions": count_terms(
            text,
            [
                "employment",
                "labor market",
                "unemployment",
                "job gains",
                "wages"
            ]
        ),

        "growth_mentions": count_terms(
            text,
            [
                "economic activity",
                "economic growth",
                "growth",
                "consumer spending"
            ]
        ),

        "financial_mentions": count_terms(
            text,
            [
                "financial conditions",
                "financial stability",
                "credit conditions",
                "banking",
                "liquidity"
            ]
        ),

        "text_length": len(text)
    }


# ============================================================
# PHASE 2B — FED DIMENSIONS
# ============================================================

DIMENSION_SIGNALS = {

    "inflation": {
        "hawkish": [
            "inflation remains elevated",
            "inflation remains high",
            "persistent inflation",
            "price pressures",
            "higher prices",
            "inflation expectations increased",
            "upside inflation risks"
        ],
        "dovish": [
            "inflation eased",
            "inflation declined",
            "inflation moderated",
            "price pressures eased",
            "inflation expectations declined"
        ]
    },

    "labor": {
        "hawkish": [
            "labor market remains strong",
            "employment increased",
            "job gains",
            "wages increased",
            "wage growth"
        ],
        "dovish": [
            "labor market weakened",
            "employment declined",
            "job losses",
            "unemployment increased",
            "hiring slowed",
            "labor demand weakened"
        ]
    },

    "growth": {
        "hawkish": [
            "economic activity increased",
            "economic growth increased",
            "growth remained solid",
            "consumer spending increased",
            "demand remained strong"
        ],
        "dovish": [
            "economic activity slowed",
            "growth slowed",
            "economic activity weakened",
            "consumer spending declined",
            "demand weakened"
        ]
    },

    "financial": {
        "hawkish": [
            "financial conditions tightened",
            "credit conditions tightened",
            "financial conditions restrictive",
            "credit became more restrictive"
        ],
        "dovish": [
            "financial conditions eased",
            "credit conditions eased",
            "financial conditions improved",
            "credit availability improved"
        ]
    },

    "policy": {
        "hawkish": [
            "higher for longer",
            "restrictive policy",
            "additional tightening",
            "rate increase",
            "higher policy rate",
            "policy remains restrictive"
        ],
        "dovish": [
            "rate cut",
            "rate cuts",
            "lower rates",
            "easing policy",
            "policy easing",
            "lower policy rate"
        ]
    }
}


DIMENSION_WEIGHTS = {
    "inflation": 25,
    "labor": 15,
    "growth": 15,
    "financial": 10,
    "policy": 35
}


def dimension_signal(
    text: str,
    dimension: str
) -> Dict:

    if not text:

        return {
            "score": 0,
            "classification": "UNAVAILABLE",
            "hawkish_hits": 0,
            "dovish_hits": 0
        }

    low = text.lower()

    cfg = DIMENSION_SIGNALS[dimension]

    hawkish_hits = sum(
        low.count(term)
        for term in cfg["hawkish"]
    )

    dovish_hits = sum(
        low.count(term)
        for term in cfg["dovish"]
    )

    raw = hawkish_hits - dovish_hits

    score = max(
        -10,
        min(10, raw)
    )

    if score >= 4:
        classification = "HAWKISH"

    elif score >= 1:
        classification = "MODERATELY HAWKISH"

    elif score <= -4:
        classification = "DOVISH"

    elif score <= -1:
        classification = "MODERATELY DOVISH"

    else:
        classification = "NEUTRAL"

    return {
        "score": score,
        "classification": classification,
        "hawkish_hits": hawkish_hits,
        "dovish_hits": dovish_hits
    }


def dimension_to_100(
    signal: Dict
) -> float:

    score = signal.get("score", 0)

    return round(
        50 + score * 5,
        1
    )


def calculate_fed_score(
    dimensions: Dict,
    sep_shift_data: Optional[Dict]
) -> Dict:

    weighted = 0
    total_weight = 0

    for name, weight in DIMENSION_WEIGHTS.items():

        if name not in dimensions:
            continue

        weighted += (
            dimensions[name]["score_100"]
            * weight
        )

        total_weight += weight

    if total_weight == 0:

        base_score = 50.0

    else:

        base_score = (
            weighted / total_weight
        )

    sep_adjustment = 0.0

    if sep_shift_data:

        classification = sep_shift_data.get(
            "classification",
            ""
        )

        if classification == "HAWKISH SHIFT":
            sep_adjustment = 5.0

        elif classification == "DOVISH SHIFT":
            sep_adjustment = -5.0

    final_score = max(
        0,
        min(
            100,
            base_score + sep_adjustment
        )
    )

    if final_score >= 75:
        classification = "HAWKISH"

    elif final_score >= 56:
        classification = "MODERATELY HAWKISH"

    elif final_score >= 45:
        classification = "NEUTRAL"

    elif final_score >= 25:
        classification = "MODERATELY DOVISH"

    else:
        classification = "DOVISH"

    return {
        "score": round(final_score, 1),
        "base_score": round(base_score, 1),
        "sep_adjustment": sep_adjustment,
        "classification": classification
    }


def build_evidence(
    dimensions: Dict,
    sep_shift_data: Optional[Dict]
) -> list:

    reasons = []

    for name, data in dimensions.items():

        classification = data.get(
            "classification"
        )

        contribution = round(
            (
                data["score_100"] - 50
            )
            * DIMENSION_WEIGHTS[name]
            / 100,
            2
        )

        reasons.append(
            f"- {name.capitalize()}: "
            f"{classification} "
            f"({contribution:+.2f})"
        )

    if sep_shift_data:

        classification = sep_shift_data.get(
            "classification"
        )

        if classification != "MIXED / NEUTRAL SHIFT":

            reasons.append(
                f"- SEP: {classification}"
            )

    return reasons


def build_deep_fed_analysis(
    statement_text: str,
    minutes_text: str,
    chair_text: str,
    sep_shift_data: Optional[Dict]
) -> Dict:

    statement_dimensions = {}
    minutes_dimensions = {}
    chair_dimensions = {}

    for dimension in DIMENSION_WEIGHTS:

        s = dimension_signal(
            statement_text,
            dimension
        )

        m = dimension_signal(
            minutes_text,
            dimension
        )

        c = dimension_signal(
            chair_text,
            dimension
        )

        statement_dimensions[dimension] = {
            **s,
            "score_100": dimension_to_100(s)
        }

        minutes_dimensions[dimension] = {
            **m,
            "score_100": dimension_to_100(m)
        }

        chair_dimensions[dimension] = {
            **c,
            "score_100": dimension_to_100(c)
        }

    combined = {}

    for dimension in DIMENSION_WEIGHTS:

        s = statement_dimensions[dimension]["score_100"]
        m = minutes_dimensions[dimension]["score_100"]
        c = chair_dimensions[dimension]["score_100"]

        combined_score = (
            s * 0.35
            + m * 0.40
            + c * 0.25
        )

        combined[dimension] = {
            "score_100": round(
                combined_score,
                1
            ),
            "statement": statement_dimensions[dimension],
            "minutes": minutes_dimensions[dimension],
            "chair": chair_dimensions[dimension]
        }

    dimensions_for_score = {
        k: {
            "score_100": v["score_100"]
        }
        for k, v in combined.items()
    }

    fed_score = calculate_fed_score(
        dimensions_for_score,
        sep_shift_data
    )

    reasons = build_evidence(
        dimensions_for_score,
        sep_shift_data
    )

    return {
        "statement": statement_dimensions,
        "minutes": minutes_dimensions,
        "chair": chair_dimensions,
        "combined": combined,
        "fed_score": fed_score,
        "reasons": reasons
    }


# ============================================================
# PHASE 2C — BEIGE BOOK
# ============================================================

def discover_beige_book(
    as_of: Optional[date] = None
) -> Dict:

    """
    Discover the latest official Beige Book.

    The Fed archive uses issue-month URLs such as:
    beigebook202608-summary.htm

    The August 2026 issue was published on
    September 2, 2026.
    """

    as_of = as_of or date.today()

    result = {
        "available": False,
        "issue_date": None,
        "publication_date": None,
        "title": None,
        "url": None,
        "text": ""
    }

    r = get(BEIGE_BOOK)

    if r is None:
        return result

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    candidates = []

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")
        label = a.get_text(
            " ",
            strip=True
        )

        full_url = absolute(href)

        m = re.search(
            r"beigebook(20\d{4})",
            href.lower()
        )

        if not m:
            continue

        issue = m.group(1)

        try:
            issue_year = int(issue[:4])
            issue_month = int(issue[4:6])

            issue_date = date(
                issue_year,
                issue_month,
                1
            )

        except Exception:
            continue

        # Never select an issue that is clearly in the future.
        if issue_date > date(
            as_of.year,
            as_of.month,
            1
        ):
            continue

        candidates.append({
            "issue_date": issue_date,
            "url": full_url,
            "label": label,
            "href": href
        })

    if not candidates:
        return result

    latest_issue = max(
        x["issue_date"]
        for x in candidates
    )

    same_issue = [
        x for x in candidates
        if x["issue_date"] == latest_issue
    ]

    # Prefer National Summary.
    national = None

    for item in same_issue:

        text = (
            item["label"]
            + " "
            + item["href"]
        ).lower()

        if "summary" in text or "national" in text:
            national = item
            break

    # If the archive did not expose a summary link,
    # use the predictable official summary URL.
    if national is None:

        predictable = (
            f"{FED}/monetarypolicy/"
            f"beigebook{latest_issue.year}"
            f"{latest_issue.month:02d}-summary.htm"
        )

        response = get(predictable)

        if response is not None:

            national = {
                "issue_date": latest_issue,
                "url": predictable,
                "label": "National Summary",
                "href": predictable
            }

    if national is None:
        return result

    text = fetch_document(
        national["url"]
    )

    if not text:
        return result

    # The publication date can be extracted from
    # the official page when available.
    publication_date = None

    date_patterns = [
        r"Last Update:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        r"Published:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})"
    ]

    for pattern in date_patterns:

        match = re.search(
            pattern,
            text,
            re.I
        )

        if match:

            try:

                publication_date = datetime.strptime(
                    match.group(1),
                    "%B %d, %Y"
                ).date()

                break

            except Exception:
                pass

    result.update({
        "available": True,
        "issue_date": latest_issue.isoformat(),
        "publication_date": (
            publication_date.isoformat()
            if publication_date
            else None
        ),
        "title": (
            f"Beige Book - "
            f"{latest_issue.strftime('%B %Y')}"
        ),
        "url": national["url"],
        "text": text
    })

    return result


# ============================================================
# BEIGE BOOK ANALYSIS
# ============================================================

BEIGE_DIMENSIONS = {

    "growth": {
        "positive": [
            "economic activity increased",
            "economic activity grew",
            "economic activity expanded",
            "activity increased",
            "activity grew",
            "activity expanded",
            "growth increased",
            "growth picked up",
            "demand strengthened",
            "outlook was positive"
        ],
        "negative": [
            "economic activity declined",
            "economic activity decreased",
            "activity declined",
            "activity decreased",
            "growth slowed",
            "growth weakened",
            "demand weakened",
            "outlook deteriorated"
        ]
    },

    "labor": {
        "positive": [
            "employment rose",
            "employment increased",
            "hiring increased",
            "labor demand increased",
            "labor demand remained healthy",
            "wages grew",
            "wage growth"
        ],
        "negative": [
            "employment declined",
            "employment fell",
            "hiring slowed",
            "labor demand declined",
            "labor demand weakened",
            "layoffs increased"
        ]
    },

    "inflation": {
        "positive": [
            "prices eased",
            "price increases slowed",
            "price pressures eased",
            "inflation moderated",
            "input costs declined"
        ],
        "negative": [
            "prices increased",
            "prices rose",
            "price pressures",
            "input price pressures",
            "input costs increased",
            "higher energy prices",
            "higher fuel prices",
            "tariff-related impacts"
        ]
    },

    "consumer_spending": {
        "positive": [
            "consumer spending grew",
            "consumer spending increased",
            "consumer spending strengthened",
            "retail sales increased",
            "tourism activity increased"
        ],
        "negative": [
            "consumer spending declined",
            "consumer spending weakened",
            "retail sales declined",
            "price sensitivity",
            "consumer confidence declined"
        ]
    },

    "manufacturing": {
        "positive": [
            "manufacturing activity picked up",
            "manufacturing activity increased",
            "manufacturing demand grew",
            "manufacturing demand increased",
            "new orders increased"
        ],
        "negative": [
            "manufacturing activity declined",
            "manufacturing activity weakened",
            "manufacturing demand declined",
            "manufacturing demand weakened"
        ]
    },

    "financial": {
        "positive": [
            "financial conditions improved",
            "financial conditions eased",
            "loan volumes increased",
            "lending increased",
            "loan demand grew"
        ],
        "negative": [
            "financial conditions tightened",
            "loan volumes declined",
            "lending declined",
            "credit conditions tightened",
            "loan demand weakened"
        ]
    },

    "housing": {
        "positive": [
            "residential construction increased",
            "housing activity increased",
            "home sales increased",
            "residential real estate improved"
        ],
        "negative": [
            "residential construction declined",
            "housing activity declined",
            "home sales declined",
            "residential real estate declined",
            "housing softened"
        ]
    }
}


def beige_dimension_signal(
    text: str,
    dimension: str
) -> Dict:

    if not text:

        return {
            "score": 0,
            "score_100": 50.0,
            "classification": "UNAVAILABLE",
            "positive_hits": 0,
            "negative_hits": 0
        }

    low = text.lower()

    cfg = BEIGE_DIMENSIONS[dimension]

    positive_hits = sum(
        low.count(term)
        for term in cfg["positive"]
    )

    negative_hits = sum(
        low.count(term)
        for term in cfg["negative"]
    )

    raw = positive_hits - negative_hits

    raw = max(
        -10,
        min(10, raw)
    )

    score_100 = round(
        50 + raw * 5,
        1
    )

    if raw >= 4:
        classification = "POSITIVE"

    elif raw >= 1:
        classification = "SLIGHTLY POSITIVE"

    elif raw <= -4:
        classification = "NEGATIVE"

    elif raw <= -1:
        classification = "SLIGHTLY NEGATIVE"

    else:
        classification = "NEUTRAL"

    return {
        "score": raw,
        "score_100": score_100,
        "classification": classification,
        "positive_hits": positive_hits,
        "negative_hits": negative_hits
    }


def build_beige_analysis(
    beige_text: str
) -> Dict:

    if not beige_text:

        return {
            "available": False,
            "score": None,
            "tone": "UNAVAILABLE",
            "dimensions": {},
            "reasons": []
        }

    dimensions = {}

    for dimension in BEIGE_DIMENSIONS:

        dimensions[dimension] = (
            beige_dimension_signal(
                beige_text,
                dimension
            )
        )

    # Beige Book is descriptive rather than a direct
    # monetary-policy document.
    #
    # Growth / labor / consumer / manufacturing /
    # financial / housing are economic-growth dimensions.
    #
    # Inflation is treated separately because stronger
    # price pressure is more hawkish for the Fed.

    weights = {
        "growth": 20,
        "labor": 15,
        "inflation": 25,
        "consumer_spending": 10,
        "manufacturing": 10,
        "financial": 10,
        "housing": 10
    }

    weighted = 0
    total_weight = 0

    for dimension, weight in weights.items():

        weighted += (
            dimensions[dimension]["score_100"]
            * weight
        )

        total_weight += weight

    score = (
        weighted / total_weight
        if total_weight
        else 50.0
    )

    # The score is an analytical balance,
    # NOT a probability and NOT a trading signal.
    if score >= 65:
        overall = "MODERATELY HAWKISH / STRONG ACTIVITY"

    elif score >= 56:
        overall = "SLIGHTLY HAWKISH"

    elif score >= 45:
        overall = "NEUTRAL"

    elif score >= 35:
        overall = "SLIGHTLY DOVISH"

    else:
        overall = "MODERATELY DOVISH"

    reasons = []

    for dimension, data in dimensions.items():

        reasons.append(
            f"- {dimension.replace('_', ' ').capitalize()}: "
            f"{data['classification']} "
            f"({data['score_100']:.1f}/100)"
        )

    return {
        "available": True,
        "score": round(score, 1),
        "tone": overall,
        "dimensions": dimensions,
        "reasons": reasons,
        "method": (
            "Heuristic analytical score based on "
            "directional language in the official "
            "National Summary. Not a probability."
        )
    }


# ============================================================
# COMPLETE FED INTELLIGENCE
# ============================================================

def build_fed_intelligence() -> Dict:

    links = discover_links()

    today = date.today()

    meeting = latest_completed_fomc(
        links,
        as_of=today
    )

    if not meeting:

        return {
            "available": False,
            "error": "No completed FOMC meeting found."
        }

    statement_url = (
        links["statement"].get(
            meeting,
            ""
        )
    )

    minutes_url = (
        links["minutes"].get(
            meeting,
            ""
        )
    )

    press_url = (
        links["press"].get(
            meeting,
            ""
        )
    )

    statement_text = fetch_document(
        statement_url
    )

    minutes_text = fetch_document(
        minutes_url
    )

    press = press_page_data(
        press_url
    )

    chair = fed_chair_for_date(
        meeting
    )

    current_sep_date = latest_sep(
        links,
        meeting
    )

    prev_sep_date = (
        previous_sep(
            links,
            current_sep_date
        )
        if current_sep_date
        else None
    )

    current_sep = (
        extract_sep(
            links["sep"].get(
                current_sep_date,
                ""
            ),
            current_sep_date
        )
        if current_sep_date
        else {}
    )

    previous = (
        extract_sep(
            links["sep"].get(
                prev_sep_date,
                ""
            ),
            prev_sep_date
        )
        if prev_sep_date
        else {}
    )

    shift = (
        sep_shift(
            current_sep,
            previous
        )
        if current_sep and previous
        else {}
    )

    # --------------------------------------------------------
    # PHASE 2B
    # --------------------------------------------------------

    deep_analysis = build_deep_fed_analysis(
        statement_text=statement_text,
        minutes_text=minutes_text,
        chair_text=press["text"],
        sep_shift_data=shift
    )

    # --------------------------------------------------------
    # PHASE 2C
    # --------------------------------------------------------

    beige = discover_beige_book(
        as_of=today
    )

    beige_analysis = build_beige_analysis(
        beige.get("text", "")
    )

    return {

        "available": True,

        "as_of_date": today.isoformat(),

        "latest_fomc": meeting.isoformat(),

        "current_date": today.isoformat(),

        "fed_chair": chair,

        # ----------------------------------------------------
        # FOMC
        # ----------------------------------------------------

        "statement": analyze(
            "FOMC Statement",
            statement_text
        ),

        "statement_source": statement_url,

        "minutes": analyze(
            "FOMC Minutes",
            minutes_text
        ),

        "minutes_source": minutes_url,

        "chair_press": analyze(
            f"{chair} Press Conference",
            press["text"]
        ),

        "chair_page": press["page_url"],

        "chair_pdf": press["pdf_url"],

        # Backward-compatible key
        "powell": analyze(
            f"{chair} Press Conference",
            press["text"]
        ),

        "powell_page": press["page_url"],

        "powell_pdf": press["pdf_url"],

        # ----------------------------------------------------
        # SEP
        # ----------------------------------------------------

        "latest_sep_date": (
            current_sep_date.isoformat()
            if current_sep_date
            else None
        ),

        "previous_sep_date": (
            prev_sep_date.isoformat()
            if prev_sep_date
            else None
        ),

        "sep_current": current_sep,

        "sep_previous": previous,

        "sep_shift": shift,

        # ----------------------------------------------------
        # PHASE 2B
        # ----------------------------------------------------

        "phase_2b": deep_analysis,

        "fed_score": deep_analysis[
            "fed_score"
        ],

        # ----------------------------------------------------
        # PHASE 2C
        # ----------------------------------------------------

        "beige_book": {
            "available": beige["available"],
            "issue_date": beige["issue_date"],
            "publication_date": beige[
                "publication_date"
            ],
            "title": beige["title"],
            "url": beige["url"]
        },

        "beige_analysis": beige_analysis
    }


# ============================================================
# SUMMARY
# ============================================================

def fed_summary(
    data: Dict
) -> str:

    if not data.get("available"):

        return (
            "FED INTELLIGENCE unavailable: "
            + str(
                data.get(
                    "error",
                    "unknown error"
                )
            )
        )

    fed_score = data.get(
        "fed_score",
        {}
    )

    beige = data.get(
        "beige_book",
        {}
    )

    beige_analysis = data.get(
        "beige_analysis",
        {}
    )

    lines = [

        "FED INTELLIGENCE",
        "================",

        f"Latest FOMC: "
        f"{data['latest_fomc']}",

        f"Fed Chair: "
        f"{data.get('fed_chair')}",

        f"Statement: "
        f"{data['statement']['tone']}",

        f"{data.get('fed_chair')} Press Conference: "
        f"{data['chair_press']['tone']}",

        f"Minutes: "
        f"{data['minutes']['tone']}",

        f"Latest SEP: "
        f"{data.get('latest_sep_date')}",

        f"Previous SEP: "
        f"{data.get('previous_sep_date')}"
    ]

    # --------------------------------------------------------
    # SEP
    # --------------------------------------------------------

    if data.get("sep_shift"):

        lines.append(
            "SEP Shift: "
            + data["sep_shift"][
                "classification"
            ]
        )

        for k, v in data[
            "sep_shift"
        ]["fields"].items():

            lines.append(
                f"{k}: "
                f"{v['previous']} -> "
                f"{v['current']} "
                f"({v['change']})"
            )

    # --------------------------------------------------------
    # PHASE 2B
    # --------------------------------------------------------

    lines.extend([

        "",
        "PHASE 2B",
        "---------",

        f"Fed Intelligence Score: "
        f"{fed_score.get('score')}/100",

        f"Overall Tone: "
        f"{fed_score.get('classification')}",

        f"Base Score: "
        f"{fed_score.get('base_score')}",

        f"SEP Adjustment: "
        f"{fed_score.get('sep_adjustment')}"
    ])

    dimensions = data.get(
        "phase_2b",
        {}
    ).get(
        "combined",
        {}
    )

    for name, dimension in dimensions.items():

        lines.append(
            f"{name.capitalize()}: "
            f"{dimension['score_100']}/100"
        )

    # --------------------------------------------------------
    # PHASE 2C
    # --------------------------------------------------------

    lines.extend([
        "",
        "PHASE 2C — BEIGE BOOK",
        "---------------------"
    ])

    if not beige.get("available"):

        lines.append(
            "Beige Book: UNAVAILABLE"
        )

    else:

        lines.append(
            f"Beige Book: "
            f"{beige.get('title')}"
        )

        lines.append(
            f"Issue: "
            f"{beige.get('issue_date')}"
        )

        lines.append(
            f"Publication: "
            f"{beige.get('publication_date')}"
        )

        lines.append(
            f"Beige Book Score: "
            f"{beige_analysis.get('score')}/100"
        )

        lines.append(
            f"Beige Book Tone: "
            f"{beige_analysis.get('tone')}"
        )

        for reason in beige_analysis.get(
            "reasons",
            []
        ):
            lines.append(reason)

    # --------------------------------------------------------
    # REASONS
    # --------------------------------------------------------

    lines.extend([
        "",
        "REASONS",
        "-------"
    ])

    for reason in data.get(
        "phase_2b",
        {}
    ).get(
        "reasons",
        []
    ):

        lines.append(reason)

    return "\n".join(lines)


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    result = build_fed_intelligence()

    print(
        fed_summary(result)
    )
