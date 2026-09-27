import json
from .common import row


def build(p):
    x = json.load(open(p / 'fed_intelligence_output_v1.json', encoding='utf-8'))
    asof = x.get('as_of_date', '')
    quality = x.get('quality') or {}
    gate = quality.get('quality_gate', 'UNKNOWN')
    pit = quality.get('pit_status', 'UNKNOWN')
    out = []
    for key, label in [('statement', 'FOMC Statement'), ('chair_press', 'Press Conference'), ('minutes', 'FOMC Minutes')]:
        v = x.get(key) or {}
        available = bool(v.get('available'))
        out.append(row(
            'FED', 'FED', label, state=v.get('tone', ''), observation_date=x.get('latest_fomc', ''),
            release_date=x.get('latest_fomc', '') if available else '', available_at=x.get('latest_fomc', '') if available else '',
            as_of_date=asof, source_name='Federal Reserve', source_artifact='fed_intelligence_output_v1.json',
            pit_status=pit if available else 'UNKNOWN', availability_status='AVAILABLE' if available else 'UNAVAILABLE',
            expected_frequency='EVENT_DRIVEN', limitations='' if available else 'NOT_YET_PUBLISHED_OR_UNAVAILABLE'))
    sep = x.get('sep_current') or {}
    out.append(row(
        'FED', 'FED', 'Summary of Economic Projections', state=(x.get('sep_shift') or {}).get('classification', ''),
        observation_date=x.get('latest_sep_date', ''), release_date=x.get('latest_sep_date', '') if sep.get('available') else '',
        available_at=x.get('latest_sep_date', '') if sep.get('available') else '', as_of_date=asof,
        source_name='Federal Reserve', source_artifact='fed_intelligence_output_v1.json',
        pit_status=pit if sep.get('available') else 'UNKNOWN', availability_status='AVAILABLE' if sep.get('available') else 'UNAVAILABLE',
        expected_frequency='QUARTERLY', limitations='DIRECTIONAL_COMPARISON_NOT_POLICY_PROBABILITY'))
    beige = x.get('beige_book') or {}
    out.append(row(
        'FED', 'FED', 'Beige Book', state=(x.get('beige_analysis') or {}).get('tone', ''),
        observation_date=beige.get('issue_date', ''), release_date=beige.get('publication_date', '') if beige.get('available') else '',
        available_at=beige.get('publication_date', '') if beige.get('available') else '', as_of_date=asof,
        source_name='Federal Reserve', source_artifact='fed_intelligence_output_v1.json',
        pit_status=pit if beige.get('available') else 'UNKNOWN', availability_status='AVAILABLE' if beige.get('available') else 'UNAVAILABLE',
        expected_frequency='EVENT_DRIVEN', limitations=f'CONTEXTUAL_ONLY;QUALITY_GATE={gate}'))
    return out
