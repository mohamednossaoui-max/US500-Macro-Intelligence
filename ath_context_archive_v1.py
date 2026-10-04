"""Immutable programme snapshots, available no earlier than their capture time.

Content fingerprints prove byte consistency, not agency truth or historical
release timing. Never backdate capture to a source's claimed reference date.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import pandas as pd

from scripts.verify_publication_integrity import run as publication_report

VERSION = 'ATH_CONTEXT_ARCHIVE_V1'
REQUIRED = ('unified_state_vector_v1.csv', 'macro_context_v1.csv',
            'decision_engine_research_v1.csv', 'fed_intelligence_output_v1.json')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def utc(value):
    date = pd.to_datetime(value, utc=True, errors='coerce')
    if pd.isna(date):
        raise ValueError('Invalid UTC timestamp.')
    return date


def integrity(root):
    report = publication_report(root)
    if report['errors'] or len(report['manifests']) != 1:
        raise ValueError('Publication Integrity must pass before archiving.')
    summary = report['manifests'][0]['summary']
    if summary['mismatch'] or summary['missing'] or summary['error']:
        raise ValueError('Publication Integrity must pass before archiving.')
    verified = {r['file'] for r in report['manifests'][0]['results'] if r['status'] == 'MATCH'}
    if not set(REQUIRED).issubset(verified):
        raise ValueError('Required context files are not all publication verified.')
    return summary


def load(archive):
    root = Path(archive)
    result = []
    # Snapshots themselves are authoritative; no mutable index can lose a
    # vintage after an interrupted run. Every file is self-checking.
    for path in sorted((root/'snapshots').glob('*.json')):
        record = json.loads(path.read_text())
        checksum = record.pop('record_sha256', None)
        if checksum != hashlib.sha256(canonical(record)).hexdigest():
            raise ValueError('Archive record checksum mismatch: ' + path.name)
        record['record_sha256'] = checksum
        expected = hashlib.sha256(canonical(record['payload'])).hexdigest()
        if record.get('version') != VERSION or record.get('snapshot_id') != expected or path.stem != expected:
            raise ValueError('Invalid or changed archive snapshot: ' + path.name)
        utc(record['recorded_at'])
        if utc(record['available_at']) != utc(record['recorded_at']):
            raise ValueError('Archive availability must equal genuine capture time.')
        for name, raw in record['payload'].get('source_text', {}).items():
            if hashlib.sha256(raw.encode('utf-8')).hexdigest() != record['payload']['source_hashes'].get(name):
                raise ValueError('Archived source text does not match source fingerprint.')
        for row in record['payload']['unified_state_vector_v1.csv']:
            if utc(row['available_at']) > utc(record['available_at']):
                raise ValueError('A source feature claims availability after capture.')
        result.append(record)
    return sorted(result, key=lambda r: (r['available_at'], r['snapshot_id']))


def capture(public_data, archive, recorded_at=None):
    public = Path(public_data).resolve()
    destination = Path(archive).resolve()
    if destination == public or public in destination.parents:
        raise ValueError('Archive must be outside public_data.')
    now = utc(recorded_at) if recorded_at is not None else pd.Timestamp.now(tz='UTC')
    evidence = integrity(public)
    payload = {}
    for name in REQUIRED:
        path = public/name
        if name.endswith('.csv'):
            data = pd.read_csv(path)
            # Preserve float precision and nulls. Default to_json rounding
            # would alter a captured vintage.
            payload[name] = data.astype(object).where(pd.notna(data), None).to_dict(orient='records')
        else:
            payload[name] = json.loads(path.read_text())
    vector = payload['unified_state_vector_v1.csv']
    if not vector or len({r['feature'] for r in vector}) != len(vector):
        raise ValueError('State vector must have unique features.')
    for row in vector:
        for field in ('context_date', 'as_of', 'available_at'):
            if utc(row[field]) > now:
                raise ValueError('Cannot capture future-dated context.')
    for name, field in [('macro_context_v1.csv','context_date'), ('decision_engine_research_v1.csv','as_of_date')]:
        if not payload[name] or any(utc(row[field]) > now for row in payload[name]):
            raise ValueError('Cannot capture empty/future context.')
    if utc(payload['fed_intelligence_output_v1.json']['as_of_date']) > now:
        raise ValueError('Cannot capture a future Fed snapshot.')
    source_hashes = {name:hashlib.sha256((public/name).read_bytes()).hexdigest() for name in REQUIRED}
    payload['source_hashes'] = source_hashes
    payload['source_text'] = {name:(public/name).read_bytes().decode('utf-8') for name in REQUIRED}
    snapshot_id = hashlib.sha256(canonical(payload)).hexdigest()
    previous = load(destination)
    existing = next((r for r in previous if r['snapshot_id'] == snapshot_id), None)
    if existing is not None:
        if utc(existing['recorded_at']) > now:
            raise ValueError('Capture clock precedes existing snapshot.')
        return {'status':'UNCHANGED', 'snapshot_id':snapshot_id, 'snapshot_count':len(previous)}
    # Serial production runs are protected by Master workflow concurrency.
    destination.joinpath('snapshots').mkdir(parents=True, exist_ok=True)
    record = {'version':VERSION, 'snapshot_id':snapshot_id, 'recorded_at':now.isoformat(),
              'available_at':now.isoformat(), 'publication_integrity':evidence,
              'source_verification':'PROGRAMME_CAPTURE_NOT_AGENCY_VINTAGE_CERTIFICATION',
              'payload':payload}
    record['record_sha256'] = hashlib.sha256(canonical(record)).hexdigest()
    raw = canonical(record)
    # Atomic creation; never overwrite an existing vintage. A failed write
    # leaves no half-written JSON for the archive reader.
    temporary = destination/'snapshots'/f'.{snapshot_id}.{os.getpid()}.tmp'
    temporary.write_bytes(raw)
    try:
        os.link(temporary, destination/'snapshots'/f'{snapshot_id}.json')
    finally:
        temporary.unlink(missing_ok=True)
    return {'status':'CAPTURED', 'snapshot_id':snapshot_id, 'snapshot_count':len(previous)+1}


def before(archive, as_of, max_age_days=7):
    cutoff = utc(as_of)
    eligible = [r for r in load(archive) if utc(r['available_at']) < cutoff]
    if not eligible:
        return None
    latest = eligible[-1]
    if cutoff - utc(latest['available_at']) > pd.Timedelta(days=max_age_days):
        return None
    return latest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--public-data',type=Path,default=Path('public_data'))
    parser.add_argument('--archive',type=Path,default=Path('research_history/ath_context_v1'))
    args=parser.parse_args()
    print(json.dumps(capture(args.public_data,args.archive),indent=2))


if __name__ == '__main__':
    main()
