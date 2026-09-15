"""Federal Reserve Intelligence Engine - Phase 2A.

Analytical only:
- FOMC Statement
- FOMC Minutes
- Fed Chair Press Conference
- Summary of Economic Projections (SEP)
- SEP shift analysis

No trade execution and no Decision Engine integration.
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 US500-Macro-Intelligence/2.0"
}

TIMEOUT = 30


# ============================================================
# HTTP
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


# ============================================================
# URL HELPERS
# ============================================================

def absolute(href: str) -> str:
    if not href:
        return ""

    if href.startswith("http://") or href.startswith("https://"):
        return href

    if href.startswith("/"):
        return FED + href

    return FED + "/" + href.lstrip("./")


# ============================================================
# HTML / PDF TEXT
# ============================================================

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

        return re.sub(
            r"\s+",
            " ",
            text
        ).strip()

    except Exception:
        return ""


# ============================================================
# DATE HELPERS
# ============================================================

def date_from_href(href: str) -> Optional[date]:
    """
    Extract YYYYMMDD from an official Federal Reserve URL.
    """

    m = re.search(
        r"(20\d{6})",
        href or ""
    )

    if not m:
        return None

    try:
        return datetime.strptime(
            m.group(1),
            "%Y%m%d"
        ).date()

    except Exception:
        return None


# ============================================================
# FED DOCUMENT DISCOVERY
# ============================================================

def discover_links() -> Dict[str, Dict[date, str]]:
    """
    Discover official FOMC document links indexed by document date.

    The Federal Reserve uses several URL formats. In particular,
    FOMC statements can appear as monetaryYYYYMMDDa.htm rather
    than fomcstmtYYYYMMDD.htm.
    """

    result = {
        "statement": {},
        "minutes": {},
        "press": {},
        "sep": {},
    }

    r = get(CALENDAR)

    if r is None:
        return result

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    for a in soup.find_all("a", href=True):

        href = a.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        url = absolute(href)

        d = date_from_href(href)

        if not d:
            continue

        h = href.lower()

        label = a.get_text(
            " ",
            strip=True
        ).lower()

        # ----------------------------------------------------
        # FOMC STATEMENT
        # ----------------------------------------------------

        if (
            (
                "monetary" in h
                and re.search(
                    r"monetary\d{8}a\.htm",
                    h
                )
            )
            or (
                "fomcstmt" in h
            )
            or (
                "statement" in label
                and "minutes" not in label
            )
        ):
            result["statement"][d] = url

        # ----------------------------------------------------
        # FOMC MINUTES
        # ----------------------------------------------------

        elif (
            "fomcminutes" in h
            or "minutes" in label
        ):
            result["minutes"][d] = url

        # ----------------------------------------------------
        # PRESS CONFERENCE
        # ----------------------------------------------------

        elif (
            "fomcpresconf" in h
            or "press conference" in label
        ):
            result["press"][d] = url

        # ----------------------------------------------------
        # SEP
        # ----------------------------------------------------

        elif (
            "fomcproj" in h
            or "projection materials" in label
        ):
            result["sep"][d] = url

    return result


# ============================================================
# FOMC DATE SELECTION
# ============================================================

def latest_completed_fomc(
    links: Dict[str, Dict[date, str]],
    as_of: Optional[date] = None
) -> Optional[date]:
    """
    Return the latest FOMC document date that is not in the future.

    This deliberately excludes a future/ongoing meeting.
    """

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

    ds = [
        d
        for d in links.get("sep", {})
        if d <= as_of
    ]

    return max(ds) if ds else None


def previous_sep(
    links: Dict[str, Dict[date, str]],
    current: date
) -> Optional[date]:

    ds = [
        d
        for d in links.get("sep", {})
        if d < current
    ]

    return max(ds) if ds else None


# ============================================================
# DOCUMENT FETCH
# ============================================================

def fetch_document(url: str) -> str:
    if not url:
        return ""

    if url.lower().endswith(".pdf"):
        return pdf_text(url)

    r = get(url)

    return (
        clean_html(r.text)
        if r is not None
        else ""
    )


# ============================================================
# PRESS CONFERENCE
# ============================================================

def press_page_data(url: str) -> Dict:
    """
    Fetch the official FOMC press conference page and,
    when available, its official PDF transcript.
    """

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

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        str(x).replace("−", "-")
    )

    return (
        float(m.group())
        if m
        else None
    )


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
    """
    Read official accessible SEP HTML tables.
    PDF/text fallback is used if necessary.
    """

    out = {
        "sep_date": sep_date.isoformat(),
        "url": url,
        "available": False,
        "year": sep_date.year,
        "gdp": None,
        "unemployment": None,
        "pce": None,
        "core_pce": None,
        "fed_funds": None,
    }

    if not url:
        return out

    # --------------------------------------------------------
    # HTML TABLES
    # --------------------------------------------------------

    try:
        tables = pd.read_html(url)

    except Exception:
        tables = []

    targets = {
        "gdp": "changeinrealgdp",
        "unemployment": "unemploymentrate",
        "pce": "pceinflation",
        "core_pce": "corepceinflation",
        "fed_funds": "federalfundsrate",
    }

    for df in tables:

        if df.empty:
            continue

        for _, row in df.iterrows():

            first = _norm(
                row.iloc[0]
            )

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

    # --------------------------------------------------------
    # TEXT FALLBACK
    # --------------------------------------------------------

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
            r"Federal funds rate.{0,120}?\b(\d+\.\d)\b",
    }

    for field, pat in patterns.items():

        m = re.search(
            pat,
            text,
            re.I
        )

        if m:
            out[field] = float(
                m.group(1)
            )

    out["available"] = any(
        out[k] is not None
        for k in targets
    )

    return out


# ============================================================
# SEP SHIFT
# ============================================================

def sep_shift(
    current: Dict,
    previous: Dict
) -> Dict:

    fields = [
        "gdp",
        "unemployment",
        "pce",
        "core_pce",
        "fed_funds",
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

        # Higher inflation / higher policy rate
        # = more hawkish
        if f in (
            "pce",
            "core_pce",
            "fed_funds"
        ):

            hawkish += change > 0
            dovish += change < 0

        # Higher GDP = hawkish
        elif f == "gdp":

            hawkish += change > 0
            dovish += change < 0

        # Higher unemployment = dovish
        elif f == "unemployment":

            dovish += change > 0
            hawkish += change < 0

    classification = (
        "HAWKISH SHIFT"
        if hawkish > dovish
        else
        "DOVISH SHIFT"
        if dovish > hawkish
        else
        "MIXED / NEUTRAL SHIFT"
    )

    return {
        "classification": classification,
        "hawkish_points": int(hawkish),
        "dovish_points": int(dovish),
        "fields": result,
    }


# ============================================================
# TONE
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


def tone_score(
    text: str
) -> int:

    if not text:
        return 0

    score = (
        count_terms(text, HAWKISH)
        -
        count_terms(text, DOVISH)
    )

    return max(
        -20,
        min(20, score)
    )


def tone(
    score: int
) -> str:

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
            "tone_score": None,
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
                "price pressures",
            ],
        ),

        "labor_mentions": count_terms(
            text,
            [
                "employment",
                "labor market",
                "unemployment",
                "job gains",
                "wages",
            ],
        ),

        "growth_mentions": count_terms(
            text,
            [
                "economic activity",
                "economic growth",
                "growth",
                "consumer spending",
            ],
        ),

        "financial_mentions": count_terms(
            text,
            [
                "financial conditions",
                "financial stability",
                "credit conditions",
                "banking",
                "liquidity",
            ],
        ),

        "text_length": len(text),
    }


# ============================================================
# FED CHAIR
# ============================================================

# Kevin Warsh became Federal Reserve Chair
# on May 22, 2026.

FED_CHAIR_TRANSITION = date(
    2026,
    5,
    22
)


def fed_chair_for_date(
    document_date: Optional[date]
) -> str:
    """
    Return the Federal Reserve Chair applicable
    to a document date.

    Before May 22, 2026:
        Jerome Powell

    From May 22, 2026:
        Kevin Warsh
    """

    if (
        document_date is not None
        and document_date >= FED_CHAIR_TRANSITION
    ):
        return "Kevin Warsh"

    return "Jerome Powell"


# ============================================================
# MAIN FED INTELLIGENCE BUILDER
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
            "error": "No completed FOMC meeting found.",
        }

    # --------------------------------------------------------
    # DOCUMENT URLS
    # --------------------------------------------------------

    statement_url = links[
        "statement"
    ].get(
        meeting,
        ""
    )

    minutes_url = links[
        "minutes"
    ].get(
        meeting,
        ""
    )

    press_url = links[
        "press"
    ].get(
        meeting,
        ""
    )

    # --------------------------------------------------------
    # DOCUMENT TEXT
    # --------------------------------------------------------

    statement_text = fetch_document(
        statement_url
    )

    minutes_text = fetch_document(
        minutes_url
    )

    press = press_page_data(
        press_url
    )

    # --------------------------------------------------------
    # HISTORICAL FED CHAIR
    # --------------------------------------------------------

    chair_name = fed_chair_for_date(
        meeting
    )

    # --------------------------------------------------------
    # SEP
    # --------------------------------------------------------

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
    # RETURN
    # --------------------------------------------------------

    return {

        "available": True,

        "as_of_date":
            today.isoformat(),

        "latest_fomc":
            meeting.isoformat(),

        "current_date":
            today.isoformat(),

        # ----------------------------------------------------
        # FED CHAIR
        # ----------------------------------------------------

        "fed_chair":
            chair_name,

        # ----------------------------------------------------
        # FOMC STATEMENT
        # ----------------------------------------------------

        "statement":
            analyze(
                "FOMC Statement",
                statement_text
            ),

        "statement_source":
            statement_url,

        # ----------------------------------------------------
        # FOMC MINUTES
        # ----------------------------------------------------

        "minutes":
            analyze(
                "FOMC Minutes",
                minutes_text
            ),

        "minutes_source":
            minutes_url,

        # ----------------------------------------------------
        # FED CHAIR PRESS CONFERENCE
        # ----------------------------------------------------

        "chair":
            analyze(
                f"{chair_name} Press Conference",
                press["text"]
            ),

        "chair_page":
            press["page_url"],

        "chair_pdf":
            press["pdf_url"],

        # ----------------------------------------------------
        # SEP
        # ----------------------------------------------------

        "latest_sep_date":
            (
                current_sep_date.isoformat()
                if current_sep_date
                else None
            ),

        "previous_sep_date":
            (
                prev_sep_date.isoformat()
                if prev_sep_date
                else None
            ),

        "sep_current":
            current_sep,

        "sep_previous":
            previous,

        "sep_shift":
            shift,
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

    lines = [

        "FED INTELLIGENCE",
        "================",

        f"Latest FOMC: "
        f"{data['latest_fomc']}",

        f"Fed Chair: "
        f"{data['fed_chair']}",

        f"Statement: "
        f"{data['statement']['tone']}",

        f"{data['fed_chair']} Press Conference: "
        f"{data['chair']['tone']}",

        f"Minutes: "
        f"{data['minutes']['tone']}",

        f"Latest SEP: "
        f"{data.get('latest_sep_date')}",

        f"Previous SEP: "
        f"{data.get('previous_sep_date')}",
    ]

    if data.get("sep_shift"):

        lines.append(
            "SEP Shift: "
            + data["sep_shift"]["classification"]
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

    return "\n".join(lines)


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    result = build_fed_intelligence()

    print(
        fed_summary(result)
    )
