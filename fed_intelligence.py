"""
Federal Reserve Intelligence Engine - Phase 2C.

Analytical only:
- FOMC Statement
- FOMC Minutes
- Fed Chair Press Conference
- Summary of Economic Projections (SEP)
- SEP shift analysis
- Multi-dimensional Fed Intelligence analysis
- Fed Intelligence Score 0-100
- Beige Book analysis

No trade execution.
No Decision Engine integration.
"""

from __future__ import annotations

import io
import re
from datetime import date, datetime
from typing import Dict, Optional, List

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

CALENDAR = (
    f"{FED}/monetarypolicy/fomccalendars.htm"
)

BEIGE_BOOK = (
    f"{FED}/monetarypolicy/publications/"
    f"beige-book-default.htm"
)

HEADERS = {
    "User-Agent":
        "Mozilla/5.0 US500-Macro-Intelligence/2.0"
}

TIMEOUT = 30


# ============================================================
# HTTP
# ============================================================

def get(
    url: str
) -> Optional[requests.Response]:

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

def absolute(
    href: str
) -> str:

    if not href:
        return ""

    if (
        href.startswith("http://")
        or href.startswith("https://")
    ):
        return href

    if href.startswith("/"):
        return FED + href

    return FED + "/" + href.lstrip("./")


# ============================================================
# HTML / PDF TEXT
# ============================================================

def clean_html(
    html: str
) -> str:

    if not html:
        return ""

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    for x in soup(
        ["script", "style", "noscript", "svg"]
    ):
        x.decompose()

    return re.sub(
        r"\s+",
        " ",
        soup.get_text(
            " ",
            strip=True
        )
    ).strip()


