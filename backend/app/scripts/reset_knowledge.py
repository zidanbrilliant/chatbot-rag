"""Full knowledge-base reset — TRUNCATE all data tables + recreate Qdrant collection.

Run from backend/:
    python -m app.scripts.reset_knowledge --dry-run    # preview SQL
    python -m app.scripts.reset_knowledge --yes         # wipe without prompt

WARNING: This is DESTRUCTIVE. All documents, products, prices, chat history,
feedback, audit logs, evaluation cases, and Qdrant vectors are PERMANENTLY DELETED.

After running, restart the worker (docker compose restart worker) to auto-ingest
files from /data folder.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import text

from app.config import QDRANT_COLLECTION, VECTOR_SIZE
from app.database import SessionLocal
from app.services.qdrant_client import get_qdrant

logger = logging.getLogger("chatbot.reset")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


# Order matters: leaf tables first, then parents
TABLES_TO_TRUNCATE: list[str] = [
    # Chat & feedback (depend on users)
    "message_citations",
    "chat_messages",
    "chat_sessions",
    "feedback",
    # Audit
    "audit_logs",
    # Evaluation
    "rag_evaluation_runs",
    "rag_evaluation_cases",
    # Ingestion
    "ingestion_jobs",
    # Documents (chunks before parent)
    "document_chunks",
    "documents",
    # Prices (ohlc + product_prices before products)
    "price_ohlc",
    "product_prices",
    "products",
    # Users (last — keep or drop based on --keep-users)
    "user_roles",
    "roles",
    "users",
]


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def truncate_tables(db, tables: list[str], dry_run: bool, keep_users: bool) -> int:
    """TRUNCATE tables with CASCADE. Returns total rows affected (best-effort)."""
    target = list(tables)
    if keep_users:
        target = [t for t in target if t not in ("user_roles", "roles", "users")]
    if not target:
        print("[TRUNCATE] nothing to do")
        return 0

    joined = ", ".join(target)
    sql = f"TRUNCATE TABLE {joined} RESTART IDENTITY CASCADE"

    if dry_run:
        print(f"[DRY-RUN] would execute: {sql}")
        return 0

    print(f"[TRUNCATE] {len(target)} table(s): {joined}")
    db.execute(text(sql))
    db.commit()
    print("[TRUNCATE] OK")
    return len(target)


def recreate_qdrant_collection(dry_run: bool) -> bool:
    """Drop + recreate the Qdrant collection. Returns True on success."""
    from qdrant_client.http.models import Distance, VectorParams

    if dry_run:
        print(
            f"[DRY-RUN] would recreate Qdrant collection "
            f"'{QDRANT_COLLECTION}' (size={VECTOR_SIZE}, distance=COSINE)"
        )
        return True

    client = get_qdrant()
    try:
        client.delete_collection(collection_name=QDRANT_COLLECTION)
        print(f"[QDRANT] deleted collection '{QDRANT_COLLECTION}'")
    except Exception as e:
        print(f"[QDRANT] delete skipped (collection may not exist): {e}")

    client.create_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=VectorParams(
            size=VECTOR_SIZE,
            distance=Distance.COSINE,
        ),
    )
    info = client.get_collection(collection_name=QDRANT_COLLECTION)
    print(
        f"[QDRANT] recreated '{QDRANT_COLLECTION}' "
        f"(size={VECTOR_SIZE}, distance=COSINE, status={info.status})"
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true", help="Preview SQL only")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompts")
    parser.add_argument(
        "--keep-users", action="store_true", help="Preserve users/roles/user_roles"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("KNOWLEDGE BASE RESET")
    print("=" * 60)
    print(f"DRY-RUN    = {args.dry_run}")
    print(f"ASSUME-YES = {args.yes}")
    print(f"KEEP-USERS = {args.keep_users}")
    print(f"TARGETS    = {len(TABLES_TO_TRUNCATE)} tables + Qdrant '{QDRANT_COLLECTION}'")
    print()

    if not args.dry_run and not _confirm(
        "This will PERMANENTLY delete all data. Continue?", args.yes
    ):
        print("Aborted.")
        return 1

    db = SessionLocal()
    try:
        truncate_tables(db, TABLES_TO_TRUNCATE, args.dry_run, args.keep_users)
    except Exception as e:
        db.rollback()
        logger.error("TRUNCATE failed: %s", e)
        return 1
    finally:
        db.close()

    try:
        recreate_qdrant_collection(args.dry_run)
    except Exception as e:
        logger.error("Qdrant recreate failed: %s", e)
        return 1

    if args.dry_run:
        print("\n[DRY-RUN] no changes made. Re-run with --yes to execute.")
    else:
        print("\n[OK] Knowledge base reset complete.")
        print("Next: docker compose restart worker  (triggers auto-ingest from /data)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
