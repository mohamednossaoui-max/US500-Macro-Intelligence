"""Evidence comparisons, not keyword scores or inferred economic probabilities."""
from __future__ import annotations

import hashlib
import io
import re
from datetime import datetime, timezone
from difflib import SequenceMatcher
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from pypdf import PdfReader

from fed_beige_evidence_v1 import official, parse_date

TOPICS = {
    "inflation": ("Inflation and prices", r"\b(?:inflation|PCE|CPI|price pressures|price growth|price increases|prices increased|prices rose)\b"),
    "labor": ("Labor market", r"\b(?:employment|unemployment|jobless|job gains|labor market|wages)\b"),
    "growth": ("Growth and demand", r"\b(?:economic activity|economic growth|GDP|consumer spending|investment|productivity)\b"),
    "risks": ("Balance of risks", r"\b(?:risks?|uncertainty|uncertain|upside|downside)\b"),
    "policy": ("Policy and guidance", r"\b(?:target range|policy rate|monetary policy|forward guidance|accommodation)\b"),
    "liquidity": ("Balance sheet and liquidity", r"\b(?:balance sheet|reserves|repo|securities holdings|redemptions|runoff)\b"),
    "credit": ("Credit and financial conditions", r"\b(?:credit|lending|loan|financial conditions|Treasury|yields)\b"),
}


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def normalize(text):
    return re.sub(r"\s+", " ", text or "").strip()


def chair_remarks(text):
    """Exclude journalist questions from attributed Fed evidence."""
    text = re.sub(r"(?m)^.*?(?:Chairman|Chair) .*?Press Conference\s+FINAL\s*$", "", text)
    text = re.sub(r"(?m)^\s*Page \d+ of \d+\s*$", "", text)
    speakers = list(re.finditer(r"(?m)^\s*([A-Z][A-Z ’'\-]{2,55})\.\s+", text))
    remarks = []
    for i, m in enumerate(speakers):
        if re.match(r"CHAIR(?:MAN)?\s+", m[1]):
            end = speakers[i+1].start() if i+1 < len(speakers) else len(text)
            remarks.append(normalize(text[m.end():end]))
    return " ".join(remarks)


def release_dates(html):
    """Explicit release labels in Related Information, never the page update."""
    soup = BeautifulSoup(html or "", "html.parser")
    out = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        kind = ("minutes" if "fomcminutes" in href else
                "statement" if re.search(r"monetary\d{8}a\.htm", href) else
                "sep" if "fomcprojtabl" in href or "fomcprojtable" in href else
                "chair_press" if "fomcpresconf" in href and ".pdf" in href else None)
        if not kind:
            continue
        node = a.parent
        for _ in range(3):
            if node is None:
                break
            matches = re.findall(r"Released\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", node.get_text(" ", strip=True), re.I)
            if len(set(matches)) > 1:
                break
            if matches:
                try:
                    out[kind] = datetime.strptime(matches[0], "%B %d, %Y").date().isoformat()
                except ValueError:
                    pass
                break
            node = node.parent
    return out


