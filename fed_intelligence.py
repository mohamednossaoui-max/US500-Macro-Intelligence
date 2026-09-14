# fed_intelligence.py
# ============================================================
# US500 Macro Intelligence
# Federal Reserve Intelligence Engine - Phase 1
#
# Sources:
#   Federal Reserve official website
#
# Analyzes:
#   1. FOMC Statement
#   2. Powell Press Conference / FOMC communication
#   3. FOMC Minutes
#   4. SEP / Projection Materials
#   5. Beige Book
#
# IMPORTANT:
# This module is an analytical layer.
# It does NOT execute trades.
# It does NOT automatically modify the Decision Engine.
# ============================================================

from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIG
# ============================================================

FED_BASE = "https://www.federalreserve.gov"

FOMC_CALENDAR_URL = (
    "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
)

BEIGE_BOOK_URL = (
    "https://www.federalreserve.gov/monetarypolicy/"
    "publications/beige-book-default.htm"
)

REQUEST_TIMEOUT = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}


# ============================================================
# HTTP HELPERS
# ============================================================

def fetch_html(url: str) -> str:
    """
    Download an official Federal Reserve HTML page.
    Returns empty string if the request fails.
    """
    try:
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        return response.text

    except Exception:
        return ""


def clean_text(html: str) -> str:
    """
    Convert HTML into normalized plain text.
    """
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(
        ["script", "style", "noscript", "svg"]
    ):
        tag.decompose()

    text = soup.get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# TEXT ANALYSIS
# ============================================================

HAWKISH_TERMS = [
    "higher for longer",
    "restrictive",
    "restrictive policy",
    "inflation remains elevated",
    "inflation remains high",
    "persistent inflation",
    "inflation pressures",
    "upside risks to inflation",
    "upside risk to inflation",
    "additional tightening",
    "tighten policy",
    "tightening policy",
    "rate increase",
    "rate increases",
    "raise the target range",
    "higher policy rate",
    "higher policy rates",
    "strong labor market",
    "strong economic activity",
    "robust economic activity",
]

DOVISH_TERMS = [
    "rate cut",
    "rate cuts",
    "lower rates",
    "lower policy rate",
    "lower policy rates",
    "easing policy",
    "ease policy",
    "easing financial conditions",
    "dovish",
    "weaker labor market",
    "labor market has cooled",
    "labor market cooling",
    "economic activity slowed",
    "economic activity weakened",
    "growth slowed",
    "growth weakened",
    "downside risks",
    "downside risk",
    "inflation has eased",
    "inflation eased",
    "inflation moving lower",
]

INFLATION_TERMS = [
    "inflation",
    "price pressures",
    "price pressure",
    "prices",
    "pce inflation",
    "core pce",
    "consumer prices",
]

LABOR_TERMS = [
    "employment",
    "labor market",
    "labour market",
    "unemployment",
    "job gains",
    "payroll",
    "wages",
    "wage growth",
]

GROWTH_TERMS = [
    "economic activity",
    "economic growth",
    "growth",
    "consumer spending",
    "household spending",
    "business investment",
    "manufacturing",
    "services",
]

FINANCIAL_TERMS = [
    "financial conditions",
    "financial stability",
    "credit conditions",
    "banking",
    "credit",
    "liquidity",
    "financial markets",
]


def count_terms(text: str, terms: List[str]) -> int:
    """
    Count occurrences of a group of keywords.
    """
    if not text:
        return 0

    text_lower = text.lower()

    score = 0

    for term in terms:
        score += text_lower.count(term.lower())

    return score


def tone_score(text: str) -> int:
    """
    Basic document tone score.

    Positive = hawkish
    Negative = dovish
    Zero = neutral

    This is deliberately transparent and rule-based in Phase 1.
    """

    if not text:
        return 0

    hawkish = count_terms(
        text,
        HAWKISH_TERMS,
    )

    dovish = count_terms(
        text,
        DOVISH_TERMS,
    )

    raw = hawkish - dovish

    # Prevent one long document from producing an enormous score.
    if raw > 20:
        raw = 20

    if raw < -20:
        raw = -20

    return raw


