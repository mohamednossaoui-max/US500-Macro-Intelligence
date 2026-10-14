"""Source-grounded Beige Book evidence; no inferred dates or policy probabilities."""
from __future__ import annotations

import hashlib
import re
from datetime import date, datetime, timezone
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

INDEX = "https://www.federalreserve.gov/monetarypolicy/publications/beige-book-default.htm"
SECTIONS = {"Overall Economic Activity": "activity", "Labor Markets": "labor", "Prices": "prices"}
NUMBERS = {word: i for i, word in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve".split())}
N = r"(?:\d{1,2}|zero|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)"


def parse_date(value):
    try:
        return date.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None


def official(url):
    return urlparse(str(url or "")).hostname == "www.federalreserve.gov"


def _english_date(value):
    try:
        return datetime.strptime(value, "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def release_catalog(html):
    """Only explicit release labels beside links; URL month is an identifier."""
    soup = BeautifulSoup(html, "html.parser")
    records = {}
    for a in soup.find_all("a", href=True):
        href = a["href"]
        match = re.search(r"beigebook(20\d{4})(?:-summary)?\.(?:htm|pdf)", href, re.I)
        if not match:
            continue
        issue = match[1]
        heading = a.find_previous(["h2", "h3", "h4", "th"])
        year_match = re.search(r"\b(20\d{2})\b", heading.get_text() if heading else "")
        # No fallback to the URL year: December issues can be released in January.
        if not year_match:
            continue
        node = a.parent
        published = None
        for _ in range(3):
            if node is None:
                break
            issues = {m[1] for x in node.find_all("a", href=True)
                      if (m := re.search(r"beigebook(20\d{4})", x["href"]))}
            if issues != {issue}:
                break
            label = re.search(r"([A-Za-z]+\s+\d{1,2})\s*:", node.get_text(" ", strip=True))
            if label:
                published = _english_date(f"{label[1]}, {year_match[1]}")
                break
            node = node.parent
        if not published:
            continue
        url = urljoin(INDEX, href)
        if not official(url):
            continue
        records[issue] = {"issue_month": f"{issue[:4]}-{issue[4:]}",
                          "issue_date": None, "publication_date": published,
                          "publication_date_source": INDEX,
                          "url": f"https://www.federalreserve.gov/monetarypolicy/beigebook{issue}-summary.htm"}
    return sorted(records.values(), key=lambda x: x["publication_date"], reverse=True)


def national_sections(html):
    """Stop before district highlights. Never score navigation/footer text."""
    soup = BeautifulSoup(html, "html.parser")
    heading = next((h for h in soup.find_all(["h2", "h3"])
                    if h.get_text(" ", strip=True) == "National Summary"), None)
    sections, current = {}, None
    if heading:
        for node in heading.find_all_next(["h2", "h3", "h4", "p"]):
            if node.name in ("h2", "h3"):
                break
            if node.name == "h4":
                current = SECTIONS.get(node.get_text(" ", strip=True))
                if not current:
                    break
            elif current:
                if node.get("id") == "f2" or node.get_text(strip=True).startswith("Note: This report"):
                    break
                sections.setdefault(current, []).append(node.get_text(" ", strip=True))
    cutoff = re.search(r"information collected on or before\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})",
                       soup.get_text(" ", strip=True), re.I)
    return {k: " ".join(v) for k, v in sections.items()}, _english_date(cutoff[1]) if cutoff else None


def _number(value):
    return int(value) if value.isdigit() else NUMBERS[value.lower()]


def _match_count(pattern, text):
    matches = re.findall(pattern, text, re.I)
    values = {_number(m) for m in matches}
    return values.pop() if len(values) == 1 else None


def report_facts(sections):
    """Conservative supported forms; unknown wording is null, never neutral/zero."""
    activity, labor, prices = (sections.get(k, "") for k in ("activity", "labor", "prices"))
    growth = _match_count(rf"\b({N}) of the twelve.*?Districts reported growth", activity)
    if growth is None:
        counts = [_match_count(pattern, activity) for pattern in (
            rf"\b({N}) of the twelve.*?Districts reported moderate growth",
            rf"\b({N}) Districts reported modest growth",
            rf"while ({N}) reported slight growth")]
        growth = sum(counts) if all(x is not None for x in counts) else None
    robust = _match_count(rf"\b({N}) Districts characterized overall price growth as robust", prices)
    if robust is None:
        robust = _match_count(rf"\band ({N}) robust increases", prices)
    faster = _match_count(rf"\b({N}) Districts reported that the pace of price increases picked up", prices)
    if faster is None:
        faster = _match_count(rf"pace of price increases.*?increased in ({N})\b", prices)
    modest = _match_count(rf"\b({N}) Districts (?:described modest increases|showing modest gains)", labor)
    slight = _match_count(rf"\b({N}) (?:reported slight increases|reporting slight gains)", labor)
    flat = _match_count(rf"\b({N}) (?:reported no significant change|Districts experiencing no change)", labor)
    def sentences(text, terms):
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text)
                if any(t in s.lower() for t in terms)]
    return {"districts_with_growth": growth, "districts_with_robust_prices": robust,
            "districts_with_accelerating_prices": faster,
            "employment_modest": modest, "employment_slight": slight, "employment_unchanged": flat,
            "consumer_spending_evidence": sentences(activity, ["consumer spending"]),
            "credit_evidence": sentences(activity, ["financial conditions", "loan", "credit", "lending"]),
            "price_evidence": sentences(prices, ["oil", "diesel", "fuel", "margin", "expect"])}


