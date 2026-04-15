"""Tests for checkpoint module."""
import sys
sys.path.insert(0, ".")

from pathlib import Path
from core_modules.export.checkpoint import checkpoint_path, create_checkpoint, load_checkpoint, save_checkpoint
from core_modules.export.models import RepoRef, CheckpointState, DocExportState


def test_checkpoint_path(tmp_path):
    path = checkpoint_path(tmp_path)
    assert path.name == "_export_checkpoint.json"
    assert path.parent == tmp_path


def test_create_checkpoint():
    repo = RepoRef(group_login="group", book_slug="book", book_id=123)
    cp = create_checkpoint(repo)
    assert cp.repo["group_login"] == "group"
    assert cp.repo["book_slug"] == "book"
    assert cp.repo["book_id"] == 123
    assert cp.export_started_at


def test_load_missing_checkpoint(tmp_path):
    assert load_checkpoint(tmp_path) is None


def test_save_and_load_checkpoint(tmp_path):
    repo = RepoRef(group_login="group", book_slug="book", book_id=123)
    cp = create_checkpoint(repo)
    cp.completed_doc_ids = [1, 2, 3]
    cp.failed_doc_ids = [4]
    cp.doc_states = {
        "1": DocExportState(stage="completed", markdown_path="doc1.md"),
        "4": DocExportState(stage="failed", warnings=["warn"], warning_count=1),
    }
    save_checkpoint(tmp_path, cp)
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None
    assert loaded.completed_doc_ids == [1, 2, 3]
    assert loaded.failed_doc_ids == [4]
    assert loaded.doc_states["1"].stage == "completed"
    assert loaded.doc_states["4"].warnings == ["warn"]


def test_save_creates_file(tmp_path):
    repo = RepoRef(group_login="group", book_slug="book")
    cp = create_checkpoint(repo)
    save_checkpoint(tmp_path, cp)
    assert checkpoint_path(tmp_path).exists()