def classify_tone(score: int) -> str:
    """
    Convert raw tone score into a readable classification.
    """

    if score >= 8:
        return "HAWKISH"

    if score >= 3:
        return "MODERATELY HAWKISH"

    if score <= -8:
        return "DOVISH"

    if score <= -3:
        return "MODERATELY DOVISH"

    return "NEUTRAL"


# ============================================================
# DOCUMENT PROFILE
# ============================================================

def analyze_document(
    name: str,
    text: str,
) -> Dict:

    if not text:
        return {
            "name": name,
            "available": False,
            "tone_score": None,
            "tone": "UNAVAILABLE",
            "inflation_mentions": 0,
            "labor_mentions": 0,
            "growth_mentions": 0,
            "financial_mentions": 0,
        }

    score = tone_score(text)

    return {
        "name": name,
        "available": True,
        "tone_score": score,
        "tone": classify_tone(score),
        "inflation_mentions": count_terms(
            text,
            INFLATION_TERMS,
        ),
        "labor_mentions": count_terms(
            text,
            LABOR_TERMS,
        ),
        "growth_mentions": count_terms(
            text,
            GROWTH_TERMS,
        ),
        "financial_mentions": count_terms(
            text,
            FINANCIAL_TERMS,
        ),
        "text_length": len(text),
    }


# ============================================================
# FOMC CALENDAR DISCOVERY
# ============================================================

def get_fomc_links() -> Dict[str, str]:
    """
    Discover useful FOMC links from the official calendar.

    Returns the latest links that can be identified from
    the Federal Reserve calendar page.
    """

    html = fetch_html(FOMC_CALENDAR_URL)

    if not html:
        return {}

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    links = {}

    for a in soup.find_all("a", href=True):

        href = a.get("href", "").strip()

        text = a.get_text(
            " ",
            strip=True,
        ).lower()

        if not href:
            continue

        if href.startswith("/"):
            full_url = FED_BASE + href
        elif href.startswith("http"):
            full_url = href
        else:
            continue

        # Minutes
        if (
            "minutes" in text
            or "fomcminutes" in href.lower()
        ):
            links.setdefault(
                "minutes",
                full_url,
            )

        # Press conference
        if (
            "press conference" in text
            or "fomcpresconf" in href.lower()
        ):
            links.setdefault(
                "press_conference",
                full_url,
            )

        # Projection materials / SEP
        if (
            "projection" in text
            or "fomcproj" in href.lower()
        ):
            links.setdefault(
                "sep",
                full_url,
            )

        # FOMC statement
        if (
            "statement" in text
            or "fomcstmt" in href.lower()
        ):
            links.setdefault(
                "statement",
                full_url,
            )

    return links


# ============================================================
# FOMC DOCUMENT FETCHING
# ============================================================

def fetch_fomc_statement() -> Dict:

    links = get_fomc_links()

    url = links.get("statement")

    if not url:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    html = fetch_html(url)

    text = clean_text(html)

    return {
        "available": bool(text),
        "url": url,
        "text": text,
    }


def fetch_fomc_minutes() -> Dict:

    links = get_fomc_links()

    url = links.get("minutes")

    if not url:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    html = fetch_html(url)

    text = clean_text(html)

    return {
        "available": bool(text),
        "url": url,
        "text": text,
    }


def fetch_press_conference() -> Dict:

    links = get_fomc_links()

    url = links.get("press_conference")

    if not url:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    html = fetch_html(url)

    text = clean_text(html)

    return {
        "available": bool(text),
        "url": url,
        "text": text,
    }


def fetch_sep() -> Dict:

    links = get_fomc_links()

    url = links.get("sep")

    if not url:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    html = fetch_html(url)

    text = clean_text(html)

    return {
        "available": bool(text),
        "url": url,
        "text": text,
    }