def load_press(url, get, as_of=None):
    """Linked or verified canonical transcript, with meeting/content validation."""
    meeting_match = re.search(r"(20\d{6})", url or "")
    result = {"page_url": url or None, "pdf_url": None, "text": "", "available": False,
              "source_status": "NOT_RETRIEVED", "publication_date": None,
              "publication_date_source": None, "retrieved_at": None,
              "scope": None, "related_release_dates": {}}
    if not official(url):
        result["source_status"] = "NON_OFFICIAL_SOURCE"
        return result
    if not meeting_match:
        return result
    meeting = datetime.strptime(meeting_match[1], "%Y%m%d").date()
    result["meeting_date"] = meeting.isoformat()
    if as_of and meeting > as_of:
        result["source_status"] = "FUTURE_MEETING"
        return result
    page = get(url)
    candidates = []
    if page is not None:
        result["related_release_dates"] = release_dates(page.text)
        published = result["related_release_dates"].get("chair_press")
        if published:
            result.update(publication_date=published, publication_date_source=url)
            if as_of and parse_date(published) > as_of:
                result["source_status"] = "FUTURE_PUBLICATION"
                return result
        soup = BeautifulSoup(page.text, "html.parser")
        for a in soup.find_all("a", href=True):
            candidate = urljoin(url, a["href"])
            if official(candidate) and re.search(r"FOMCpresconf" + meeting_match[1] + r"(?:[a-z_-]*)\.pdf$", candidate, re.I):
                candidates.append(candidate)
    canonical = f"https://www.federalreserve.gov/mediacenter/files/FOMCpresconf{meeting_match[1]}.pdf"
    # Full transcript first; an opening statement is explicitly scoped and never
    # silently substituted for a complete Q&A transcript.
    candidates = list(dict.fromkeys([canonical] + candidates))
    for candidate in candidates:
        response = get(candidate)
        if response is None:
            continue
        if not getattr(response, "content", b"").startswith(b"%PDF-"):
            result["source_status"] = "INVALID_PDF"
            continue
        try:
            reader = PdfReader(io.BytesIO(response.content))
            full = "\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception:
            result["source_status"] = "PDF_EXTRACTION_FAILED"
            continue
        header_date = re.search(r"([A-Za-z]+\s+\d{1,2},\s+\d{4})", full[:1800])
        try:
            header_meeting = datetime.strptime(header_date[1], "%B %d, %Y").date() if header_date else None
        except ValueError:
            header_meeting = None
        if header_meeting != meeting or not re.search(r"(?:Transcript|Opening Statement).*?Press Conference", normalize(full[:1800]), re.I):
            result["source_status"] = "TRANSCRIPT_DATE_OR_TYPE_MISMATCH"
            continue
        remarks = chair_remarks(full)
        if not remarks:
            result["source_status"] = "CHAIR_REMARKS_NOT_EXTRACTED"
            continue
        scope = "OPENING_STATEMENT" if re.search(r"opening", candidate, re.I) or "opening statement" in full[:1800].lower() else "FULL_TRANSCRIPT_CHAIR_REMARKS"
        result.update(available=True, text=remarks, pdf_url=candidate, source_status="VERIFIED_TRANSCRIPT",
                      scope=scope, retrieved_at=datetime.now(timezone.utc).isoformat(),
                      content_sha256=digest(remarks), pdf_sha256=hashlib.sha256(response.content).hexdigest())
        return result
    return result


def report_body(html):
    soup = BeautifulSoup(html or "", "html.parser")
    # These containers hold the release/minutes, excluding site navigation.
    body = soup.select_one("#article") or soup.select_one(".col-xs-12.col-sm-8.col-md-8")
    if body is None:
        return ""
    for tag in body.select("script, style, nav, footer, .shareDL, .social, .panel, .heading"):
        tag.decompose()
    paragraphs = []
    for p in body.find_all("p"):
        text = p.get_text(" ", strip=True)
        if text and not text.startswith(("Last Update", "For media inquiries", "Voting for", "Implementation Note")):
            paragraphs.append(text)
    return "\n".join(paragraphs)


def sentences(text):
    text = normalize(text)
    for abbreviation in ("U.S.", "Mr.", "Ms.", "Dr.", "p.m.", "a.m."):
        text = text.replace(abbreviation, abbreviation.replace(".", "\u2024"))
    return [s.replace("\u2024", ".") for s in re.split(r"(?<=[.!?])\s+(?=[A-Z\"“])", text) if s]


def _numeric_fractions(text):
    values = {"¼": .25, "½": .5, "¾": .75}
    text = re.sub(r"(\d+)?([¼½¾])", lambda m: str(float(m[1] or 0)+values[m[2]]), text)
    return re.sub(r"\b(\d+)[ -](\d)\s*/\s*(\d)\b", lambda m: str(float(m[1])+float(m[2])/float(m[3])), text)


