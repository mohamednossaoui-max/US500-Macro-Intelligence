"""Preserve document-specific publication/observation bounds across Fed layers."""
import json
from .common import row


def build(p):
    x = json.loads((p / 'fed_intelligence_output_v1.json').read_text(encoding='utf-8'))
    asof = x.get('as_of_date', '')
    quality = x.get('quality') or {}
    source_pit = quality.get('pit_status', 'UNKNOWN')
    if source_pit == 'DATE_CHECKED': source_pit = 'PIT_LIMITED'
    dates = x.get('evidence_dates') or {}
    out = []
    specs = [('statement', 'FOMC Statement', 'EVENT_DRIVEN'),
             ('chair_press', 'Press Conference', 'EVENT_DRIVEN'),
             ('minutes', 'FOMC Minutes', 'EVENT_DRIVEN'),
             ('sep', 'Summary of Economic Projections', 'QUARTERLY'),
             ('beige_book', 'Beige Book', 'EVENT_DRIVEN')]
    for key, label, frequency in specs:
        obj = x.get('sep_current' if key == 'sep' else key) or {}
        meta = dates.get(key) or {}
        available = bool(obj.get('available'))
        meeting = meta.get('meeting_date') or (x.get('latest_sep_date') if key == 'sep' else x.get('latest_fomc')) or ''
        published = meta.get('publication_date') or ''
        if key == 'minutes': published = published or x.get('minutes_publication_date') or ''
        if key == 'beige_book':
            published = published or obj.get('publication_date') or ''
            meeting = obj.get('issue_date') or published
        # Meeting date is never a publication-date fallback. Observation only
        # establishes availability from retrieval onward, never historical PIT.
        observed = meta.get('retrieved_at') or x.get('generated_at') or ''
        bound = published or observed
        pit = source_pit if source_pit in {'PIT_SAFE','PIT_LIMITED','NOT_PIT_SAFE','OBSERVATION_CHECKED'} else 'UNKNOWN'
        if not published: pit = 'OBSERVATION_CHECKED' if observed else 'UNKNOWN'
        if not available: pit = 'UNKNOWN'; bound = ''
        limitations = ['PUBLICATION_DATE_ONLY;INTRADAY_NOT_CERTIFIED' if published else 'PUBLICATION_UNKNOWN;RETRIEVAL_BOUND_ONLY']
        if key == 'beige_book': limitations.append('CONTEXTUAL_ONLY;QUALITY_GATE='+str(quality.get('quality_gate','UNKNOWN')))
        if key == 'sep': limitations.append('DIRECTIONAL_COMPARISON_NOT_POLICY_PROBABILITY')
        if not available: limitations.append('NOT_YET_PUBLISHED_OR_UNAVAILABLE')
        state = (x.get('sep_shift') or {}).get('classification','') if key == 'sep' else ((x.get('beige_analysis') or {}).get('tone','') if key == 'beige_book' else obj.get('tone',''))
        out.append(row('FED','FED',label,state=state, observation_date=meeting,
                       release_date=published if available else '',available_at=bound,
                       as_of_date=asof,source_name='Federal Reserve',source_artifact='fed_intelligence_output_v1.json',
                       pit_status=pit,availability_status='AVAILABLE' if available else 'UNAVAILABLE',
                       expected_frequency=frequency,limitations=';'.join(limitations)))
    return out
