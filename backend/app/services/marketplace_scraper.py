"""Marketplace scraper — fetches current market prices for products.

Strategy:
1. Check DB cache (`market_price_snapshots`) for fresh entries (TTL 24h)
2. For cache misses, do DuckDuckGo `site:` searches per marketplace
3. Extract prices from search snippets using existing price_parser
4. Save new snapshots to cache for next time

Why search-driven (not real page scraping):
- Avoids ToS/rate-limit issues with Tokopedia/Shopee/etc.
- No browser/headless Chrome needed
- Free (no API keys)
- Good enough for 90% of catalog products
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import ENABLE_WEB_SEARCH, SEARCH_MAX_RESULTS
from app.models.market_price import (
    MARKETPLACE_BRANDS,
    MARKETPLACE_DOMAINS,
    MARKETPLACE_TOKOPEDIA,
    MarketPriceSnapshot,
    SUPPORTED_MARKETPLACES,
)
from app.services.price_parser import ExtractedPrice, extract_prices_from_snippet
from app.services.search_client import search_web

logger = logging.getLogger("chatbot")


CACHE_TTL_HOURS = 24
SNIPPET_PRICE_LIMIT = 200


@dataclass
class MarketPrice:
    """One marketplace price observation."""

    marketplace: str
    price: Decimal
    currency: str
    url: str | None = None
    snippet_excerpt: str | None = None
    scraped_at: datetime | None = None
    is_cached: bool = False
    confidence: float = 0.0
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "marketplace": self.marketplace,
            "price": float(self.price),
            "currency": self.currency,
            "url": self.url,
            "snippet_excerpt": (self.snippet_excerpt or "")[:SNIPPET_PRICE_LIMIT],
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "is_cached": self.is_cached,
            "confidence": self.confidence,
        }


class MarketplaceScraper:
    """Service for fetching & caching marketplace prices."""

    def __init__(self, db: Session):
        self.db = db

    def get_cached(
        self,
        product_query: str,
        marketplace: str,
        max_age_hours: int = CACHE_TTL_HOURS,
    ) -> MarketPrice | None:
        """Return cached snapshot if fresh enough, else None."""
        if not product_query or not marketplace:
            return None
        cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
        snap = (
            self.db.query(MarketPriceSnapshot)
            .filter(
                MarketPriceSnapshot.product_query == product_query.strip().lower(),
                MarketPriceSnapshot.marketplace == marketplace,
                MarketPriceSnapshot.scraped_at >= cutoff,
            )
            .order_by(MarketPriceSnapshot.scraped_at.desc())
            .first()
        )
        if not snap:
            return None
        return self._snapshot_to_price(snap, is_cached=True)

    def save_snapshot(
        self,
        product_query: str,
        marketplace: str,
        price: Decimal,
        currency: str,
        url: str | None,
        snippet_excerpt: str | None,
        product_sku: str | None = None,
    ) -> MarketPriceSnapshot:
        """Persist a new snapshot to cache. Returns the saved row."""
        snap = MarketPriceSnapshot(
            product_query=product_query.strip().lower(),
            product_sku=product_sku,
            marketplace=marketplace,
            price=price,
            currency=currency,
            url=url,
            snippet_excerpt=(snippet_excerpt or "")[:500] if snippet_excerpt else None,
            scraped_at=datetime.utcnow(),
        )
        self.db.add(snap)
        self.db.commit()
        self.db.refresh(snap)
        return snap

    def search_marketplace(
        self,
        product_query: str,
        marketplace: str,
        max_results: int = 3,
    ) -> MarketPrice | None:
        """Do a DDG `site:<domain>` search and extract the first useful price.

        Returns None if no usable result found.
        """
        if not ENABLE_WEB_SEARCH or not product_query.strip():
            return None

        domains = MARKETPLACE_DOMAINS.get(marketplace, [])
        if not domains:
            return None

        # Use the first domain for `site:` operator
        domain = domains[0]
        query = f'site:{domain} "{product_query.strip()}" harga'
        try:
            results = search_web(query, max_results=max_results)
        except Exception as e:
            logger.warning("Marketplace search %s failed: %s", marketplace, str(e)[:120])
            return None

        for r in results:
            url = r.url or ""
            # Verify the URL is from the expected marketplace
            if not _url_matches_marketplace(url, marketplace):
                continue
            prices = extract_prices_from_snippet(r.snippet or "", default_currency="IDR")
            if not prices:
                continue
            best = _pick_best_price(prices, product_query)
            if not best:
                continue
            return MarketPrice(
                marketplace=marketplace,
                price=Decimal(str(best.value)),
                currency=best.currency or "IDR",
                url=url,
                snippet_excerpt=r.snippet or "",
                scraped_at=datetime.utcnow(),
                is_cached=False,
                confidence=best.confidence,
            )
        return None

    def search_all(
        self,
        product_query: str,
        product_sku: str | None = None,
        marketplaces: list[str] | None = None,
        per_market_timeout: float = 5.0,
    ) -> list[MarketPrice]:
        """Search all marketplaces (cache-first, then live search on miss).

        Returns a list of MarketPrice, one per marketplace that returned data.
        Includes both cached hits (is_cached=True) and freshly scraped results.
        Runs cache checks in parallel and live scrapes in parallel for speed.
        """
        if not product_query.strip():
            return []

        targets = marketplaces or SUPPORTED_MARKETPLACES
        results: list[MarketPrice] = []

        # Phase 1: parallel cache lookups
        from concurrent.futures import ThreadPoolExecutor, as_completed
        cache_hits: dict[str, MarketPrice] = {}
        cache_misses: list[str] = []

        with ThreadPoolExecutor(max_workers=len(targets)) as ex:
            future_to_mp = {
                ex.submit(self.get_cached, product_query, mp): mp
                for mp in targets
            }
            for fut in future_to_mp:
                mp = future_to_mp[fut]
                try:
                    cached = fut.result(timeout=2.0)
                    if cached:
                        cache_hits[mp] = cached
                    else:
                        cache_misses.append(mp)
                except Exception as e:
                    logger.debug("Cache lookup failed for %s: %s", mp, str(e)[:80])
                    cache_misses.append(mp)

        for mp in targets:
            if mp in cache_hits:
                results.append(cache_hits[mp])

        # Phase 2: parallel live search for cache misses
        if cache_misses:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=len(cache_misses)) as ex:
                future_to_mp = {
                    ex.submit(self.search_marketplace, product_query, mp): mp
                    for mp in cache_misses
                }
                for fut in future_to_mp:
                    mp = future_to_mp[fut]
                    try:
                        fresh = fut.result(timeout=per_market_timeout)
                    except Exception as e:
                        logger.debug("Live search failed for %s: %s", mp, str(e)[:80])
                        continue
                    if not fresh:
                        continue
                    try:
                        self.save_snapshot(
                            product_query=product_query,
                            marketplace=mp,
                            price=fresh.price,
                            currency=fresh.currency,
                            url=fresh.url,
                            snippet_excerpt=fresh.snippet_excerpt,
                            product_sku=product_sku,
                        )
                    except Exception as e:
                        logger.warning("Save snapshot failed for %s: %s", mp, str(e)[:120])
                    results.append(fresh)

        # Sort by price ASC so the cheapest market is first
        results.sort(key=lambda p: p.price)
        return results

    @staticmethod
    def _snapshot_to_price(snap: MarketPriceSnapshot, is_cached: bool) -> MarketPrice:
        return MarketPrice(
            marketplace=snap.marketplace,
            price=Decimal(str(snap.price)),
            currency=snap.currency or "IDR",
            url=snap.url,
            snippet_excerpt=snap.snippet_excerpt,
            scraped_at=snap.scraped_at,
            is_cached=is_cached,
            confidence=1.0,
        )


def _url_matches_marketplace(url: str, marketplace: str) -> bool:
    """Check if the URL belongs to the expected marketplace domain."""
    if not url:
        return False
    url_lower = url.lower()
    domains = MARKETPLACE_DOMAINS.get(marketplace, [])
    return any(d in url_lower for d in domains)


def _pick_best_price(
    prices: list[ExtractedPrice],
    product_query: str,
) -> ExtractedPrice | None:
    """Pick the most confident price that doesn't look like noise."""
    if not prices:
        return None
    # Filter out very low values (< 100) which are likely extract noise
    candidates = [p for p in prices if p.value >= 100]
    if not candidates:
        return None
    # If product query mentions a number range, prefer prices in that range
    # (e.g., "Polytron PAS 8C28" should match prices for 1-5jt products)
    return max(candidates, key=lambda p: p.confidence)


def get_marketplace_label(marketplace: str) -> str:
    """Human-readable Indonesian label for a marketplace."""
    labels = {
        MARKETPLACE_TOKOPEDIA: "Tokopedia",
        "shopee": "Shopee",
        "lazada": "Lazada",
        "bukalapak": "Bukalapak",
        "bhinneka": "Bhinneka",
        "blibli": "Blibli",
        "brand_store": "Official Store",
    }
    if marketplace in labels:
        return labels[marketplace]
    # Convert snake_case to Title Case for unknowns
    return marketplace.replace("_", " ").title()


def is_marketplace_url(url: str) -> bool:
    """Check if a URL is from any known marketplace."""
    if not url:
        return False
    url_lower = url.lower()
    for domains in MARKETPLACE_DOMAINS.values():
        if any(d in url_lower for d in domains):
            return True
    return False


__all__ = [
    "CACHE_TTL_HOURS",
    "MarketPrice",
    "MarketplaceScraper",
    "get_marketplace_label",
    "is_marketplace_url",
]