def policy_facts(text):
    facts = {}
    for sentence in sentences(text):
        if not re.search(r"(?:Committee|FOMC) (?:decided|voted)", sentence, re.I):
            continue
        numeric = _numeric_fractions(sentence)
        action = re.search(r"\b(raise|increase|reduce|lower|maintain|keep)\b.{0,100}?target range", numeric, re.I)
        rate_range = re.search(r"target range.{0,180}?\b(\d+(?:\.\d+)?)\s*(?:to|[-–])\s*(\d+(?:\.\d+)?)\s*percent", numeric, re.I)
        if action and rate_range:
            low, high = float(rate_range[1]), float(rate_range[2])
            if not 0 <= low <= high <= 25:
                continue
            facts["policy_action"] = {"value": {"raise":"RAISE", "increase":"RAISE", "reduce":"CUT", "lower":"CUT", "maintain":"HOLD", "keep":"HOLD"}[action[1].lower()], "evidence": sentence}
            facts["target_range"] = {"value": [low, high], "unit": "percent", "evidence": sentence}
            vote = re.search(r"(\d+)\s*(?:[- ]to[- ]|to)\s*(\d+)\s+vote", sentence, re.I)
            if vote:
                facts["vote"] = {"value": f"{vote[1]}–{vote[2]}", "evidence": sentence}
            break
    unanimous = next((s for s in sentences(text) if "unanimous vote" in s.lower()), None)
    if unanimous:
        facts["vote"] = {"value": "UNANIMOUS", "evidence": unanimous}
    explicit_vote = next((s for s in sentences(text) if re.search(r"approved.*?statement.*?by a \d+\s*[–-]\s*\d+ vote", s, re.I)), None)
    if explicit_vote:
        vote = re.search(r"by a (\d+)\s*[–-]\s*(\d+) vote", explicit_vote, re.I)
        facts["vote"] = {"value": f"{vote[1]}–{vote[2]}", "evidence": explicit_vote}
    return facts


def document(text, metadata, scope):
    return {**metadata, "available": bool(text.strip()), "scope": scope,
            "content_sha256": digest(text), "facts": policy_facts(text),
            "topics": {k: {"label": label, "evidence": [s for s in sentences(text) if re.search(pattern, s, re.I)]}
                       for k, (label, pattern) in TOPICS.items()}}


def pair_evidence(previous, current):
    """Align wording within one topic. Labels describe text, not inferred policy."""
    used = set()
    pairs = []
    for now in current:
        remaining = [(i, old) for i, old in enumerate(previous) if i not in used]
        if remaining:
            i, old = max(remaining, key=lambda x: SequenceMatcher(None, x[1].lower(), now.lower()).ratio())
            similarity = SequenceMatcher(None, old.lower(), now.lower()).ratio()
            if similarity >= .28:
                used.add(i)
                pairs.append({"previous": old, "current": now,
                              "status": "SAME_WORDING" if normalize(old).lower() == normalize(now).lower() else "WORDING_CHANGED"})
                continue
        pairs.append({"previous": None, "current": now, "status": "CURRENT_ONLY_EVIDENCE"})
    pairs.extend({"previous": old, "current": None, "status": "PREVIOUS_ONLY_EVIDENCE"}
                 for i, old in enumerate(previous) if i not in used)
    return pairs


def compare(previous, current):
    out = {"available": bool(previous.get("available") and current.get("available")),
           "previous": previous, "current": current, "metrics": {}, "topics": {},
           "method": "Official numeric facts and aligned source sentences. Wording changes are not a semantic policy verdict. No keyword coverage score."}
    if not out["available"]:
        out["status"] = "CURRENT_OR_PREVIOUS_NOT_RETRIEVED"
        return out
    if previous.get("scope") != current.get("scope"):
        out.update(available=False, status="SCOPE_MISMATCH")
        return out
    out["status"] = "COMPARISON_READY"
    for key in ("policy_action", "target_range", "vote"):
        old, new = previous["facts"].get(key), current["facts"].get(key)
        row = {"previous": old, "current": new, "change": None}
        if old and new and key == "target_range":
            row["change"] = [round((n-o)*100, 2) for o, n in zip(old["value"], new["value"])]
            row["change_unit"] = "basis points"
        row["status"] = ("NOT_COMPARABLE" if not old or not new else "UNCHANGED" if old["value"] == new["value"] else "CHANGED")
        out["metrics"][key] = row
    for key, (label, _) in TOPICS.items():
        old, new = previous["topics"][key]["evidence"], current["topics"][key]["evidence"]
        out["topics"][key] = {"label": label, "pairs": pair_evidence(old, new),
                              "status": "EVIDENCE_AVAILABLE" if old and new else "PARTIAL_TOPIC_EVIDENCE"}
    return out
