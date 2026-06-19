"""Cleanup old market_price_snapshots.

Run from backend/:
    python -m app.scripts.cleanup_market_snapshots                 # list only
    python -m app.scripts.cleanup_market_snapshots --dry-run      # preview
    python -m app.scripts.cleanup_market_snapshots --older-than 7 --yes  # delete

Default retention: 7 days.
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.database import SessionLocal
from app.models.market_price import MarketPriceSnapshot

logger = logging.getLogger("chatbot.cleanup_market")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def _confirm(prompt: str, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    try:
        return input(f"{prompt} [y/N] ").strip().lower() == "y"
    except EOFError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument(
        "--older-than", type=int, default=7,
        help="Retention in days (default 7)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("MARKET PRICE SNAPSHOTS CLEANUP")
    print("=" * 60)
    print(f"DRY-RUN    = {args.dry_run}")
    print(f"ASSUME-YES = {args.yes}")
    print(f"OLDER-THAN = {args.older_than} days")
    print()

    cutoff = datetime.utcnow() - timedelta(days=args.older_than)

    db = SessionLocal()
    try:
        old = db.query(MarketPriceSnapshot).filter(
            MarketPriceSnapshot.scraped_at < cutoff,
        ).all()
        total = db.query(MarketPriceSnapshot).count()

        print(f"Total snapshots in DB:    {total}")
        print(f"Older than {args.older_than} days:    {len(old)}")
        if old:
            by_mp: dict[str, int] = {}
            for snap in old:
                by_mp[snap.marketplace] = by_mp.get(snap.marketplace, 0) + 1
            for mp, n in sorted(by_mp.items()):
                print(f"  {mp}: {n}")

        if not old:
            print("\nNothing to clean.")
            return 0

        if not _confirm(f"Delete {len(old)} old snapshots?", args.yes):
            print("Aborted.")
            return 1

        if args.dry_run:
            print(f"\n[DRY-RUN] would delete {len(old)} snapshots")
            return 0

        for snap in old:
            db.delete(snap)
        db.commit()
        print(f"\n[OK] Deleted {len(old)} old snapshots")
        print(f"Remaining: {db.query(MarketPriceSnapshot).count()}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
