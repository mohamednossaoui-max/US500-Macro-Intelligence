"""Explicit meeting and verified publication labels for Fed comparisons."""
from datetime import date
from html import escape


def _date(value):
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError:
        return 'Unavailable'


def communication_dates(key, item):
    previous = _date(item.get('previous_date'))
    current = _date(item.get('current_date'))
    if key != 'minutes':
        return escape(f'{previous} → {current}')
    released = _date(item.get('current_publication_date'))
    prior_release = _date(item.get('previous_publication_date'))
    return (escape(f'Meeting dates: {previous} → {current}') + '<br>' +
            escape(f'Current release: {released} · Previous release: {prior_release}'))
