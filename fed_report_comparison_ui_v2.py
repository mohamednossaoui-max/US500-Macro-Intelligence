"""Compact previous/current evidence, without keyword coverage indicators."""
import streamlit as st
from contextlib import nullcontext
from html import escape


def _value(fact):
    if not fact:
        return "Not reported / not comparable"
    value = fact.get("value")
    if isinstance(value, list):
        return "–".join(f"{x:.2f}" for x in value) + "%"
    return str(value)


def render_metrics(pair):
    labels = {"target_range": "Policy target range", "policy_action": "Policy decision", "vote": "Voting"}
    rows = [(k, (pair.get("metrics") or {}).get(k, {})) for k in labels]
    rows = [(k, row) for k, row in rows if row.get("previous") or row.get("current")]
    if rows:
        cols = st.columns(len(rows))
        for col, (key, row) in zip(cols, rows):
            with col:
                st.markdown(f"**{labels[key]}**")
                st.write(f"{_value(row.get('previous'))} → {_value(row.get('current'))}")
                change = row.get("change")
                if isinstance(change, list):
                    if len(change) == 2 and change[0] == change[1]:
                        st.caption(f"Range shift: {change[0]:+g} basis points (both bounds)")
                    else:
                        st.caption(f"Lower bound: {change[0]:+g}; upper bound: {change[1]:+g} basis points")
                elif row.get("status") == "NOT_COMPARABLE":
                    st.caption("A missing value is not an unchanged result.")


def render_comparison(pair, title, namespace, compact=False):
    pair = pair if isinstance(pair, dict) else {}
    st.markdown(f"**{title} — Previous → Current**")
    previous, current = pair.get("previous", {}), pair.get("current", {})
    event_key = "information_cutoff_date" if namespace == "beige_book" else "meeting_date"
    event_label = "Information cutoffs" if namespace == "beige_book" else "Meeting dates"
    st.caption(f"{event_label}: {previous.get(event_key) or 'Unknown'} → {current.get(event_key) or 'Unknown'}. "
               f"Published: {previous.get('publication_date') or 'Not explicitly verified'} → "
               f"{current.get('publication_date') or 'Not explicitly verified'}.")
    cols = st.columns(2)
    for col, side, record in zip(cols, ("Previous", "Current"), (previous, current)):
        with col:
            source = record.get("source") or record.get("url")
            if source:
                st.markdown(f"[{side} official source]({source})")
            st.caption(f"{side} text: {'retrieved' if record.get('available') else 'not retrieved'} · "
                       f"Observed: {record.get('retrieved_at') or 'Unknown'}")
    if not pair.get("available"):
        st.warning("Comparison is not ready: " + str(pair.get("status") or "Rebuild the Fed artifact with the comparison engine."))
        return
    if namespace == "chair_press":
        st.caption("Comparison scope: " + str(current.get("scope") or "Unknown"))
    render_metrics(pair)
    for key, topic in (pair.get("topics") or {}).items():
        pairs = topic.get("pairs") or []
        if not pairs:
            continue
        with nullcontext() if compact else st.expander(topic.get("label", key), expanded=False):
            if compact:
                st.markdown(f"**{topic.get('label', key)}**")
            # Literal text differences first. Retain the complete evidence in JSON
            # and link the official documents, rather than producing large tables.
            ordered = sorted(pairs, key=lambda p: p.get("status") == "SAME_WORDING")
            for item in ordered[:3]:
                columns = st.columns(2)
                for col, side in zip(columns, ("previous", "current")):
                    with col:
                        st.markdown(f"**{side.title()}**")
                        st.write(item.get(side) or "No aligned statement extracted. No inference of unchanged conditions.")
                status = item.get("status", "")
                st.caption({"SAME_WORDING": "Same reported wording", "WORDING_CHANGED": "Reported wording differs",
                            "CURRENT_ONLY_EVIDENCE": "Current-side evidence; no matched previous sentence",
                            "PREVIOUS_ONLY_EVIDENCE": "Previous-side evidence; no matched current sentence"}.get(status, status))
            if len(ordered) > 3:
                st.caption(f"{len(ordered)-3} additional sentence pairs are retained in Complete Fed JSON and the official sources.")
    st.caption("Official text is shown above. Sentence alignment and wording differences are mechanical comparisons; "
               "they do not by themselves establish a hawkish/dovish shift or a policy forecast.")


def coverage(obj):
    reports = obj.get("report_coverage") or {}
    ready = sum(bool(v.get("current_available")) for v in reports.values())
    compared = sum(bool(v.get("comparison_available")) for v in reports.values())
    return f"Report texts: {ready}/4 retrieved · Previous/current comparisons: {compared}/4 ready"


def compact_comparison(pair, title, namespace):
    """Restore the original compact cards; keep full evidence collapsed."""
    metrics = pair.get("metrics") or {}
    row = metrics.get("target_range") or metrics.get("policy_action") or {}
    ready = bool(pair.get("available"))
    previous, current = pair.get("previous") or {}, pair.get("current") or {}
    event_key = "meeting_date"
    badge = "COMPARISON READY" if ready else "SCOPE MISMATCH" if pair.get("status") == "SCOPE_MISMATCH" else "COMPARISON PENDING"
    prev = _value(row.get("previous")) if ready else "Text retrieved" if previous.get("available") else "Unavailable"
    cur = _value(row.get("current")) if ready else "Text retrieved" if current.get("available") else "Unavailable"
    if ready and not row:
        prev, cur = "Text retrieved", "Text retrieved"
    st.markdown(
        f"<div class='comm-shift'><div class='comm-shift-head'><b>{escape(title)}</b>"
        f"<span class='shift-badge flat'>{badge}</span></div>"
        f"<div class='comm-shift-flow'><span><small>PREVIOUS</small>{escape(prev)}</span>"
        f"<strong>→</strong><span><small>CURRENT</small>{escape(cur)}</span></div>"
        f"<div class='comm-shift-date'>Meeting dates: {escape(str(previous.get(event_key) or 'Unknown'))} → "
        f"{escape(str(current.get(event_key) or 'Unknown'))}</div></div>", unsafe_allow_html=True)
    with st.expander(f"{title} — Detailed report comparison", expanded=False):
        render_comparison(pair, title, namespace, compact=True)
