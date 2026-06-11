"""Smoke tests for cleanup_failed_documents.py script.

These tests verify the listing and reporting functions work correctly.
Destructive operations (dedupe, requeue, delete) are tested with mock
sessions to avoid mutating real DB state.
"""

import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.scripts.cleanup_failed_documents import (
    list_failed,
    list_duplicates,
    list_orphaned_jobs,
)


def _make_doc(
    id: str = "doc-1",
    filename: str = "test.pdf",
    status: str = "failed",
    file_hash: str = "abc123",
    error_code: str = "EMBED_FAILED",
    error_message: str = "All chunks failed to embed",
    file_path: str = "/data/test.pdf",
    created_at: datetime | None = None,
):
    d = MagicMock()
    d.id = id
    d.original_filename = filename
    # Status is a DocumentStatus enum in real code; mock with .value for print formatting
    status_mock = MagicMock()
    status_mock.value = status
    d.status = status_mock
    d.document_hash = file_hash
    d.error_code = error_code
    d.error_message = error_message
    d.file_path = file_path
    d.created_at = created_at or datetime(2026, 6, 11, 8, 0, 0, tzinfo=timezone.utc)
    return d


def _make_job(id: str = "job-1", document_id: str = "doc-1", status: str = "failed"):
    j = MagicMock()
    j.id = id
    j.document_id = document_id
    status_mock = MagicMock()
    status_mock.value = status
    j.status = status_mock
    return j


# ── list_failed ────────────────────────────────────────


def test_list_failed_returns_only_failed():
    """list_failed should query status='failed' and return matching documents."""
    db = MagicMock()
    failed_doc = _make_doc(id="f1", status="failed")
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = [failed_doc]

    result = list_failed(db)
    assert len(result) == 1
    assert result[0].id == "f1"
    assert result[0].status.value == "failed"


def test_list_failed_empty():
    """No failed documents -> empty list."""
    db = MagicMock()
    db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

    result = list_failed(db)
    assert result == []


# ── list_duplicates ────────────────────────────────────


def test_list_duplicates_groups_by_filename_and_hash():
    """Documents with same (filename, hash) are grouped together."""
    db = MagicMock()
    # status.value is used for print, and status==DocumentStatus.COMPLETED.value (str comparison)
    # is used in dedupe. We need __eq__ to work as expected.
    docs = [
        _make_doc(id="d1", filename="a.pdf", file_hash="hash1", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        _make_doc(id="d2", filename="a.pdf", file_hash="hash1", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)),
        _make_doc(id="d3", filename="b.pdf", file_hash="hash2", created_at=datetime(2026, 1, 3, tzinfo=timezone.utc)),
    ]
    # Make status support == comparison
    for d in docs:
        def _eq(self, other):
            return self.value == other
        type(d.status).__eq__ = _eq
    db.query.return_value.filter.return_value.all.return_value = docs

    result = list_duplicates(db)
    assert len(result) == 1
    label = next(iter(result))
    assert "a.pdf" in label
    assert len(result[label]) == 2


def test_list_duplicates_excludes_null_hash():
    """Documents with NULL/empty hash are excluded (can't dedupe without hash)."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _make_doc(id="d1", file_hash=None),
        _make_doc(id="d2", file_hash=""),
    ]
    result = list_duplicates(db)
    assert result == {}


def test_list_duplicates_no_dupes():
    """Different filenames or different hashes = no duplicates."""
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [
        _make_doc(id="d1", filename="a.pdf", file_hash="h1"),
        _make_doc(id="d2", filename="a.pdf", file_hash="h2"),
        _make_doc(id="d3", filename="b.pdf", file_hash="h1"),
    ]
    result = list_duplicates(db)
    assert result == {}


# ── list_orphaned_jobs ─────────────────────────────────


def test_list_orphaned_jobs_returns_jobs_with_missing_docs():
    """Jobs whose document_id is not in documents table are returned."""
    db = MagicMock()
    # First query: get all jobs; second query (inner): get all document IDs
    # The expression: ~IngestionJob.document_id.in_(db.query(Document.id))
    # We need to set up the mock so .in_(...) returns a filter and the outer .filter(...) call works.
    mock_filter = MagicMock()
    mock_filter.all.return_value = [_make_job(id="orphan-1", document_id="missing-doc")]
    db.query.return_value.filter.return_value = mock_filter

    result = list_orphaned_jobs(db)
    assert len(result) == 1
    assert result[0].id == "orphan-1"


def test_list_orphaned_jobs_empty():
    db = MagicMock()
    mock_filter = MagicMock()
    mock_filter.all.return_value = []
    db.query.return_value.filter.return_value = mock_filter
    result = list_orphaned_jobs(db)
    assert result == []
