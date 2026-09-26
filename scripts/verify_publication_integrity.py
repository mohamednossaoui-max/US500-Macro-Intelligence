from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

CANONICAL_MANIFEST = "manifest.json"
LEGACY_MANIFEST = "public_data_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def extract_entries(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, dict):
        raise ValueError("Canonical manifest must contain a 'files' object")

    entries: dict[str, dict[str, Any]] = {}
    for filename, metadata in files.items():
        if not isinstance(filename, str) or not isinstance(metadata, dict):
            raise ValueError("Invalid file entry in canonical manifest")
        entries[filename] = {
            "bytes": metadata.get("bytes"),
            "sha256": metadata.get("sha256"),
        }
    return entries


def verify_manifest(manifest_path: Path, root: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []

    for filename, metadata in sorted(
        extract_entries(load_json(manifest_path)).items()
    ):
        path = root / filename
        row = {
            "file": filename,
            "expected_sha256": metadata.get("sha256"),
            "actual_sha256": None,
            "expected_bytes": metadata.get("bytes"),
            "actual_bytes": None,
            "status": "MISSING",
        }

        if path.is_file():
            row["actual_sha256"] = sha256_file(path)
            row["actual_bytes"] = path.stat().st_size
            row["status"] = (
                "MATCH"
                if row["actual_sha256"] == row["expected_sha256"]
                and row["actual_bytes"] == row["expected_bytes"]
                else "MISMATCH"
            )

        rows.append(row)

    return {
        "summary": {
            "manifest": manifest_path.name,
            "total": len(rows),
            "match": sum(r["status"] == "MATCH" for r in rows),
            "mismatch": sum(r["status"] == "MISMATCH" for r in rows),
            "missing": sum(r["status"] == "MISSING" for r in rows),
            "error": 0,
        },
        "results": rows,
    }


def run(root: Path) -> dict[str, Any]:
    canonical = root / CANONICAL_MANIFEST
    legacy = root / LEGACY_MANIFEST

    errors: list[str] = []
    reports: list[dict[str, Any]] = []

    if legacy.exists():
        errors.append(f"Legacy manifest must be retired: {legacy}")

    if not canonical.is_file():
        errors.append(f"Canonical manifest is missing: {canonical}")
    else:
        try:
            reports.append(verify_manifest(canonical, root))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            errors.append(f"Unable to verify canonical manifest: {exc}")

    return {
        "manifests": reports,
        "manifest_conflicts": [],
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--public-data",
        type=Path,
        default=Path("public_data"),
    )
    args = parser.parse_args()
    report = run(args.public_data)

    print("\n============================================")
    print("US500 PUBLICATION INTEGRITY")
    print("============================================")

    for item in report["manifests"]:
        summary = item["summary"]
        print(f"\nManifest: {summary['manifest']}")
        print(f"Total:     {summary['total']}")
        print(f"Match:     {summary['match']}")
        print(f"Mismatch:  {summary['mismatch']}")
        print(f"Missing:   {summary['missing']}")
        print(f"Error:     {summary['error']}")

        for row in item["results"]:
            if row["status"] == "MATCH":
                continue
            print(f"  [{row['status']}] {row['file']}")
            print(f"    expected sha256: {row['expected_sha256']}")
            print(f"    actual sha256:   {row['actual_sha256']}")
            print(f"    expected bytes:  {row['expected_bytes']}")
            print(f"    actual bytes:    {row['actual_bytes']}")

    if report["errors"]:
        print("\nErrors:")
        for error in report["errors"]:
            print(f"  - {error}")

    failed = bool(report["errors"])
    for item in report["manifests"]:
        summary = item["summary"]
        failed = failed or summary["mismatch"] > 0 or summary["missing"] > 0

    if failed:
        print("\nPUBLICATION INTEGRITY FAILED")
        return 1

    print("\nPUBLICATION INTEGRITY PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