def pdf_text(
    url: str
) -> str:

    if not url or PdfReader is None:
        return ""

    r = get(url)

    if r is None:
        return ""

    try:

        reader = PdfReader(
            io.BytesIO(r.content)
        )

        text = " ".join(
            (
                page.extract_text()
                or ""
            )
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

def date_from_href(
    href: str
) -> Optional[date]:

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
    Discover official FOMC document links.

    Supports:
    - FOMC statements
    - FOMC minutes
    - Press conferences
    - SEP / projection materials
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

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        url = absolute(href)

        d = date_from_href(
            href
        )

        if not d:
            continue

        h = href.lower()

        label = a.get_text(
            " ",
            strip=True
        ).lower()

        # ----------------------------------------------------
        # STATEMENT
        # ----------------------------------------------------

        if (
            (
                "monetary" in h
                and re.search(
                    r"monetary\d{8}a\.htm",
                    h
                )
            )
            or "fomcstmt" in h
            or (
                "statement" in label
                and "minutes" not in label
            )
        ):

            result[
                "statement"
            ][d] = url

        # ----------------------------------------------------
        # MINUTES
        # ----------------------------------------------------

        elif (
            "fomcminutes" in h
            or "minutes" in label
        ):

            result[
                "minutes"
            ][d] = url

        # ----------------------------------------------------
        # PRESS CONFERENCE
        # ----------------------------------------------------

        elif (
            "fomcpresconf" in h
            or "press conference" in label
        ):

            result[
                "press"
            ][d] = url

        # ----------------------------------------------------
        # SEP
        # ----------------------------------------------------

        elif (
            "fomcproj" in h
            or "projection materials" in label
        ):

            result[
                "sep"
            ][d] = url

    return result


# ============================================================
# FOMC DATE SELECTION
# ============================================================

def latest_completed_fomc(
    links: Dict[str, Dict[date, str]],
    as_of: Optional[date] = None
) -> Optional[date]:

    as_of = as_of or date.today()

    dates = (
        set(
            links.get(
                "statement",
                {}
            )
        )
        |
        set(
            links.get(
                "minutes",
                {}
            )
        )
        |
        set(
            links.get(
                "press",
                {}
            )
        )
    )

    done = [
        d
        for d in dates
        if d <= as_of
    ]

    return (
        max(done)
        if done
        else None
    )


def latest_sep(
    links: Dict[str, Dict[date, str]],
    as_of: Optional[date] = None
) -> Optional[date]:

    as_of = as_of or date.today()

    ds = [
        d
        for d in links.get(
            "sep",
            {}
        )
        if d <= as_of
    ]

    return (
        max(ds)
        if ds
        else None
    )


def previous_sep(
    links: Dict[str, Dict[date, str]],
    current: date
) -> Optional[date]:

    ds = [
        d
        for d in links.get(
            "sep",
            {}
        )
        if d < current
    ]

    return (
        max(ds)
        if ds
        else None
    )


# ============================================================
# DOCUMENT FETCH
# ============================================================

def fetch_document(
    url: str
) -> str:

    if not url:
        return ""

    if url.lower().endswith(
        ".pdf"
    ):

        return pdf_text(
            url
        )

    r = get(url)

    if r is None:
        return ""

    return clean_html(
        r.text
    )


# ============================================================
# PRESS CONFERENCE
# ============================================================

def press_page_data(
    url: str
) -> Dict:

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

    for a in soup.find_all(
        "a",
        href=True
    ):

        label = a.get_text(
            " ",
            strip=True
        ).lower()

        href = absolute(
            a.get(
                "href",
                ""
            )
        )

        if (
            href.lower().endswith(
                ".pdf"
            )
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
        else clean_html(
            r.text
        )
    )

    return {
        "page_url":
            url,

        "pdf_url":
            pdf or None,

        "text":
            text
    }


# ============================================================
# SEP HELPERS
# ============================================================

def _num(x):

    if x is None:
        return None

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        str(x).replace(
            "−",
            "-"
        )
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


# ============================================================
# SEP EXTRACTION
# ============================================================

def extract_sep(
    url: str,
    sep_date: date
) -> Dict:

    out = {

        "sep_date":
            sep_date.isoformat(),

        "url":
            url,

        "available":
            False,

        "year":
            sep_date.year,

        "gdp":
            None,

        "unemployment":
            None,

        "pce":
            None,

        "core_pce":
            None,

        "fed_funds":
            None,
    }

    if not url:
        return out

    # --------------------------------------------------------
    # HTML TABLES
    # --------------------------------------------------------

    try:

        tables = pd.read_html(
            url
        )

    except Exception:

        tables = []

    targets = {

        "gdp":
            "changeinrealgdp",

        "unemployment":
            "unemploymentrate",

        "pce":
            "pceinflation",

        "core_pce":
            "corepceinflation",

        "fed_funds":
            "federalfundsrate",
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
                        v
                        for v in vals
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

    text = fetch_document(
        url
    )

    out["available"] = bool(
        text
    )

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

        c = current.get(
            f
        )

        p = previous.get(
            f
        )

        change = (
            round(
                c - p,
                2
            )
            if (
                c is not None
                and p is not None
            )
            else None
        )

        result[f] = {

            "current":
                c,

            "previous":
                p,

            "change":
                change,
        }

        if (
            change is None
            or change == 0
        ):
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

        "classification":
            classification,

        "hawkish_points":
            int(hawkish),

        "dovish_points":
            int(dovish),

        "fields":
            result,
    }


# ============================================================
# BASIC TONE
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

    "inflationary pressures",

    "tight monetary policy",

    "policy remains restrictive",
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

    "policy easing",

    "monetary easing",

    "lower policy rate",

    "lower policy rates",
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
        count_terms(
            text,
            HAWKISH
        )
        -
        count_terms(
            text,
            DOVISH
        )
    )

    return max(
        -20,
        min(
            20,
            score
        )
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


# ============================================================
# DOCUMENT ANALYSIS
# ============================================================

def analyze(
    name: str,
    text: str
) -> Dict:

    if not text:

        return {

            "name":
                name,

            "available":
                False,

            "tone":
                "UNAVAILABLE",

            "tone_score":
                None,
        }

    s = tone_score(
        text
    )

    return {

        "name":
            name,

        "available":
            True,

        "tone":
            tone(s),

        "tone_score":
            s,

        "inflation_mentions":
            count_terms(
                text,
                [
                    "inflation",
                    "prices",
                    "price pressures",
                    "inflation pressures",
                ]
            ),

        "labor_mentions":
            count_terms(
                text,
                [
                    "employment",
                    "labor market",
                    "unemployment",
                    "job gains",
                    "wages",
                    "payroll",
                ]
            ),

        "growth_mentions":
            count_terms(
                text,
                [
                    "economic activity",
                    "economic growth",
                    "growth",
                    "consumer spending",
                    "demand",
                    "output",
                ]
            ),

        "financial_mentions":
            count_terms(
                text,
                [
                    "financial conditions",
                    "financial stability",
                    "credit conditions",
                    "banking",
                    "liquidity",
                    "credit",
                ]
            ),

        "text_length":
            len(text),
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

    if (
        document_date is not None
        and document_date >=
        FED_CHAIR_TRANSITION
    ):

        return "Kevin Warsh"

    return "Jerome Powell"


# ============================================================
# PHASE 2B — DIRECTIONAL LANGUAGE
# ============================================================

DIMENSION_SIGNALS = {

    "inflation": {

        "hawkish": [

            "inflation remains elevated",

            "inflation remains high",

            "inflation has moved up",

            "inflation increased",

            "inflation picked up",

            "inflation pressures remain",

            "price pressures remain",

            "upside risks to inflation",

            "inflationary pressures",

            "persistent inflation",

            "higher inflation",

            "inflation expectations increased",

            "inflation expectations remain elevated",
        ],

        "dovish": [

            "inflation has eased",

            "inflation eased",

            "inflation declined",

            "inflation moderated",

            "inflation moved lower",

            "price pressures eased",

            "inflation pressures eased",

            "inflation expectations declined",

            "inflation expectations eased",

            "further progress on inflation",
        ],
    },

    "labor": {

        "hawkish": [

            "employment remains strong",

            "job gains remained solid",

            "job gains remain strong",

            "labor market remains tight",

            "labor market remains strong",

            "wage pressures remain",

            "wages increased",

            "employment increased",

            "employment grew",

            "labor demand remains strong",
        ],

        "dovish": [

            "labor market has cooled",

            "labor market cooled",

            "employment slowed",

            "job gains slowed",

            "job gains weakened",

            "employment declined",

            "unemployment increased",

            "unemployment rose",

            "labor demand weakened",

            "labor market softened",

            "labor market weakened",
        ],
    },

    "growth": {

        "hawkish": [

            "economic activity remains solid",

            "economic activity remains strong",

            "economic growth remained solid",

            "growth remained solid",

            "growth remained strong",

            "consumer spending remained strong",

            "consumer spending increased",

            "demand remains strong",

            "economic activity increased",
        ],

        "dovish": [

            "economic activity slowed",

            "economic activity weakened",

            "growth slowed",

            "growth weakened",

            "economic growth slowed",

            "consumer spending slowed",

            "consumer spending weakened",

            "demand weakened",

            "economic activity declined",

            "economic activity softened",
        ],
    },

    "financial": {

        "hawkish": [

            "financial conditions tightened",

            "financial conditions remain tight",

            "credit conditions tightened",

            "financial conditions restrictive",

            "financial stress increased",
        ],

        "dovish": [

            "financial conditions eased",

            "financial conditions improved",

            "credit conditions eased",

            "credit conditions improved",

            "financial stress declined",
        ],
    },

    "policy": {

        "hawkish": [

            "higher for longer",

            "policy remains restrictive",

            "policy remains restrictive for longer",

            "additional tightening",

            "higher policy rate",

            "higher policy rates",

            "raise the target range",

            "rate increase",

            "rate increases",

            "restrictive policy",

            "restrictive monetary policy",

            "not yet time to ease",

            "not ready to cut",
        ],

        "dovish": [

            "rate cut",

            "rate cuts",

            "lower policy rate",

            "lower policy rates",

            "easing policy",

            "policy easing",

            "monetary easing",

            "begin easing",

            "easier policy",

            "lower rates",

            "time to ease",
        ],
    },
}


# ============================================================
# SIGNAL SCORING
# ============================================================

def dimension_signal(
    text: str,
    dimension: str
) -> Dict:

    if not text:

        return {

            "score":
                0,

            "hawkish":
                0,

            "dovish":
                0,

            "classification":
                "UNAVAILABLE",

            "evidence":
                [],
        }

    low = text.lower()

    signals = DIMENSION_SIGNALS[
        dimension
    ]

    hawkish_hits = []
    dovish_hits = []

    for phrase in signals[
        "hawkish"
    ]:

        count = low.count(
            phrase.lower()
        )

        if count > 0:

            hawkish_hits.extend(
                [phrase] * count
            )

    for phrase in signals[
        "dovish"
    ]:

        count = low.count(
            phrase.lower()
        )

        if count > 0:

            dovish_hits.extend(
                [phrase] * count
            )

    raw = (
        len(hawkish_hits)
        -
        len(dovish_hits)
    )

    score = max(
        -10,
        min(
            10,
            raw
        )
    )

    if score >= 5:

        classification = "HAWKISH"

    elif score >= 2:

        classification = (
            "MODERATELY HAWKISH"
        )

    elif score <= -5:

        classification = "DOVISH"

    elif score <= -2:

        classification = (
            "MODERATELY DOVISH"
        )

    else:

        classification = "NEUTRAL"

    evidence = []

    for phrase in hawkish_hits[:3]:

        evidence.append(
            f"Hawkish: {phrase}"
        )

    for phrase in dovish_hits[:3]:

        evidence.append(
            f"Dovish: {phrase}"
        )

    return {

        "score":
            score,

        "hawkish":
            len(hawkish_hits),

        "dovish":
            len(dovish_hits),

        "classification":
            classification,

        "evidence":
            evidence,
    }


# ============================================================
# DOCUMENT DIMENSION ANALYSIS
# ============================================================

def analyze_dimensions(
    text: str
) -> Dict:

    return {

        dimension:
            dimension_signal(
                text,
                dimension
            )

        for dimension
        in DIMENSION_SIGNALS
    }


# ============================================================
# FED INTELLIGENCE WEIGHTS
# ============================================================

DIMENSION_WEIGHTS = {

    "inflation":
        25,

    "labor":
        15,

    "growth":
        15,

    "financial":
        10,

    "policy":
        35,
}


# ============================================================
# NORMALIZE DIMENSION
# ============================================================

def dimension_to_100(
    score: float
) -> float:

    value = (
        (score + 10)
        / 20
        * 100
    )

    return round(
        max(
            0,
            min(
                100,
                value
            )
        ),
        1
    )


# ============================================================
# FED INTELLIGENCE SCORE
# ============================================================

def calculate_fed_score(
    dimensions: Dict,
    sep_shift_data: Optional[Dict] = None
) -> Dict:

    weighted_sum = 0.0
    total_weight = 0.0

    component_scores = {}

    for dimension, weight in (
        DIMENSION_WEIGHTS.items()
    ):

        item = dimensions.get(
            dimension,
            {}
        )

        score = item.get(
            "score"
        )

        if score is None:
            continue

        normalized = dimension_to_100(
            score
        )

        component_scores[
            dimension
        ] = normalized

        weighted_sum += (
            normalized * weight
        )

        total_weight += weight

    if total_weight == 0:

        base_score = 50.0

    else:

        base_score = (
            weighted_sum
            /
            total_weight
        )

    # --------------------------------------------------------
    # SEP adjustment
    # --------------------------------------------------------

    sep_adjustment = 0.0

    if sep_shift_data:

        classification = (
            sep_shift_data.get(
                "classification",
                ""
            )
        )

        if classification == (
            "HAWKISH SHIFT"
        ):

            sep_adjustment = 5.0

        elif classification == (
            "DOVISH SHIFT"
        ):

            sep_adjustment = -5.0

    final_score = max(
        0,
        min(
            100,
            base_score
            +
            sep_adjustment
        )
    )

    final_score = round(
        final_score,
        1
    )

    if final_score >= 75:

        classification = "HAWKISH"

    elif final_score >= 56:

        classification = (
            "MODERATELY HAWKISH"
        )

    elif final_score >= 45:

        classification = "NEUTRAL"

    elif final_score >= 25:

        classification = (
            "MODERATELY DOVISH"
        )

    else:

        classification = "DOVISH"

    return {

        "score":
            final_score,

        "classification":
            classification,

        "base_score":
            round(
                base_score,
                1
            ),

        "sep_adjustment":
            sep_adjustment,

        "components":
            component_scores,
    }


# ============================================================
# EVIDENCE GENERATOR
# ============================================================

def build_evidence(
    dimensions: Dict,
    sep_shift_data: Optional[Dict] = None
) -> List[str]:

    evidence = []

    ordered = sorted(
        dimensions.items(),
        key=lambda x: abs(
            x[1].get(
                "score",
                0
            )
        ),
        reverse=True
    )

    for dimension, data in ordered:

        score = data.get(
            "score",
            0
        )

        if score == 0:
            continue

        label = dimension.replace(
            "_",
            " "
        ).title()

        classification = data.get(
            "classification",
            "NEUTRAL"
        )

        if score > 0:

            evidence.append(
                f"{label}: "
                f"{classification} "
                f"(+{score})"
            )

        else:

            evidence.append(
                f"{label}: "
                f"{classification} "
                f"({score})"
            )

    if sep_shift_data:

        sep_class = (
            sep_shift_data.get(
                "classification"
            )
        )

        if sep_class:

            evidence.append(
                f"SEP: {sep_class}"
            )

    return evidence[:6]


# ============================================================
# FULL FED ANALYSIS
# ============================================================

def build_deep_fed_analysis(
    statement_text: str,
    minutes_text: str,
    chair_text: str,
    sep_shift_data: Optional[Dict] = None
) -> Dict:

    statement_dimensions = (
        analyze_dimensions(
            statement_text
        )
    )

    minutes_dimensions = (
        analyze_dimensions(
            minutes_text
        )
    )

    chair_dimensions = (
        analyze_dimensions(
            chair_text
        )
    )

    combined = {}

    for dimension in DIMENSION_WEIGHTS:

        s = statement_dimensions[
            dimension
        ].get(
            "score",
            0
        )

        m = minutes_dimensions[
            dimension
        ].get(
            "score",
            0
        )

        c = chair_dimensions[
            dimension
        ].get(
            "score",
            0
        )

        combined_score = (
            s * 0.35
            +
            m * 0.40
            +
            c * 0.25
        )

        combined_score = max(
            -10,
            min(
                10,
                combined_score
            )
        )

        classification = (

            "HAWKISH"
            if combined_score >= 5

            else
            "MODERATELY HAWKISH"
            if combined_score >= 2

            else
            "DOVISH"
            if combined_score <= -5

            else
            "MODERATELY DOVISH"
            if combined_score <= -2

            else
            "NEUTRAL"
        )

        evidence = []

        for source_name, source_data in [

            (
                "Statement",
                statement_dimensions[
                    dimension
                ]
            ),

            (
                "Minutes",
                minutes_dimensions[
                    dimension
                ]
            ),

            (
                "Chair",
                chair_dimensions[
                    dimension
                ]
            ),
        ]:

            if source_data.get(
                "score",
                0
            ) != 0:

                evidence.append(
                    f"{source_name}: "
                    f"{source_data['classification']}"
                )

        combined[
            dimension
        ] = {

            "score":
                round(
                    combined_score,
                    2
                ),

            "classification":
                classification,

            "evidence":
                evidence,
        }

    score = calculate_fed_score(
        combined,
        sep_shift_data
    )

    reasons = build_evidence(
        combined,
        sep_shift_data
    )

    return {

        "score":
            score,

        "dimensions":
            combined,

        "documents":
            {

                "statement":
                    statement_dimensions,

                "minutes":
                    minutes_dimensions,

                "chair":
                    chair_dimensions,
            },

        "reasons":
            reasons,
    }


# ============================================================
# PHASE 2C — BEIGE BOOK
# ============================================================

def discover_latest_beige_book(
    as_of: Optional[date] = None
) -> Dict:

    as_of = as_of or date.today()

    result = {

        "available":
            False,

        "date":
            None,

        "url":
            None,

        "text":
            "",
    }

    r = get(
        BEIGE_BOOK
    )

    if r is None:
        return result

    soup = BeautifulSoup(
        r.text,
        "html.parser"
    )

    candidates = []

    for a in soup.find_all(
        "a",
        href=True
    ):

        href = a.get(
            "href",
            ""
        ).strip()

        if not href:
            continue

        url = absolute(
            href
        )

        label = a.get_text(
            " ",
            strip=True
        )

        combined = (
            f"{label} {href}"
        ).lower()

        if (
            "beige book"
            not in combined
        ):
            continue

        # ----------------------------------------------------
        # YYYY-MM-DD / YYYY_MM_DD / YYYY/MM/DD
        # ----------------------------------------------------

        dates = re.findall(
            r"(20\d{2})[-_/]"
            r"(\d{1,2})[-_/]"
            r"(\d{1,2})",
            combined
        )

        for y, m, d in dates:

            try:

                dt = date(
                    int(y),
                    int(m),
                    int(d)
                )

                if dt <= as_of:

                    candidates.append(
                        (
                            dt,
                            url
                        )
                    )

            except Exception:

                continue

        # ----------------------------------------------------
        # YYYYMMDD
        # ----------------------------------------------------

        dt = date_from_href(
            href
        )

        if (
            dt
            and dt <= as_of
        ):

            candidates.append(
                (
                    dt,
                    url
                )
            )

    # --------------------------------------------------------
    # If page links don't expose a date, try text patterns
    # --------------------------------------------------------

    if not candidates:

        page_text = clean_html(
            r.text
        )

        date_patterns = re.findall(
            r"(20\d{2})[-/]"
            r"(\d{1,2})[-/]"
            r"(\d{1,2})",
            page_text
        )

        for y, m, d in date_patterns:

            try:

                dt = date(
                    int(y),
                    int(m),
                    int(d)
                )

                if dt <= as_of:

                    candidates.append(
                        (
                            dt,
                            BEIGE_BOOK
                        )
                    )

            except Exception:

                continue

    if not candidates:
        return result

    # Remove duplicate pairs.
    candidates = list(
        {
            (dt, url)
            for dt, url in candidates
        }
    )

    candidates.sort(
        key=lambda x: x[0],
        reverse=True
    )

    latest_date, latest_url = (
        candidates[0]
    )

    text = fetch_document(
        latest_url
    )

    # --------------------------------------------------------
    # Some Beige Book links point to an HTML page that links
    # to the actual PDF. If text is too short, inspect links.
    # --------------------------------------------------------

    if (
        not text
        or len(text) < 1000
    ):

        page_response = get(
            latest_url
        )

        if page_response is not None:

            page_soup = BeautifulSoup(
                page_response.text,
                "html.parser"
            )

            pdf_candidates = []

            for a in page_soup.find_all(
                "a",
                href=True
            ):

                href = absolute(
                    a.get(
                        "href",
                        ""
                    )
                )

                label = a.get_text(
                    " ",
                    strip=True
                ).lower()

                if (
                    href.lower().endswith(
                        ".pdf"
                    )
                    and (
                        "beige" in label
                        or "beige" in href.lower()
                    )
                ):

                    pdf_candidates.append(
                        href
                    )

            if pdf_candidates:

                pdf_url = (
                    pdf_candidates[0]
                )

                pdf_content = pdf_text(
                    pdf_url
                )

                if pdf_content:

                    text = pdf_content

                    latest_url = pdf_url

    result.update({

        "available":
            bool(text),

        "date":
            latest_date.isoformat(),

        "url":
            latest_url,

        "text":
            text,
    })

    return result


# ============================================================
# BEIGE BOOK DIMENSION SIGNALS
# ============================================================

BEIGE_DIMENSION_SIGNALS = {

    "growth": {

        "hawkish": [

            "economic activity increased",

            "economic activity grew",

            "activity increased",

            "activity grew",

            "consumer spending increased",

            "consumer spending grew",

            "manufacturing activity increased",

            "demand increased",

            "business activity increased",

            "output increased",
        ],

        "dovish": [

            "economic activity declined",

            "economic activity decreased",

            "activity declined",

            "activity decreased",

            "consumer spending declined",

            "consumer spending decreased",

            "manufacturing activity declined",

            "demand declined",

            "business activity declined",

            "output declined",
        ],
    },

    "labor": {

        "hawkish": [

            "employment increased",

            "employment grew",

            "hiring increased",

            "hiring picked up",

            "labor demand increased",

            "labor demand remained strong",

            "wage growth increased",

            "wage pressures increased",
        ],

        "dovish": [

            "employment declined",

            "employment decreased",

            "hiring slowed",

            "hiring declined",

            "labor demand weakened",

            "labor demand declined",

            "wage growth slowed",

            "wage pressures eased",
        ],
    },

    "inflation": {

        "hawkish": [

            "prices increased",

            "prices rose",

            "price pressures increased",

            "price pressures remained elevated",

            "input costs increased",

            "input costs rose",

            "wage pressures remained elevated",

            "inflationary pressures increased",

            "cost pressures increased",
        ],

        "dovish": [

            "prices declined",

            "prices decreased",

            "price pressures eased",

            "price pressures moderated",

            "input costs declined",

            "input costs decreased",

            "cost pressures eased",

            "inflationary pressures eased",
        ],
    },

    "consumer": {

        "hawkish": [

            "consumer spending increased",

            "consumer spending grew",

            "retail sales increased",

            "consumer demand increased",
        ],

        "dovish": [

            "consumer spending declined",

            "consumer spending decreased",

            "consumer spending slowed",

            "retail sales declined",

            "consumer demand weakened",
        ],
    },

    "financial": {

        "hawkish": [

            "financial conditions tightened",

            "credit conditions tightened",

            "lending standards tightened",

            "credit availability decreased",

            "financial stress increased",
        ],

        "dovish": [

            "financial conditions eased",

            "financial conditions improved",

            "credit conditions eased",

            "credit availability improved",

            "financial stress declined",
        ],
    },
}


# ============================================================
# BEIGE BOOK DIMENSION ANALYSIS
# ============================================================

def beige_dimension_signal(
    text: str,
    dimension: str
) -> Dict:

    if not text:

        return {

            "score":
                0,

            "hawkish":
                0,

            "dovish":
                0,

            "classification":
                "UNAVAILABLE",

            "evidence":
                [],
        }

    low = text.lower()

    signals = (
        BEIGE_DIMENSION_SIGNALS[
            dimension
        ]
    )

    hawkish_hits = []
    dovish_hits = []

    for phrase in signals[
        "hawkish"
    ]:

        count = low.count(
            phrase.lower()
        )

        if count:

            hawkish_hits.extend(
                [phrase] * count
            )

    for phrase in signals[
        "dovish"
    ]:

        count = low.count(
            phrase.lower()
        )

        if count:

            dovish_hits.extend(
                [phrase] * count
            )

    raw = (
        len(hawkish_hits)
        -
        len(dovish_hits)
    )

    score = max(
        -10,
        min(
            10,
            raw
        )
    )

    if score >= 5:

        classification = "HAWKISH"

    elif score >= 2:

        classification = (
            "MODERATELY HAWKISH"
        )

    elif score <= -5:

        classification = "DOVISH"

    elif score <= -2:

        classification = (
            "MODERATELY DOVISH"
        )

    else:

        classification = "NEUTRAL"

    evidence = []

    for phrase in hawkish_hits[:3]:

        evidence.append(
            f"Hawkish: {phrase}"
        )

    for phrase in dovish_hits[:3]:

        evidence.append(
            f"Dovish: {phrase}"
        )

    return {

        "score":
            score,

        "hawkish":
            len(hawkish_hits),

        "dovish":
            len(dovish_hits),

        "classification":
            classification,

        "evidence":
            evidence,
    }


def analyze_beige_book(
    text: str
) -> Dict:

    dimensions = {

        dimension:
            beige_dimension_signal(
                text,
                dimension
            )

        for dimension
        in BEIGE_DIMENSION_SIGNALS
    }

    # --------------------------------------------------------
    # Beige Book weights
    # --------------------------------------------------------

    weights = {

        "growth":
            25,

        "labor":
            20,

        "inflation":
            30,

        "consumer":
            15,

        "financial":
            10,
    }

    weighted_sum = 0.0
    total_weight = 0.0

    components = {}

    for dimension, weight in (
        weights.items()
    ):

        item = dimensions[
            dimension
        ]

        score = item.get(
            "score",
            0
        )

        normalized = dimension_to_100(
            score
        )

        components[
            dimension
        ] = normalized

        weighted_sum += (
            normalized
            * weight
        )

        total_weight += weight

    if total_weight:

        final_score = (
            weighted_sum
            /
            total_weight
        )

    else:

        final_score = 50.0

    final_score = round(
        max(
            0,
            min(
                100,
                final_score
            )
        ),
        1
    )

    if final_score >= 75:

        classification = "HAWKISH"

    elif final_score >= 56:

        classification = (
            "MODERATELY HAWKISH"
        )

    elif final_score >= 45:

        classification = "NEUTRAL"

    elif final_score >= 25:

        classification = (
            "MODERATELY DOVISH"
        )

    else:

        classification = "DOVISH"

    return {

        "score":
            final_score,

        "classification":
            classification,

        "components":
            components,

        "dimensions":
            dimensions,

        "text_length":
            len(text),
    }


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

            "available":
                False,

            "error":
                "No completed FOMC meeting found.",
        }

    # --------------------------------------------------------
    # URLS
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
    # FED CHAIR
    # --------------------------------------------------------

    chair_name = fed_chair_for_date(
        meeting
    )

    # --------------------------------------------------------
    # BEIGE BOOK — PHASE 2C
    # --------------------------------------------------------

    beige_book = (
        discover_latest_beige_book(
            as_of=today
        )
    )

    beige_analysis = (
        analyze_beige_book(
            beige_book.get(
                "text",
                ""
            )
        )
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
            links[
                "sep"
            ].get(
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
            links[
                "sep"
            ].get(
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

        if (
            current_sep
            and previous
        )

        else {}
    )

    # --------------------------------------------------------
    # BASIC DOCUMENT ANALYSIS
    # --------------------------------------------------------

    statement_analysis = analyze(
        "FOMC Statement",
        statement_text
    )

    minutes_analysis = analyze(
        "FOMC Minutes",
        minutes_text
    )

    chair_analysis = analyze(
        f"{chair_name} Press Conference",
        press["text"]
    )

    # --------------------------------------------------------
    # PHASE 2B DEEP ANALYSIS
    # --------------------------------------------------------

    deep_analysis = (
        build_deep_fed_analysis(

            statement_text=
                statement_text,

            minutes_text=
                minutes_text,

            chair_text=
                press["text"],

            sep_shift_data=
                shift,
        )
    )

    # --------------------------------------------------------
    # RETURN
    # --------------------------------------------------------

    return {

        "available":
            True,

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
        # DOCUMENT ANALYSIS
        # ----------------------------------------------------

        "statement":
            statement_analysis,

        "statement_source":
            statement_url,

        "minutes":
            minutes_analysis,

        "minutes_source":
            minutes_url,

        "chair":
            chair_analysis,

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

        # ----------------------------------------------------
        # PHASE 2B
        # ----------------------------------------------------

        "fed_intelligence":
            deep_analysis,

        # ----------------------------------------------------
        # PHASE 2C — BEIGE BOOK
        # ----------------------------------------------------

        "beige_book":
            beige_book,

        "beige_analysis":
            beige_analysis,
    }


# ============================================================
# SUMMARY
# ============================================================

def fed_summary(
    data: Dict
) -> str:

    if not data.get(
        "available"
    ):

        return (
            "FED INTELLIGENCE unavailable: "
            +
            str(
                data.get(
                    "error",
                    "unknown error"
                )
            )
        )

    fi = data.get(
        "fed_intelligence",
        {}
    )

    score_data = fi.get(
        "score",
        {}
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

        (
            f"{data['fed_chair']} "
            f"Press Conference: "
            f"{data['chair']['tone']}"
        ),

        f"Minutes: "
        f"{data['minutes']['tone']}",

        f"Latest SEP: "
        f"{data.get('latest_sep_date')}",

        f"Previous SEP: "
        f"{data.get('previous_sep_date')}",
    ]

    # --------------------------------------------------------
    # SEP SHIFT
    # --------------------------------------------------------

    if data.get(
        "sep_shift"
    ):

        lines.append(
            "SEP Shift: "
            +
            data[
                "sep_shift"
            ][
                "classification"
            ]
        )

        for k, v in data[
            "sep_shift"
        ][
            "fields"
        ].items():

            lines.append(
                f"{k}: "
                f"{v['previous']} -> "
                f"{v['current']} "
                f"({v['change']})"
            )

    # --------------------------------------------------------
    # PHASE 2B SCORE
    # --------------------------------------------------------

    if score_data:

        lines.extend([

            "",

            "PHASE 2B",

            "---------",

            (
                "Fed Intelligence Score: "
                f"{score_data.get('score')}/100"
            ),

            (
                "Overall Tone: "
                f"{score_data.get('classification')}"
            ),

            (
                "Base Score: "
                f"{score_data.get('base_score')}"
            ),

            (
                "SEP Adjustment: "
                f"{score_data.get('sep_adjustment')}"
            ),
        ])

        components = score_data.get(
            "components",
            {}
        )

        for dimension, value in (
            components.items()
        ):

            lines.append(
                f"{dimension.title()}: "
                f"{value}/100"
            )

    # --------------------------------------------------------
    # PHASE 2C — BEIGE BOOK
    # --------------------------------------------------------

    beige_source = data.get(
        "beige_book",
        {}
    )

    beige = data.get(
        "beige_analysis",
        {}
    )

    if beige_source.get(
        "available"
    ):

        lines.extend([

            "",

            "PHASE 2C — BEIGE BOOK",

            "---------------------",

            (
                "Latest Beige Book: "
                f"{beige_source.get('date')}"
            ),

            (
                "Beige Book Score: "
                f"{beige.get('score')}/100"
            ),

            (
                "Overall Tone: "
                f"{beige.get('classification')}"
            ),
        ])

        for dimension, value in (
            beige.get(
                "components",
                {}
            ).items()
        ):

            lines.append(
                f"{dimension.title()}: "
                f"{value}/100"
            )

    else:

        lines.extend([

            "",

            "PHASE 2C — BEIGE BOOK",

            "---------------------",

            "Beige Book: UNAVAILABLE",
        ])

    # --------------------------------------------------------
    # REASONS
    # --------------------------------------------------------

    reasons = fi.get(
        "reasons",
        []
    )

    if reasons:

        lines.extend([

            "",

            "REASONS",

            "-------",
        ])

        for reason in reasons:

            lines.append(
                f"- {reason}"
            )

    return "\n".join(
        lines
    )


# ============================================================
# LOCAL TEST
# ============================================================

if __name__ == "__main__":

    result = (
        build_fed_intelligence()
    )

    print(
        fed_summary(
            result
        )
    )
