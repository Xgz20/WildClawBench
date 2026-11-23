from pathlib import Path

import pytest

from src.e2e.preparation import _revision


def test_revision_uses_release_marker_without_git_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WCB_E2E_REVISION", raising=False)
    revision = "a" * 40
    (tmp_path / ".wildclawbench-revision").write_text(revision + "\n", encoding="utf-8")

    assert _revision(tmp_path) == revision


def test_revision_rejects_invalid_release_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("WCB_E2E_REVISION", raising=False)
    (tmp_path / ".wildclawbench-revision").write_text("not-a-revision\n", encoding="utf-8")

    with pytest.raises(ValueError, match="WCB_E2E_REVISION_INVALID"):
        _revision(tmp_path)
