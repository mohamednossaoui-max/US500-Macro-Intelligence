from publication_manifest import manifest_file_names, manifest_metric


def test_canonical_files_mapping_is_visible_to_data_explorer():
    manifest = {
        "files": {
            "alpha.csv": {"bytes": 1, "sha256": "a"},
            "beta.json": {"bytes": 2, "sha256": "b"},
        },
        "publisher": "publisher.py",
        "publisher_version": "1.0",
        "source_run_id": "run-123",
    }
    assert manifest_file_names(manifest) == ["alpha.csv", "beta.json"]
    assert manifest_metric(manifest, "artifact_count") == 2
    assert manifest_metric(manifest, "source_run_id") == "run-123"


def test_empty_canonical_files_mapping_is_not_misread_as_missing_manifest():
    manifest = {"files": {}, "publisher": "publisher.py"}
    assert manifest
    assert manifest_file_names(manifest) == []
    assert manifest_metric(manifest, "artifact_count") == 0


def test_legacy_datasets_supported_only_as_ui_compatibility_fallback():
    manifest = {"datasets": [{"file": "legacy.csv"}], "dataset_count": 1}
    assert manifest_file_names(manifest) == ["legacy.csv"]
    assert manifest_metric(manifest, "artifact_count") == 1
