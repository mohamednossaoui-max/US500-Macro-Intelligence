"""Helpers for the canonical public_data/manifest.json publication contract."""
from __future__ import annotations

from typing import Any


def manifest_file_names(manifest: dict[str, Any]) -> list[str]:
    """Return published artifact names from the canonical ``files`` mapping.

    A legacy ``datasets`` list is accepted only as a UI compatibility fallback;
    publication integrity continues to require the canonical ``files`` mapping.
    """
    files = manifest.get("files")
    if isinstance(files, dict):
        return sorted({name for name in files if isinstance(name, str) and name})

    datasets = manifest.get("datasets")
    if isinstance(datasets, list):
        names = {
            item["file"]
            for item in datasets
            if isinstance(item, dict) and isinstance(item.get("file"), str) and item["file"]
        }
        return sorted(names)

    return []


def manifest_metric(manifest: dict[str, Any], key: str, default: Any = "—") -> Any:
    """Read current manifest metadata with narrowly-scoped legacy aliases."""
    if key == "artifact_count":
        files = manifest.get("files")
        if isinstance(files, dict):
            return len(files)
        return manifest.get("dataset_count", default)
    if key == "source_run_id":
        return manifest.get("source_run_id", manifest.get("master_run_id", default))
    if key == "publisher":
        return manifest.get("publisher", default)
    if key == "publisher_version":
        return manifest.get("publisher_version", default)
    return manifest.get(key, default)
