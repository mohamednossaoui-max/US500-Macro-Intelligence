from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SCRIPTS = ROOT / "scripts"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(
        0,
        str(SCRIPTS),
    )


from verify_publication_integrity import (  # noqa: E402
    run,
    sha256_file,
    verify_manifest,
)


def raw_sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def write_manifest(
    path: Path,
    filename: str,
    data: bytes,
) -> None:

    manifest = {
        "files": {
            filename: {
                "bytes": len(data),
                "sha256":
                    hashlib.sha256(
                        data
                    ).hexdigest(),
            }
        }
    }

    path.write_text(
        json.dumps(manifest),
        encoding="utf-8",
    )


def test_sha256_file(tmp_path: Path):

    path = tmp_path / "sample.csv"

    path.write_bytes(
        b"a,b\n1,2\n"
    )

    expected = hashlib.sha256(
        b"a,b\n1,2\n"
    ).hexdigest()

    assert sha256_file(path) == expected


def test_matching_file(tmp_path: Path):

    public_data = tmp_path / "public_data"
    public_data.mkdir()

    data = b"a,b\n1,2\n"

    data_path = (
        public_data / "sample.csv"
    )

    data_path.write_bytes(data)

    manifest_path = (
        public_data / "manifest.json"
    )

    write_manifest(
        manifest_path,
        "sample.csv",
        data,
    )

    report = verify_manifest(
        manifest_path,
        public_data,
    )

    assert (
        report["summary"]["match"]
        == 1
    )

    assert (
        report["summary"]["mismatch"]
        == 0
    )


def test_changed_file_is_mismatch(
    tmp_path: Path,
):

    public_data = tmp_path / "public_data"
    public_data.mkdir()

    original = b"a,b\n1,2\n"

    data_path = (
        public_data / "sample.csv"
    )

    data_path.write_bytes(original)

    manifest_path = (
        public_data / "manifest.json"
    )

    write_manifest(
        manifest_path,
        "sample.csv",
        original,
    )

    data_path.write_bytes(
        b"a,b\n1,3\n"
    )

    report = verify_manifest(
        manifest_path,
        public_data,
    )

    assert (
        report["summary"]["mismatch"]
        == 1
    )


def test_missing_file(
    tmp_path: Path,
):

    public_data = tmp_path / "public_data"
    public_data.mkdir()

    data = b"example"

    manifest_path = (
        public_data / "manifest.json"
    )

    write_manifest(
        manifest_path,
        "missing.csv",
        data,
    )

    report = verify_manifest(
        manifest_path,
        public_data,
    )

    assert (
        report["summary"]["missing"]
        == 1
    )


def test_verifier_does_not_modify_inputs(
    tmp_path: Path,
):

    public_data = tmp_path / "public_data"
    public_data.mkdir()

    data = b"a,b\n1,2\n"

    data_path = (
        public_data / "sample.csv"
    )

    data_path.write_bytes(data)

    manifest_path = (
        public_data / "manifest.json"
    )

    write_manifest(
        manifest_path,
        "sample.csv",
        data,
    )

    manifest_before = raw_sha256(
        manifest_path
    )

    data_before = raw_sha256(
        data_path
    )

    verify_manifest(
        manifest_path,
        public_data,
    )

    manifest_after = raw_sha256(
        manifest_path
    )

    data_after = raw_sha256(
        data_path
    )

    assert (
        manifest_before
        == manifest_after
    )

    assert (
        data_before
        == data_after
    )


def test_detects_conflicting_manifests(
    tmp_path: Path,
):

    public_data = tmp_path / "public_data"
    public_data.mkdir()

    actual = b"current-data"

    (
        public_data / "sample.csv"
    ).write_bytes(actual)

    old_manifest = {
        "datasets": [
            {
                "file": "sample.csv",
                "bytes": 8,
                "sha256":
                    hashlib.sha256(
                        b"old-data"
                    ).hexdigest(),
            }
        ]
    }

    (
        public_data
        / "public_data_manifest.json"
    ).write_text(
        json.dumps(old_manifest),
        encoding="utf-8",
    )

    new_manifest = {
        "files": {
            "sample.csv": {
                "bytes": len(actual),
                "sha256":
                    hashlib.sha256(
                        actual
                    ).hexdigest(),
            }
        }
    }

    (
        public_data
        / "manifest.json"
    ).write_text(
        json.dumps(new_manifest),
        encoding="utf-8",
    )

    report = run(
        public_data
    )

    conflicts = report[
        "manifest_conflicts"
    ]

    assert len(conflicts) == 1

    assert (
        conflicts[0]["file"]
        == "sample.csv"
    )
