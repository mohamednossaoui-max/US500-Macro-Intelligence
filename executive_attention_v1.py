"""Presentation only. Never infer a Fed vote or recompute Decision State."""
from collections import Counter


def attention_rows(records, fed):
    rows = [dict(row) for row in records]
    # Keep historical/core Fed evidence if present; add only the independent snapshot.
    rows = [r for r in rows if r.get('source') != 'Fed Intelligence (current)']
    obj = fed if isinstance(fed, dict) else {}
    score = obj.get('fed_score') if isinstance(obj.get('fed_score'), dict) else {}
    quality = obj.get('quality') if isinstance(obj.get('quality'), dict) else {}
    available = bool(obj) and obj.get('available') is not False
    classification = score.get('classification') or 'Classification unavailable'
    value = score.get('score')
    detail = classification + (f' · score {value}' if value is not None else '')
    detail += f" · as of {obj.get('as_of_date') or 'unknown'}"
    detail += f" · gate {quality.get('quality_gate') or 'UNKNOWN'}"
    detail += f" · freshness {quality.get('freshness_status') or 'UNKNOWN'}"
    detail += f" · PIT {quality.get('pit_status') or 'UNKNOWN'}"
    detail += ' · Contextual snapshot; excluded from Decision State.'
    rows.append({'source': 'Fed Intelligence (current)', 'category': 'fed',
                 'stance': 'CONTEXTUAL' if available else 'UNAVAILABLE',
                 'reason': detail if available else 'Fed snapshot unavailable; no stance inferred. Excluded from Decision State.'})
    priority = {'CONTRADICTORY': 0, 'MIXED': 1, 'SUPPORTIVE': 2}
    return sorted(rows, key=lambda r: (priority.get(str(r.get('stance', '')).upper(), 3), str(r.get('category', ''))))


def decision_explanation(records, published_state):
    counts = Counter(str(row.get('stance', '')).upper() for row in records)
    support, oppose, mixed = (counts[x] for x in ('SUPPORTIVE', 'CONTRADICTORY', 'MIXED'))
    text = f'Published CORE evidence: {support} supportive · {oppose} contradictory · {mixed} mixed.'
    if published_state == 'SUPPORTIVE' and support and not oppose:
        text += ' V1 labels this SUPPORTIVE because supportive evidence exists and none is contradictory; MIXED does not oppose it. This is directional support, not broad agreement.'
    else:
        text += ' Decision State is read from the published artifact; this panel does not recalculate it.'
    return text + ' Evidence Coverage measures completeness, not agreement or probability. Independent Fed is contextual.'
