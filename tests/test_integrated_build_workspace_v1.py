import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from scripts.integrated_build_workspace_v1 import prepare, install


def publication(folder, value='old'):
    folder.mkdir(parents=True, exist_ok=True)
    raw=value.encode()
    (folder/'data.csv').write_bytes(raw)
    (folder/'manifest.json').write_text(json.dumps({'files':{
        'data.csv':{'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}}}))


def snapshot(folder):
    return {str(p.relative_to(folder)):p.read_bytes() for p in folder.rglob('*') if p.is_file()}


def test_generated_inputs_never_dirty_checkout(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    publication(root/'public_data')
    source=root/'financial_stress_records_input_v1.csv';source.write_text('original input')
    (root/'app.py').write_text('original source')
    original=snapshot(root)
    workspace=prepare(root,tmp_path/'build')
    (workspace/source.name).write_text('refreshed runtime input')
    (workspace/'economic_historical_events_v1.csv').write_text('runtime dataset')
    (workspace/'audit.json').write_text('{}')
    assert snapshot(root)==original
    publication(workspace/'public_data','new')
    install(root,workspace/'public_data')
    assert source.read_text()=='original input'
    assert (root/'app.py').read_text()=='original source'
    assert not (root/'audit.json').exists()
    assert not (root/'economic_historical_events_v1.csv').exists()
    assert (root/'public_data/data.csv').read_text()=='new'


def test_invalid_candidate_leaves_checkout_unchanged(tmp_path):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    candidate=tmp_path/'candidate';publication(candidate,'new')
    (candidate/'data.csv').write_text('corrupted')
    before=snapshot(root)
    with pytest.raises(ValueError,match='Integrity'):
        install(root,candidate)
    assert snapshot(root)==before


def test_existing_publication_cannot_be_removed(tmp_path):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    (root/'public_data/extra.csv').write_text('preserve')
    candidate=tmp_path/'candidate';publication(candidate,'new')
    with pytest.raises(ValueError,match='remove'):
        install(root,candidate)
    assert (root/'public_data/extra.csv').read_text()=='preserve'


def test_no_nested_workspace_or_candidate(tmp_path):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    with pytest.raises(ValueError,match='separate'):
        prepare(root,root/'build')
    with pytest.raises(ValueError,match='outside'):
        install(root,root/'public_data')


def test_prepare_excludes_runtime_and_git(tmp_path):
    root=tmp_path/'repo';root.mkdir()
    for n in ['.git','__pycache__','.pytest_cache','master_runs','master_artifacts','decision_engine_output']:
        (root/n).mkdir();(root/n/'file').write_text('runtime')
    (root/'source.py').write_text('source')
    workspace=prepare(root,tmp_path/'work')
    assert snapshot(workspace)=={'source.py':b'source'}


def test_install_same_candidate_is_idempotent(tmp_path):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    candidate=tmp_path/'candidate';publication(candidate,'new')
    install(root,candidate);before=snapshot(root)
    install(root,candidate)
    assert snapshot(root)==before


def test_unknown_source_change_still_fails_git_gate(tmp_path):
    # Only the temporary test index is created. No commit, push or rebase.
    root=tmp_path/'repo';root.mkdir()
    subprocess.run(['git','init',str(root)],check=True,capture_output=True)
    (root/'app.py').write_text('source')
    subprocess.run(['git','add','app.py'],cwd=root,check=True)
    (root/'app.py').write_text('unexpected modification')
    assert subprocess.run(['git','diff','--quiet'],cwd=root).returncode==1
    text=(Path(__file__).resolve().parents[1]/'.github/workflows/us500-full-research-pipeline.yml').read_text()
    sync=text.split('- name: Final Git Synchronization and Push',1)[1]
    assert 'if ! git diff --quiet' in sync
    assert 'git ls-files --others --exclude-standard' in sync
    assert 'git reset --hard' not in sync


def test_install_rolls_back_if_directory_swap_fails(tmp_path, monkeypatch):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    candidate=tmp_path/'candidate';publication(candidate,'new')
    before=snapshot(root)
    original=Path.replace
    def failing_swap(self, target):
        if self.name=='validated':
            raise OSError('simulated swap failure')
        return original(self,target)
    monkeypatch.setattr(Path,'replace',failing_swap)
    with pytest.raises(OSError,match='simulated'):
        install(root,candidate)
    assert snapshot(root)==before


def test_archive_history_and_sources_are_preserved(tmp_path):
    root=tmp_path/'repo';root.mkdir();publication(root/'public_data')
    archive=root/'research_history/ath_context_v1/snapshots';archive.mkdir(parents=True)
    (archive/'previous.json').write_text('immutable vintage')
    candidate=tmp_path/'candidate';publication(candidate,'new')
    install(root,candidate)
    assert (archive/'previous.json').read_text()=='immutable vintage'
