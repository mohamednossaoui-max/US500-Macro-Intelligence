"""Read-only presentation of published Fed evidence. No fetching or score changes."""
from __future__ import annotations

from datetime import datetime
from html import escape
import re
from urllib.parse import urlparse


def _dict(value):
    return value if isinstance(value, dict) else {}


def _fact(record, key, metric):
    if not record.get("available"):
        return {}
    candidate = _dict(_dict(record.get("facts")).get(key)) or _dict(metric)
    return candidate if candidate.get("value") is not None else {}


def _dissent(record, vote):
    if not record.get("available") or record.get("scope") != "OFFICIAL_STATEMENT":
        return {}
    direct = _dict(_dict(record.get("facts")).get("dissent_preference"))
    if direct.get("value") is not None and direct.get("evidence"):
        return direct
    evidence = _dict(_dict(record.get("topics")).get("policy")).get("evidence") or []
    if not isinstance(evidence, list):
        return {}
    matches = []
    mapping = {"raise": "RAISE", "increase": "RAISE", "reduce": "CUT", "lower": "CUT", "maintain": "HOLD", "keep": "HOLD"}
    for sentence in evidence:
        if not isinstance(sentence, str):
            continue
        found = re.findall(r"\bpreferred to (raise|increase|reduce|lower|maintain|keep)\b", sentence, re.I)
        if found:
            matches.append((set(mapping[word.lower()] for word in found), sentence))
    if matches:
        values = set().union(*(values for values, _ in matches))
        return {"value": next(iter(values)) if len(values) == 1 else "MULTIPLE PREFERENCES",
                "evidence": "\n".join(dict.fromkeys(text for _, text in matches)),
                "basis": "EXPLICIT_PREFERENCE_IN_PUBLISHED_STATEMENT_EVIDENCE"}
    value = vote.get("value")
    explicit_zero = (isinstance(value, str) and (bool(re.fullmatch(r"\d+\s*[–-]\s*0", value)) or value == "UNANIMOUS")) or (
        isinstance(value, list) and len(value) == 2 and value[1] == 0)
    if explicit_zero and vote.get("evidence"):
        return {"value": "NO DISSENT", "evidence": vote["evidence"], "basis": "EXPLICIT_VOTE"}
    return {}


def _timestamp_known(value):
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def _source(value):
    if not isinstance(value, str):
        return None
    try:
        parsed = urlparse(value)
        if parsed.scheme == "https" and parsed.hostname in {"federalreserve.gov", "www.federalreserve.gov"} and not parsed.username and not parsed.password:
            return value
    except ValueError:
        pass
    return None


def panel_model(pair, namespace):
    """Derive display data only; preserve published scores, PIT flags and inputs."""
    pair = _dict(pair)
    records = {side: _dict(pair.get(side)) for side in ("previous", "current")}
    expected = {"statement": {"OFFICIAL_STATEMENT"}, "chair_press": {"OPENING_STATEMENT", "FULL_TRANSCRIPT_CHAIR_REMARKS"}}.get(namespace, set())
    scopes = [records[side].get("scope") for side in records]
    comparable = bool(pair.get("available") and all(records[s].get("available") for s in records)
                      and scopes[0] == scopes[1] and scopes[0] in expected)
    metrics = _dict(pair.get("metrics"))
    rows = []
    for key, label in (("policy_action", "Policy decision"), ("target_range", "Target range"), ("vote", "Vote")):
        row = {"key": key, "label": label}
        for side, record in records.items():
            row[side] = _fact(record, key, _dict(metrics.get(key)).get(side))
        row["status"] = ("NOT COMPARABLE" if not comparable or not row["previous"] or not row["current"] else
                         "UNCHANGED" if row["previous"]["value"] == row["current"]["value"] else "CHANGED")
        rows.append(row)
    if namespace == "statement":
        vote = rows[-1]
        row = {"key": "dissent_preference", "label": "Dissent preference"}
        for side, record in records.items():
            row[side] = _dissent(record, vote[side])
        row["status"] = ("NOT COMPARABLE" if not comparable or not row["previous"] or not row["current"] else
                         "UNCHANGED" if row["previous"]["value"] == row["current"]["value"] else "CHANGED")
        rows.append(row)
    highlights = []
    if comparable:
        for key in ("growth", "inflation", "credit", "policy"):
            topic = _dict(_dict(pair.get("topics")).get(key))
            pairs = [p for p in topic.get("pairs", []) if isinstance(p, dict)]
            changed = [p for p in pairs if p.get("status") == "WORDING_CHANGED" and p.get("previous") and p.get("current")]
            if changed:
                highlights.append({"label": topic.get("label", key), **changed[0]})
    provenance = {}
    for side, record in records.items():
        version = record.get("version_status")
        provenance[side] = {
            "source": _source(record.get("source") or record.get("url")),
            "meeting_date": record.get("meeting_date"),
            "publication_date": record.get("publication_date"),
            "retrieved_at": record.get("retrieved_at"),
            "scope": record.get("scope"),
            "version_status": version if version in {"PRELIMINARY", "FINAL"} else "UNKNOWN",
            "content_sha256": record.get("content_sha256"),
            "publication_time_status": "RECORDED" if _timestamp_known(record.get("published_at")) else "NOT VERIFIED",
        }
    return {"comparable": comparable, "rows": rows, "highlights": highlights[:2], "provenance": provenance}


