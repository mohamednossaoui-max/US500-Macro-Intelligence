from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DEFAULT_PUBLIC_DATA = Path("public_data")

MANIFEST_NAMES = (
    "public_data_manifest.json",
    "manifest.json",
)


def sha256_file(path: Path) -> str:
    """Return SHA-256 of the exact bytes stored on disk."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open(
        "r",
        encoding="utf-8",
    ) as handle:
        data = json.load(handle)

    if not isinstance(data, dict):
        raise ValueError(
            f"{path} must contain a JSON object."
        )

    return data


def extract_entries(
    manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """
    Support both manifest formats currently present
    in the repository.

    Format A:
        {
            "files": {
                "file.csv": {
                    "bytes": ...,
                    "sha256": ...
                }
            }
        }

    Format B:
        {
            "datasets": [
                {
                    "file": "file.csv",
                    "bytes": ...,
                    "sha256": ...
                }
            ]
        }
    """

    entries: dict[str, dict[str, Any]] = {}

    files = manifest.get("files")

    if isinstance(files, dict):
        for filename, metadata in files.items():
            if not isinstance(filename, str):
                continue

            if not isinstance(metadata, dict):
                continue

            entries[filename] = {
                "bytes": metadata.get("bytes"),
                "sha256": metadata.get("sha256"),
            }

        return entries

    datasets = manifest.get("datasets")

    if isinstance(datasets, list):
        for item in datasets:
            if not isinstance(item, dict):
                continue

            filename = item.get("file")

            if not isinstance(filename, str):
                continue

            entries[filename] = {
                "bytes": item.get("bytes"),
                "sha256": item.get("sha256"),
            }

        return entries

    raise ValueError(
        "Unsupported manifest format. "
        "Expected 'files' or 'datasets'."
    )


def verify_entry(
    public_data: Path,
    filename: str,
    metadata: dict[str, Any],
) -> dict[str, Any]:

    path = public_data / filename

    expected_hash = metadata.get("sha256")
    expected_bytes = metadata.get("bytes")

    result: dict[str, Any] = {
        "file": filename,
        "status": "ERROR",
        "expected_sha256": expected_hash,
        "actual_sha256": None,
        "expected_bytes": expected_bytes,
        "actual_bytes": None,
    }

    if not path.exists():
        result["status"] = "MISSING"
        return result

    if not path.is_file():
        result["status"] = "ERROR"
        return result

    actual_bytes = path.stat().st_size
    actual_hash = sha256_file(path)

    result["actual_bytes"] = actual_bytes
    result["actual_sha256"] = actual_hash

    hash_match = (
        isinstance(expected_hash, str)
        and expected_hash == actual_hash
    )

    bytes_match = (
        isinstance(expected_bytes, int)
        and expected_bytes == actual_bytes
    )

    if hash_match and bytes_match:
        result["status"] = "MATCH"
    else:
        result["status"] = "MISMATCH"

    return result


def verify_manifest(
    manifest_path: Path,
    public_data: Path,
) -> dict[str, Any]:

    manifest = load_json(manifest_path)
    entries = extract_entries(manifest)

    results = []

    for filename in sorted(entries):
        results.append(
            verify_entry(
                public_data,
                filename,
                entries[filename],
            )
        )

    summary = {
        "manifest": manifest_path.name,
        "total": len(results),
        "match": sum(
            r["status"] == "MATCH"
            for r in results
        ),
        "mismatch": sum(
            r["status"] == "MISMATCH"
            for r in results
        ),
        "missing": sum(
            r["status"] == "MISSING"
            for r in results
        ),
        "error": sum(
            r["status"] == "ERROR"
            for r in results
        ),
    }

    return {
        "summary": summary,
        "results": results,
    }


def compare_manifests(
    reports: list[dict[str, Any]],
) -> list[dict[str, Any]]:

    by_file: dict[
        str,
        dict[str, dict[str, Any]],
    ] = {}

    for report in reports:
        manifest_name = report["summary"]["manifest"]

        for result in report["results"]:
            filename = result["file"]

            by_file.setdefault(
                filename,
                {},
            )[manifest_name] = result

    conflicts = []

    for filename, manifests in sorted(
        by_file.items()
    ):
        expected_hashes = {
            name: result.get("expected_sha256")
            for name, result in manifests.items()
        }

        unique_hashes = {
            value
            for value in expected_hashes.values()
            if isinstance(value, str)
        }

        if len(unique_hashes) > 1:
            conflicts.append(
                {
                    "file": filename,
                    "manifest_hashes":
                        expected_hashes,
                }
            )

    return conflicts


def run(
    public_data: Path,
) -> dict[str, Any]:

    reports = []

    for manifest_name in MANIFEST_NAMES:
        manifest_path = (
            public_data / manifest_name
        )

        if not manifest_path.exists():
            continue

        reports.append(
            verify_manifest(
                manifest_path,
                public_data,
            )
        )

    if not reports:
        raise FileNotFoundError(
            "No publication manifest found."
        )

    conflicts = compare_manifests(
        reports
    )

    return {
        "public_data":
            str(public_data),
        "manifests":
            reports,
        "manifest_conflicts":
            conflicts,
    }


def print_report(
    report: dict[str, Any],
) -> None:

    print(
        "\n"
        "============================================\n"
        "US500 PUBLICATION INTEGRITY\n"
        "============================================"
    )

    for manifest_report in report["manifests"]:
        summary = manifest_report["summary"]

        print(
            f"\nManifest: {summary['manifest']}"
        )

        print(
            f"Total:     {summary['total']}"
        )
        print(
            f"Match:     {summary['match']}"
        )
        print(
            f"Mismatch:  {summary['mismatch']}"
        )
        print(
            f"Missing:   {summary['missing']}"
        )
        print(
            f"Error:     {summary['error']}"
        )

        problems = [
            result
            for result
            in manifest_report["results"]
            if result["status"] != "MATCH"
        ]

        if problems:
            print("\nProblems:")

            for result in problems:
                print(
                    f"  [{result['status']}] "
                    f"{result['file']}"
                )

                print(
                    "    expected sha256: "
                    f"{result['expected_sha256']}"
                )

                print(
                    "    actual sha256:   "
                    f"{result['actual_sha256']}"
                )

                print(
                    "    expected bytes:  "
                    f"{result['expected_bytes']}"
                )

                print(
                    "    actual bytes:    "
                    f"{result['actual_bytes']}"
                )

    conflicts = report[
        "manifest_conflicts"
    ]

    print(
        "\n"
        "--------------------------------------------"
    )

    print(
        f"Manifest conflicts: {len(conflicts)}"
    )

    for conflict in conflicts:
        print(
            f"\n  {conflict['file']}"
        )

        for (
            manifest_name,
            expected_hash,
        ) in conflict[
            "manifest_hashes"
        ].items():

            print(
                f"    {manifest_name}: "
                f"{expected_hash}"
            )

    print(
        "\n"
        "============================================"
    )


def main() -> int:

    parser = argparse.ArgumentParser(
        description=(
            "Read-only verification of "
            "US500 public_data publication integrity."
        )
    )

    parser.add_argument(
        "--public-data",
        type=Path,
        default=DEFAULT_PUBLIC_DATA,
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON report.",
    )

    args = parser.parse_args()

    try:
        report = run(
            args.public_data
        )

    except Exception as exc:
        print(
            f"Integrity verification failed: {exc}",
            file=sys.stderr,
        )
        return 2

    if args.json:
        print(
            json.dumps(
                report,
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print_report(report)

    # PR-01 is diagnostic.
    # Existing mismatches must not break deployment.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
