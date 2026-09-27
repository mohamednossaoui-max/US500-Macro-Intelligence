from pathlib import Path


def _app_source() -> str:
    return Path(__file__).resolve().parents[1].joinpath("app.py").read_text(encoding="utf-8")


def test_manifest_reader_supports_canonical_files_mapping():
    source = _app_source()
    assert 'files = manifest.get("files")' in source
    assert 'result.extend(str(name) for name in files' in source
    assert 'datasets = manifest.get("datasets")' in source


def test_public_data_root_is_anchored_to_app_file():
    source = _app_source()
    assert 'PUBLIC_DATA = Path(__file__).resolve().parent / "public_data"' in source
    assert 'local = PUBLIC_DATA / clean' in source


def test_explorer_routes_only_json_to_json_parser():
    source = _app_source()
    assert 'if suffix == ".csv"' in source
    assert 'elif suffix == ".json"' in source
    assert 'raw, src = load_bytes(selected)' in source


def test_explorer_can_render_text_artifacts_without_marking_them_unreadable():
    source = _app_source()
    assert 'elif isinstance(obj, (bytes, bytearray))' in source
    assert 'bytes(obj).decode("utf-8")' in source
    assert 'st.code(text, language=None)' in source
