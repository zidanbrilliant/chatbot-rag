"""Cleanup script for failed/duplicate documents and stale ingestion jobs.

Run from backend/:
    python -m app.scripts.cleanup_failed_documents                # list only
    python -m app.scripts.cleanup_failed_documents --dry-run      # preview changes
    python -m app.scripts.cleanup_failed_documents --dedupe       # remove duplicate documents
    python -m app.scripts.cleanup_failed_documents --requeue-failed
    python -m app.scripts.cleanup_failed_documents --delete-orphans
    python -m app.scripts.cleanup_failed_documents --all --yes    # do everything non-interactively

SAFETY:
    - No destructive action runs without explicit --yes (or interactive y/N).
    --dry-run shows what would change but commits nothing.
    - Cascade deletes (chunks, qdrant vectors) follow the ForeignKey rules.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import DATA_DIR
from app.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.ingestion import IngestionJob, IngestionJobStatus

logger = logging.getLogger("chatbot.cleanup")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def list_failed(db) -> list[Document]:
    rows = (
        db.query(Document)
        .filter(Document.status == DocumentStatus.FAILED.value)
        .order_by(Document.created_at)
        .all()
    )
    print(f"\n[FAILED] {len(rows)} document(s):")
    for d in rows:
        print(f"  {d.id}  {d.original_filename}  err={d.error_code or '-':<20}  msg={(d.error_message or '-')[:60]}")
    return rows


def list_duplicates(db) -> dict[str, list[Document]]:
    """Group documents by (filename, hash). Hash NULL/empty is excluded."""
    rows = (
        db.query(Document)
        .filter(Document.document_hash.isnot(None), Document.document_hash != "")
        .all()
    )
    groups: dict[tuple[str, str], list[Document]] = {}
    for d in rows:
        key = (d.original_filename, d.document_hash)
        groups.setdefault(key, []).append(d)
    dupes = {f"{k[0]}|{k[1][:8]}": v for k, v in groups.items() if len(v) > 1}

    print(f"\n[DUPLICATES] {len(dupes)} filename+hash group(s) with >1 entry:")
    for label, items in dupes.items():
        print(f"  {label}  -> {len(items)} copies:")
        for d in items:
            print(f"    {d.id}  status={d.status.value:<10}  created={d.created_at.isoformat()}")
    return dupes


def list_orphaned_jobs(db) -> list[IngestionJob]:
    """Jobs whose document_id no longer exists."""
    rows = (
        db.query(IngestionJob)
        .filter(~IngestionJob.document_id.in_(db.query(Document.id)))
        .all()
    )
    print(f"\n[ORPHANED JOBS] {len(rows)} job(s) reference missing documents:")
    for j in rows:
        print(f"  {j.id}  status={j.status.value:<10}  doc={j.document_id}")
    return rows


def dedupe_duplicates(db, dry_run: bool, assume_yes: bool) -> int:
    """Delete duplicates: keep the oldest COMPLETED, drop everything else."""
    dupes = list_duplicates(db)
    if not dupes:
        return 0
    if not _confirm("Delete duplicate documents (keep oldest COMPLETED)?", assume_yes):
        return 0

    deleted = 0
    for items in dupes.values():
        items.sort(key=lambda d: d.created_at)
        keep = next((d for d in items if d.status == DocumentStatus.COMPLETED.value), items[0])
        for d in items:
            if d.id == keep.id:
                continue
            if dry_run:
                print(f"  [dry-run] would delete {d.id} ({d.original_filename})")
            else:
                db.delete(d)
                deleted += 1
                print(f"  deleted {d.id} ({d.original_filename})")
    if not dry_run:
        db.commit()
    return deleted


def requeue_failed(db, dry_run: bool, assume_yes: bool) -> int:
    """Reset FAILED documents -> QUEUED and create a fresh IngestionJob.

    Skips documents whose file is no longer on disk.
    """
    failed = list_failed(db)
    if not failed:
        return 0
    if not _confirm("Re-queue FAILED documents (only those with files on disk)?", assume_yes):
        return 0

    requeued = 0
    for d in failed:
        if not os.path.isfile(d.file_path):
            print(f"  [skip] {d.original_filename}: file not found at {d.file_path}")
            continue
        if dry_run:
            print(f"  [dry-run] would re-queue {d.id} ({d.original_filename})")
            requeued += 1
            continue
        d.status = DocumentStatus.QUEUED.value
        d.error_code = None
        d.error_message = None
        job = IngestionJob(
            document_id=d.id,
            status=IngestionJobStatus.QUEUED.value,
            attempts=0,
            max_attempts=3,
        )
        db.add(job)
        requeued += 1
        print(f"  re-queued {d.id} ({d.original_filename})")
    if not dry_run:
        db.commit()
    return requeued


def delete_orphaned_jobs(db, dry_run: bool, assume_yes: bool) -> int:
    """Delete jobs whose document no longer exists."""
    orphans = list_orphaned_jobs(db)
    if not orphans:
        return 0
    if not _confirm("Delete orphaned jobs?", assume_yes):
        return 0
    if dry_run:
        return len(orphans)
    for j in orphans:
        db.delete(j)
    db.commit()
    return len(orphans)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Preview changes; commit nothing")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument("--dedupe", action="store_true", help="Delete duplicate documents")
    parser.add_argument("--requeue-failed", action="store_true", help="Re-queue FAILED documents")
    parser.add_argument("--delete-orphans", action="store_true", help="Delete orphaned jobs")
    parser.add_argument("--all", action="store_true", help="Run dedupe + requeue + delete-orphans")
    parser.add_argument("--data-dir", default=DATA_DIR, help="DATA_DIR for sanity check (unused otherwise)")
    args = parser.parse_args()

    print(f"DATA_DIR = {args.data_dir}")
    print(f"DRY-RUN  = {args.dry_run or 'no destructive flag set'}")
    print(f"ASSUME-Y = {args.yes}")

    db = SessionLocal()
    try:
        if not any([args.dedupe, args.requeue_failed, args.delete_orphans, args.all]):
            list_failed(db)
            list_duplicates(db)
            list_orphaned_jobs(db)
            print("\nNo action taken. Use --dedupe / --requeue-failed / --delete-orphans / --all to act.")
            return 0

        total = 0
        if args.all or args.dedupe:
            total += dedupe_duplicates(db, args.dry_run, args.yes)
        if args.all or args.requeue_failed:
            total += requeue_failed(db, args.dry_run, args.yes)
        if args.all or args.delete_orphans:
            total += delete_orphaned_jobs(db, args.dry_run, args.yes)

        verb = "would change" if args.dry_run else "changed"
        print(f"\nDone. {verb} {total} row(s).")
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