def _value(fact, key):
    if not fact:
        return "Not reported"
    value = fact.get("value")
    if isinstance(value, list):
        if key == "target_range" and len(value) == 2 and all(isinstance(x, (float, int)) for x in value):
            return f"{value[0]:.2f}–{value[1]:.2f}%"
        return "–".join(str(x) for x in value)
    return str(value)


def render_evidence_panel(pair, namespace):
    import streamlit as st

    model = panel_model(pair, namespace)
    title = "Fed Evidence — What changed?" if namespace == "statement" else "Press Conference — Evidence & timing"
    st.markdown("**" + title + "**")
    if namespace == "statement":
        cards = []
        for row in model["rows"]:
            status = row["status"]
            color = "#ffbd69" if status == "CHANGED" else "#95adbe"
            cards.append(
                f"<div style='border:1px solid #30485f;border-radius:10px;padding:12px;background:#12253a'>"
                f"<div style='font-size:.78rem;color:#b4c5d4'>{escape(row['label'])}</div>"
                f"<div style='font-weight:750;margin:8px 0;overflow-wrap:anywhere'>{escape(_value(row['previous'],row['key']))} → {escape(_value(row['current'],row['key']))}</div>"
                f"<div style='font-size:.7rem;color:{color}'>{status}</div></div>")
        st.markdown("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(min(210px,100%),1fr));gap:10px;margin:10px 0'>" + "".join(cards) + "</div>", unsafe_allow_html=True)
        st.caption("Dissent preference is separate from the adopted decision. Not reported does not mean neutral or unchanged.")
    if not model["comparable"]:
        st.info("Evidence comparison pending — both documents must be retrieved with the same verified scope.")
    elif not model["highlights"]:
        st.caption("No aligned wording changes were extracted for the highlighted topics. See the detailed comparison; this is not a neutral-policy verdict.")
    for item in model["highlights"]:
        st.markdown("**" + str(item["label"]) + " · wording changed**")
        for col, side in zip(st.columns(2), ("previous", "current")):
            with col:
                st.caption(side.title())
                st.write(item[side])
    st.caption("Source text differences only — no new Fed score, Decision State or trading signal.")
    with st.expander(title + " — sources and timing", expanded=False):
        for col, side in zip(st.columns(2), ("previous", "current")):
            with col:
                meta = model["provenance"][side]
                st.markdown("**" + side.title() + "**")
                if meta["source"]:
                    st.link_button("Official document", meta["source"])
                st.caption(f"Meeting: {meta['meeting_date'] or 'Unknown'} · Published date: {meta['publication_date'] or 'Unknown'}")
                st.caption(f"Observed version: {meta['retrieved_at'] or 'Unknown'}")
                st.caption(f"Scope: {meta['scope'] or 'Unknown'} · Version: {meta['version_status']}")
                st.caption("Publication time: " + meta["publication_time_status"])
                if meta["content_sha256"]:
                    st.code(str(meta["content_sha256"]), language=None)
        for row in model["rows"]:
            snippets = [(side, row[side].get("evidence")) for side in ("previous", "current") if row[side].get("evidence")]
            if snippets:
                st.markdown("**" + row["label"] + " — supporting text**")
                for side, text in snippets:
                    st.write(side.title() + ": " + str(text))
        st.caption("A meeting or publication date alone does not establish intraday availability. Observed version is its retrieval time, not proof it was available earlier. Preliminary/final status stays unknown unless recorded by the source collector.")