# ============================================================
# BEIGE BOOK
# ============================================================

def fetch_beige_book() -> Dict:
    """
    Fetch the official Beige Book index and identify the
    latest available report.
    """

    html = fetch_html(
        BEIGE_BOOK_URL
    )

    if not html:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # Find links that point to Beige Book summaries.
    candidates = []

    for a in soup.find_all("a", href=True):

        href = a.get("href", "")

        text = a.get_text(
            " ",
            strip=True,
        )

        if (
            "beigebook" in href.lower()
            and (
                "html" in text.lower()
                or "pdf" in text.lower()
            )
        ):

            if href.startswith("/"):
                href = FED_BASE + href

            candidates.append(
                (
                    text,
                    href,
                )
            )

    # Prefer the first HTML report found.
    selected_url = None

    for label, url in candidates:

        if "html" in label.lower():
            selected_url = url
            break

    if selected_url is None and candidates:
        selected_url = candidates[0][1]

    if not selected_url:
        return {
            "available": False,
            "url": None,
            "text": "",
        }

    report_html = fetch_html(
        selected_url
    )

    text = clean_text(
        report_html
    )

    return {
        "available": bool(text),
        "url": selected_url,
        "text": text,
    }


# ============================================================
# DOCUMENT SHIFT
# ============================================================

def calculate_shift(
    current_score: Optional[int],
    previous_score: Optional[int],
) -> Dict:

    if (
        current_score is None
        or previous_score is None
    ):
        return {
            "available": False,
            "delta": None,
            "classification": "UNAVAILABLE",
        }

    delta = (
        current_score
        - previous_score
    )

    if delta >= 5:
        classification = "HAWKISH SHIFT"

    elif delta >= 2:
        classification = "SLIGHTLY HAWKISH"

    elif delta <= -5:
        classification = "DOVISH SHIFT"

    elif delta <= -2:
        classification = "SLIGHTLY DOVISH"

    else:
        classification = "NO MAJOR SHIFT"

    return {
        "available": True,
        "delta": delta,
        "classification": classification,
    }


# ============================================================
# FED INTELLIGENCE SCORE
# ============================================================

def weighted_fed_score(
    document_scores: Dict[str, int]
) -> Optional[int]:

    """
    Initial Phase-1 weighted score.

    IMPORTANT:
    These weights are provisional.
    They must be validated with historical backtesting
    before they influence trade decisions.
    """

    weights = {
        "fomc": 0.25,
        "powell": 0.25,
        "sep": 0.25,
        "minutes": 0.15,
        "beige_book": 0.10,
    }

    available_weight = 0.0
    weighted_sum = 0.0

    for key, weight in weights.items():

        value = document_scores.get(
            key
        )

        if value is None:
            continue

        available_weight += weight

        weighted_sum += (
            value * weight
        )

    if available_weight == 0:
        return None

    score = (
        weighted_sum
        / available_weight
    )

    # Convert raw keyword score to
    # approximately -10 to +10.
    normalized = round(
        score / 2
    )

    normalized = max(
        -10,
        min(10, normalized),
    )

    return normalized


def classify_fed_score(
    score: Optional[int]
) -> str:

    if score is None:
        return "UNAVAILABLE"

    if score >= 6:
        return "STRONGLY HAWKISH"

    if score >= 3:
        return "MODERATELY HAWKISH"

    if score <= -6:
        return "STRONGLY DOVISH"

    if score <= -3:
        return "MODERATELY DOVISH"

    return "NEUTRAL / MIXED"


# ============================================================
# FULL FED INTELLIGENCE ANALYSIS
# ============================================================

