from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "us500-full-research-pipeline.yml"
GITIGNORE = ROOT / ".gitignore"


def test_runtime_artifacts_are_ignored():
    text = GITIGNORE.read_text(encoding="utf-8")
    for rule in (
        "__pycache__/",
        "*.py[cod]",
        ".pytest_cache/",
        "decision_engine_output/",
        "master_artifacts/",
        "master_runs/",
    ):
        assert rule in text


def test_final_sync_restores_only_tracked_runtime_cache_before_rebase():
    text = WORKFLOW.read_text(encoding="utf-8")
    section = text.split("- name: Final Git Synchronization and Push", 1)[1]
    assert "TRACKED_RUNTIME=$(git ls-files" in section
    assert "git restore --worktree" in section
    assert "git clean -fdX" in section
    assert section.index("git clean -fdX") < section.index("git fetch origin main")
    assert section.index("git clean -fdX") < section.index("git rebase origin/main")


def test_final_sync_refuses_real_unstaged_or_untracked_source_changes():
    text = WORKFLOW.read_text(encoding="utf-8")
    section = text.split("- name: Final Git Synchronization and Push", 1)[1]
    assert "if ! git diff --quiet" in section
    assert "git ls-files --others --exclude-standard" in section
    assert "tracked unstaged non-runtime changes remain" in section
    assert "untracked non-ignored files remain" in section
    assert "git reset --hard" not in section
    assert "git clean -fd" not in section.replace("git clean -fdX", "")
