"""Isolate generated root inputs; install only a verified public directory."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.verify_publication_integrity import run as verify


def prepare(root, destination):
    root, destination = Path(root).resolve(), Path(destination).resolve()
    if destination == root or root in destination.parents or destination in root.parents:
        raise ValueError('Build workspace must be separate from the checkout.')
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Build workspace must be empty.')
    shutil.copytree(root, destination, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache',
                                                 'master_runs', 'master_artifacts',
                                                 'decision_engine_output'))
    return destination


def install(root, candidate):
    root, candidate = Path(root).resolve(), Path(candidate).resolve()
    if candidate == root or root in candidate.parents or candidate in root.parents:
        raise ValueError('Candidate must be outside the checkout.')
    report = verify(candidate)
    if (report['errors'] or len(report['manifests']) != 1
            or any(report['manifests'][0]['summary'][k] for k in ('mismatch', 'missing', 'error'))):
        raise ValueError('Publication Integrity failed; checkout was not updated.')
    public = root/'public_data'
    if not public.is_dir() or public.is_symlink():
        raise ValueError('Expected an existing public_data directory.')
    # Rebuilds may update datasets, but must preserve pre-existing publications.
    missing = [p.name for p in public.iterdir() if p.is_file() and not (candidate/p.name).is_file()]
    if missing:
        raise ValueError('Candidate would remove existing publications: '+', '.join(sorted(missing)))
    with tempfile.TemporaryDirectory(prefix='.integrated-install-', dir=root) as folder:
        transaction = Path(folder)
        staged, backup = transaction/'validated', transaction/'previous'
        shutil.copytree(candidate, staged)
        # Verify the actual bytes to be installed, after copying.
        copied = verify(staged)
        if copied != report:
            raise ValueError('Candidate changed while copying; checkout was not updated.')
        public.replace(backup)
        try:
            staged.replace(public)
        except BaseException:
            backup.replace(public)
            raise
    return report['manifests'][0]['summary']


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='mode', required=True)
    prep = sub.add_parser('prepare')
    prep.add_argument('--root', type=Path, required=True)
    prep.add_argument('--destination', type=Path, required=True)
    merge = sub.add_parser('install')
    merge.add_argument('--root', type=Path, required=True)
    merge.add_argument('--candidate', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'prepare':
        print(prepare(args.root, args.destination))
    else:
        print(install(args.root, args.candidate))


if __name__ == '__main__':
    main()