def build_fed_intelligence() -> Dict:
    """
    Main entry point.

    Fetches available Federal Reserve documents and
    produces a transparent analytical structure.
    """

    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "source": FED_BASE,
        "documents": {},
        "fed_score": None,
        "fed_classification": "UNAVAILABLE",
        "links": {},
    }

    # --------------------------------------------------------
    # FOMC Statement
    # --------------------------------------------------------

    statement = fetch_fomc_statement()

    statement_analysis = analyze_document(
        "FOMC Statement",
        statement.get(
            "text",
            "",
        ),
    )

    result["documents"]["fomc"] = (
        statement_analysis
    )

    if statement.get("url"):
        result["links"]["fomc"] = (
            statement["url"]
        )

    # --------------------------------------------------------
    # Powell
    # --------------------------------------------------------

    press = fetch_press_conference()

    press_analysis = analyze_document(
        "Powell Press Conference",
        press.get(
            "text",
            "",
        ),
    )

    result["documents"]["powell"] = (
        press_analysis
    )

    if press.get("url"):
        result["links"]["powell"] = (
            press["url"]
        )

    # --------------------------------------------------------
    # Minutes
    # --------------------------------------------------------

    minutes = fetch_fomc_minutes()

    minutes_analysis = analyze_document(
        "FOMC Minutes",
        minutes.get(
            "text",
            "",
        ),
    )

    result["documents"]["minutes"] = (
        minutes_analysis
    )

    if minutes.get("url"):
        result["links"]["minutes"] = (
            minutes["url"]
        )

    # --------------------------------------------------------
    # SEP
    # --------------------------------------------------------

    sep = fetch_sep()

    sep_analysis = analyze_document(
        "SEP",
        sep.get(
            "text",
            "",
        ),
    )

    result["documents"]["sep"] = (
        sep_analysis
    )

    if sep.get("url"):
        result["links"]["sep"] = (
            sep["url"]
        )

    # --------------------------------------------------------
    # Beige Book
    # --------------------------------------------------------

    beige = fetch_beige_book()

    beige_analysis = analyze_document(
        "Beige Book",
        beige.get(
            "text",
            "",
        ),
    )

    result["documents"]["beige_book"] = (
        beige_analysis
    )

    if beige.get("url"):
        result["links"]["beige_book"] = (
            beige["url"]
        )

    # --------------------------------------------------------
    # Combined Score
    # --------------------------------------------------------

    document_scores = {}

    for key, data in result[
        "documents"
    ].items():

        document_scores[key] = data.get(
            "tone_score"
        )

    fed_score = weighted_fed_score(
        document_scores
    )

    result["fed_score"] = fed_score

    result["fed_classification"] = (
        classify_fed_score(
            fed_score
        )
    )

    return result


# ============================================================
# SIMPLE SUMMARY
# ============================================================

def fed_summary(
    analysis: Dict
) -> Dict:

    documents = analysis.get(
        "documents",
        {},
    )

    summary = []

    for key in [
        "fomc",
        "powell",
        "sep",
        "minutes",
        "beige_book",
    ]:

        item = documents.get(
            key,
            {},
        )

        summary.append(
            {
                "document": item.get(
                    "name",
                    key,
                ),
                "tone": item.get(
                    "tone",
                    "UNAVAILABLE",
                ),
                "score": item.get(
                    "tone_score"
                ),
            }
        )

    return {
        "fed_score": analysis.get(
            "fed_score"
        ),
        "classification": analysis.get(
            "fed_classification",
            "UNAVAILABLE",
        ),
        "documents": summary,
    }


# ============================================================
# TEST
# ============================================================

if __name__ == "__main__":

    print(
        "Running Federal Reserve Intelligence Engine..."
    )

    analysis = build_fed_intelligence()

    summary = fed_summary(
        analysis
    )

    print()
    print(
        "FED SCORE:",
        summary["fed_score"],
    )

    print(
        "CLASSIFICATION:",
        summary["classification"],
    )

    print()

    for item in summary[
        "documents"
    ]:

        print(
            f'{item["document"]}: '
            f'{item["tone"]} '
            f'({item["score"]})'
        )