def load_reports(get, as_of):
    """Use the latest eligible release, even if its content fails to download."""
    index = get(INDEX)
    catalog = release_catalog(index.text) if index is not None else []
    eligible = [x for x in catalog if parse_date(x["publication_date"]) <= as_of]
    def load(record):
        result = {"issue_date": None, "issue_month": None, "publication_date": None,
                  "url": None, "title": None, **(record or {}), "available": False, "text": "", "sections": {},
                  "information_cutoff_date": None, "retrieved_at": None,
                  "catalog_verified": bool(catalog), "latest_publication_date": eligible[0]["publication_date"] if eligible else None}
        if not record:
            return result
        response = get(record["url"])
        if response is None:
            return result
        sections, cutoff = national_sections(response.text)
        # Failed extraction is missing evidence, never whole-page fallback.
        text = " ".join(sections.values())
        temporal_ok = not cutoff or parse_date(cutoff) <= parse_date(record["publication_date"])
        result.update(available=all(sections.get(k) for k in SECTIONS.values()) and temporal_ok,
                      sections=sections, text=text if temporal_ok else "",
                      information_cutoff_date=cutoff,
                      retrieved_at=datetime.now(timezone.utc).isoformat(),
                      content_sha256=hashlib.sha256(text.encode()).hexdigest(),
                      title=f"Beige Book — {record['issue_month']}")
        if result["available"]:
            result["facts"] = report_facts(sections)
        return result
    return load(eligible[0] if eligible else None), load(eligible[1] if len(eligible) > 1 else None)


def metadata(report):
    return {k: v for k, v in report.items() if k not in ("text", "sections", "facts")}


def comparison(current, previous, current_analysis, previous_analysis):
    out = {"available": bool(current.get("available") and previous.get("available")),
           "current": metadata(current), "previous": metadata(previous),
           "current_facts": current.get("facts", {}), "previous_facts": previous.get("facts", {}),
           "changes": {}, "dimension_changes": {},
           "interpretation": "Comparison of reported evidence; no inference of a policy decision."}
    if not out["available"]:
        out["reason"] = "CURRENT_OR_PREVIOUS_REPORT_UNAVAILABLE"
        return out
    for k, value in current.get("facts", {}).items():
        old = previous.get("facts", {}).get(k)
        if isinstance(value, int) and isinstance(old, int):
            out["changes"][k] = {"previous": old, "current": value, "change": value - old}
    for k, value in current_analysis.get("dimensions", {}).items():
        old = previous_analysis.get("dimensions", {}).get(k, {}).get("score_100")
        new = value.get("score_100")
        if isinstance(old, (int, float)) and isinstance(new, (int, float)):
            out["dimension_changes"][k] = {"previous": old, "current": new, "change": round(new-old, 1)}
    return out


def snapshot_quality(data, as_of):
    """Date-level checks, not a guarantee about archived intraday vintages."""
    checks = {}
    for key, record in data.get("evidence_dates", {}).items():
        pub = parse_date(record.get("publication_date"))
        event = parse_date(record.get("information_cutoff_date") if key == "beige_book" else record.get("meeting_date"))
        expected = parse_date(record.get("latest_publication_date"))
        if not record.get("available"):
            status = "MISSING"
        elif pub is None or event is None or not official(record.get("publication_date_source")):
            status = "UNKNOWN"
        elif pub > as_of or (event and event > pub):
            status = "INVALID_DATES"
        elif expected is None or not record.get("catalog_verified"):
            status = "UNKNOWN"
        elif pub < expected:
            status = "STALE"
        else:
            status = "CURRENT"
        checks[key] = status
    required = {"statement", "minutes", "chair_press", "sep", "beige_book"}
    complete = set(checks) == required
    states = list(checks.values())
    snapshot_date = parse_date(data.get("as_of_date"))
    pit = "INVALID_DATES" if "INVALID_DATES" in states or (snapshot_date and snapshot_date > as_of) else (
        "DATE_CHECKED" if complete and all(x in ("CURRENT", "STALE") for x in states) else "UNKNOWN")
    freshness = "STALE" if "STALE" in states or (parse_date(data.get("as_of_date")) and parse_date(data["as_of_date"]) < as_of) else (
        "CURRENT" if complete and all(x == "CURRENT" for x in states) and parse_date(data.get("as_of_date")) == as_of else "UNVERIFIED")
    return {"pit_status": pit, "freshness_status": freshness, "document_checks": checks,
            "pit_scope": "Publication-date ordering only; no intraday or archived-vintage guarantee."}
