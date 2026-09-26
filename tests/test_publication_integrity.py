import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from verify_publication_integrity import (  # noqa: E402
    extract_entries,
    run,
    sha256_file,
    verify_manifest,
)


def write_manifest(path: Path, filename: str, data: bytes) -> None:
    path.write_text(
        json.dumps(
            {
                "files": {
                    filename: {
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                }
            }
        ),
        encoding="utf-8",
    )


def test_sha256_file(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"abc")
    assert sha256_file(path) == hashlib.sha256(b"abc").hexdigest()


def test_extract_entries_requires_files_mapping():
    try:
        extract_entries({"datasets": []})
    except ValueError as exc:
        assert "files" in str(exc)
    else:
        raise AssertionError("legacy manifest format must not be accepted")


def test_match(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    (root / "x").write_bytes(b"a")
    write_manifest(root / "manifest.json", "x", b"a")
    assert verify_manifest(root / "manifest.json", root)["summary"]["match"] == 1


def test_mismatch(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    (root / "x").write_bytes(b"b")
    write_manifest(root / "manifest.json", "x", b"a")
    assert verify_manifest(root / "manifest.json", root)["summary"]["mismatch"] == 1


def test_missing_published_file(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    write_manifest(root / "manifest.json", "x", b"a")
    assert verify_manifest(root / "manifest.json", root)["summary"]["missing"] == 1


def test_verifier_is_read_only(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    data_file = root / "x"
    data_file.write_bytes(b"a")
    manifest = root / "manifest.json"
    write_manifest(manifest, "x", b"a")
    before = (manifest.read_bytes(), data_file.read_bytes())
    verify_manifest(manifest, root)
    assert before == (manifest.read_bytes(), data_file.read_bytes())


def test_run_uses_only_canonical_manifest(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    (root / "x").write_bytes(b"a")
    write_manifest(root / "manifest.json", "x", b"a")
    report = run(root)
    assert not report["errors"]
    assert len(report["manifests"]) == 1
    assert report["manifests"][0]["summary"]["manifest"] == "manifest.json"


def test_run_fails_when_legacy_manifest_exists(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    (root / "x").write_bytes(b"a")
    write_manifest(root / "manifest.json", "x", b"a")
    (root / "public_data_manifest.json").write_text("{}", encoding="utf-8")
    report = run(root)
    assert any("Legacy manifest must be retired" in error for error in report["errors"])


def test_run_fails_when_canonical_manifest_missing(tmp_path):
    root = tmp_path / "public_data"
    root.mkdir()
    report = run(root)
    assert any("Canonical manifest is missing" in error for error in report["errors"])
