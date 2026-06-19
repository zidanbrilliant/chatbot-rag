"""Generic price lookup service.

Handles 4 price-query categories:
1. Product catalog lookup  (name-based, latest price)
2. Timeseries lookup      (date-based, specific date)
3. Range lookup           (date range with OHLC field + aggregation)
4. Multi-criteria filter   (supplier, brand, price range, attributes)

Sources queried in parallel (Postgres + file scan):
- Postgres: products + product_prices + price_ohlc tables
- CSV/XLSX: /data directory (falls back to pandas direct read)

Returns normalized PriceResult list â€” caller can merge with web search results.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.price import PriceOHLC, Product

logger = logging.getLogger("chatbot")


# Threshold after which an internal price is considered stale.
# Stale results are still returned but deprioritized in the response.
STALE_DAYS: int = 30


def _compute_staleness(price_date: date | None) -> tuple[bool, int | None]:
    """Compute is_stale flag and age_days for a price_date."""
    if price_date is None:
        return False, None
    today = date.today()
    age = (today - price_date).days
    return age > STALE_DAYS, age


def make_price_result(
    *,
    product_name: str,
    price: Decimal,
    currency: str,
    unit: str | None = None,
    source: str = "",
    source_detail: str = "",
    price_date: date | None = None,
    field_type: str = "",
    attributes: dict[str, Any] | None = None,
    relevance_score: float = 1.0,
    url: str | None = None,
    title: str | None = None,
) -> PriceResult:
    """Factory that auto-populates is_stale and age_days from price_date."""
    is_stale, age_days = _compute_staleness(price_date)
    return PriceResult(
        product_name=product_name,
        price=price,
        currency=currency,
        unit=unit,
        source=source,
        source_detail=source_detail,
        price_date=price_date,
        field_type=field_type,
        attributes=attributes or {},
        relevance_score=relevance_score,
        url=url,
        title=title,
        is_stale=is_stale,
        age_days=age_days,
    )


def select_top_results(
    internal: list[PriceResult],
    market: list | None = None,
    max_internal: int = 2,
    max_market: int = 2,
) -> tuple[list[PriceResult], list]:
    """Pick the most relevant results for display.

    Strategy:
    - Internal: keep up to `max_internal` —
        1) Cheapest non-stale (best deal)
        2) Most recent non-stale (freshest data)
        3) If only stale data exists, cheapest stale
    - Marketplace: keep up to `max_market` —
        1) Cheapest
        2) Most recently scraped
    - Stale internal results are demoted to the bottom of the list.

    Returns: (selected_internal, selected_market)
    """
    market = market or []

    if not internal and not market:
        return [], []

    # Split internal into fresh and stale
    fresh = [r for r in internal if not getattr(r, "is_stale", False) and r.price]
    stale = [r for r in internal if getattr(r, "is_stale", False) and r.price]

    selected_internal: list = []
    if fresh:
        # Cheapest fresh wins
        cheapest = min(fresh, key=lambda r: r.price)
        selected_internal.append(cheapest)
        # Most recent fresh (different from cheapest, by price_date)
        if len(fresh) > 1:
            most_recent = max(
                (r for r in fresh if r is not cheapest or len(fresh) == 1),
                key=lambda r: r.price_date or date.min,
            )
            if most_recent is not cheapest:
                selected_internal.append(most_recent)
    elif stale:
        # Only stale data — show cheapest stale
        selected_internal.append(min(stale, key=lambda r: r.price))

    # Trim to max_internal before adding any extra stale
    selected_internal = selected_internal[:max_internal]

    # If we still have room in the budget, append up to 2 stale at the bottom
    remaining = max_internal - len(selected_internal)
    if remaining > 0 and stale:
        seen_keys = {
            (r.product_name, float(r.price), r.currency)
            for r in selected_internal
        }
        extra_stale = [
            r for r in sorted(stale, key=lambda r: r.price)
            if (r.product_name, float(r.price), r.currency) not in seen_keys
        ][:remaining]
        selected_internal = selected_internal + extra_stale

    # Marketplace: cheapest first, then most recent (by scraped_at)
    if market:
        priced = [m for m in market if getattr(m, "price", None) and m.price > 0]
        if priced:
            priced_sorted_cheapest = sorted(priced, key=lambda m: m.price)
            priced_sorted_recent = sorted(
                priced,
                key=lambda m: m.scraped_at or datetime.min,
                reverse=True,
            )
            selected_market: list = []
            # Add cheapest
            if priced_sorted_cheapest:
                selected_market.append(priced_sorted_cheapest[0])
            # Add most recent (different from cheapest)
            for m in priced_sorted_recent:
                if m is priced_sorted_cheapest[0]:
                    continue
                selected_market.append(m)
                break
            selected_market = selected_market[:max_market]
        else:
            selected_market = []
    else:
        selected_market = []

    return selected_internal, selected_market


@dataclass
class PriceResult:
    """Unified price result from any source."""

    product_name: str
    price: Decimal
    currency: str
    unit: str | None = None
    source: str = ""          # "postgres" | "postgres_ohlc" | "csv" | "xlsx"
    source_detail: str = ""   # sku/uuid or filename
    price_date: date | None = None
    field_type: str = ""      # "high" | "low" | "open" | "close" | "latest" | ""
    attributes: dict[str, Any] = field(default_factory=dict)
    relevance_score: float = 1.0
    url: str | None = None
    title: str | None = None
    is_stale: bool = False   # True if price_date > STALE_DAYS ago
    age_days: int | None = None  # computed at build time


class PriceService:
    """Generic price lookup service â€” multi-source, multi-category."""

    def __init__(self, db: Session, data_dir: str | None = None):
        self.db = db
        self.data_dir = data_dir or DATA_DIR

    # â”€â”€ 1. Product catalog lookup (name-based) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup_by_name(
        self, name: str, category: str | None = None, limit: int = 10
    ) -> list[PriceResult]:
        """Lookup by product name. Returns latest price for each match.

        Uses multi-strategy search:
        1. Exact substring match
        2. Drop first word (e.g., "speaker") and retry â€” handles cases like
           "speaker Polytron X" matching "SPEAKER AKTIF POLYTRON X"
        3. Drop last word â€” handles queries like "Polytron X terbaru"
        """
        if not name or len(name.strip()) < 2:
            return []

        # Try multiple name strategies
        strategies = self._build_name_strategies(name)
        seen_product_ids: set = set()
        products: list = []

        for strategy_name in strategies:
            query = self.db.query(Product).filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{strategy_name}%"),
            )
            if category:
                query = query.filter(Product.category == category)
            for p in query.limit(limit * 2).all():
                if p.id not in seen_product_ids:
                    seen_product_ids.add(p.id)
                    products.append(p)
            if len(products) >= limit:
                break

        results: list[PriceResult] = []
        for p in products:
            latest = p.latest_price()
            latest_ohlc = p.latest_ohlc()
            # Prefer product_prices, fallback to OHLC close
            if latest:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=latest.to_decimal(),
                        currency=latest.currency,
                        unit=p.unit,
                        source="postgres",
                        source_detail=p.sku or str(p.id),
                        price_date=latest.price_date,
                        field_type="latest",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(name, p.name),
                    )
                )
            elif latest_ohlc and latest_ohlc.close is not None:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=Decimal(str(latest_ohlc.close)),
                        currency=latest_ohlc.currency,
                        unit=p.unit,
                        source="postgres_ohlc",
                        source_detail=p.sku or str(p.id),
                        price_date=latest_ohlc.trade_date,
                        field_type="close",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(name, p.name),
                    )
                )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    @staticmethod
    def _build_name_strategies(name: str) -> list[str]:
        """Build list of name variations to try, in priority order.

        Strategy:
        1. Full name as-is
        2. Drop first word (generic category like "speaker", "LED")
        3. Drop last word (e.g., "terbaru", "hari ini")
        4. Take longest 2-word substring from end (brand + model)
        5. Apply synonym substitution (e.g., "AC" -> "AIR COOLER") to the
           original name and repeat the top strategies.
        """
        strategies: list[str] = []
        cleaned = name.strip()
        if cleaned:
            strategies.append(cleaned)

        words = cleaned.split()
        if len(words) >= 2:
            # Drop first word
            strategies.append(" ".join(words[1:]))
        if len(words) >= 2:
            # Drop last word
            strategies.append(" ".join(words[:-1]))
        if len(words) >= 2:
            # Take last 2 words (likely brand+model)
            strategies.append(" ".join(words[-2:]))
        if len(words) >= 3:
            # Take last 3 words
            strategies.append(" ".join(words[-3:]))

        # Synonym expansion: "AC" matches "AIR COOLER" rows in the catalog
        expanded = _expand_synonyms(cleaned)
        if expanded and expanded not in strategies:
            strategies.append(expanded)
            expanded_words = expanded.split()
            if len(expanded_words) >= 2:
                tail2 = " ".join(expanded_words[-2:])
                if tail2 not in strategies:
                    strategies.append(tail2)

        return strategies

    # â”€â”€ 2. Timeseries lookup (date-based) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup_by_date(
        self,
        product_name: str,
        target_date: date,
        field: str = "close",
        limit: int = 5,
    ) -> list[PriceResult]:
        """Lookup historical price on a specific date.

        Tries product_prices first, then price_ohlc.
        """
        if not product_name:
            return []

        products = (
            self.db.query(Product)
            .filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{product_name.strip()}%"),
            )
            .limit(limit * 2)
            .all()
        )

        results: list[PriceResult] = []
        for p in products:
            price_row = p.price_on_date(target_date)
            if price_row:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=price_row.to_decimal(),
                        currency=price_row.currency,
                        unit=p.unit,
                        source="postgres",
                        source_detail=p.sku or str(p.id),
                        price_date=price_row.price_date,
                        field_type=field or "latest",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(product_name, p.name),
                    )
                )
                continue

            # Fallback to OHLC
            ohlc_row = p.ohlc_on_date(target_date)
            if ohlc_row:
                value = ohlc_row.get_field(field) if field else ohlc_row.get_field("close")
                if value is not None:
                    results.append(
                        make_price_result(
                            product_name=p.name,
                            price=value,
                            currency=ohlc_row.currency,
                            unit=p.unit,
                            source="postgres_ohlc",
                            source_detail=p.sku or str(p.id),
                            price_date=ohlc_row.trade_date,
                            field_type=field or "close",
                            attributes=p.attributes or {},
                            relevance_score=self._name_relevance(product_name, p.name),
                        )
                    )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # â”€â”€ 2b. OHLC-specific lookup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup_ohlc_by_date(
        self,
        product_name: str,
        target_date: date,
        field: str = "close",
        limit: int = 5,
    ) -> list[PriceResult]:
        """Lookup specific OHLC field on a specific date."""
        if not product_name or field not in ("open", "high", "low", "close"):
            return []

        products = (
            self.db.query(Product)
            .filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{product_name.strip()}%"),
            )
            .limit(limit * 2)
            .all()
        )

        results: list[PriceResult] = []
        for p in products:
            ohlc = p.ohlc_on_date(target_date)
            if not ohlc:
                continue
            value = ohlc.get_field(field)
            if value is None:
                continue
            results.append(
                make_price_result(
                    product_name=p.name,
                    price=value,
                    currency=ohlc.currency,
                    unit=p.unit,
                    source="postgres_ohlc",
                    source_detail=p.sku or str(p.id),
                    price_date=ohlc.trade_date,
                    field_type=field,
                    attributes=p.attributes or {},
                    relevance_score=self._name_relevance(product_name, p.name),
                )
            )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # â”€â”€ 3. Range lookup (OHLC aggregation) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup_ohlc_by_range(
        self,
        product_name: str,
        start: date,
        end: date,
        field: str = "high",
        aggregation: str = "max",
        limit: int = 5,
    ) -> list[PriceResult]:
        """Aggregate OHLC field over date range.

        Args:
            product_name: product name (partial match)
            start, end: date range (inclusive)
            field: open | high | low | close
            aggregation: max | min | avg
        """
        if not product_name or field not in ("open", "high", "low", "close"):
            return []
        if aggregation not in ("max", "min", "avg"):
            aggregation = "max"

        field_col = getattr(PriceOHLC, field)
        agg_func = {
            "max": func.max(field_col),
            "min": func.min(field_col),
            "avg": func.avg(field_col),
        }[aggregation]

        # Subquery: find best aggregation per product
        products_subq = (
            self.db.query(Product)
            .filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{product_name.strip()}%"),
            )
            .limit(limit * 2)
            .subquery()
        )

        # For each matching product, compute aggregation
        product_ids = [p.id for p in self.db.query(products_subq.c.id).all()]

        results: list[PriceResult] = []
        for pid in product_ids:
            product = self.db.query(Product).get(pid)
            if not product:
                continue

            agg_value = (
                self.db.query(agg_func)
                .filter(
                    PriceOHLC.product_id == pid,
                    PriceOHLC.trade_date >= start,
                    PriceOHLC.trade_date <= end,
                )
                .scalar()
            )
            if agg_value is None:
                continue

            # Find the trade_date where the aggregation was achieved
            if aggregation == "max":
                ohlc = (
                    self.db.query(PriceOHLC)
                    .filter(
                        PriceOHLC.product_id == pid,
                        PriceOHLC.trade_date >= start,
                        PriceOHLC.trade_date <= end,
                        field_col == agg_value,
                    )
                    .order_by(PriceOHLC.trade_date.desc())
                    .first()
                )
            elif aggregation == "min":
                ohlc = (
                    self.db.query(PriceOHLC)
                    .filter(
                        PriceOHLC.product_id == pid,
                        PriceOHLC.trade_date >= start,
                        PriceOHLC.trade_date <= end,
                        field_col == agg_value,
                    )
                    .order_by(PriceOHLC.trade_date.asc())
                    .first()
                )
            else:  # avg
                # For avg, just pick any date in range
                ohlc = (
                    self.db.query(PriceOHLC)
                    .filter(
                        PriceOHLC.product_id == pid,
                        PriceOHLC.trade_date >= start,
                        PriceOHLC.trade_date <= end,
                    )
                    .order_by(PriceOHLC.trade_date.desc())
                    .first()
                )

            if not ohlc:
                continue

            results.append(
                make_price_result(
                    product_name=product.name,
                    price=Decimal(str(agg_value)),
                    currency=ohlc.currency,
                    unit=product.unit,
                    source="postgres_ohlc",
                    source_detail=f"{product.sku or str(product.id)} | {aggregation.upper()} {field} {start}..{end}",
                    price_date=ohlc.trade_date,
                    field_type=field,
                    attributes={
                        **(product.attributes or {}),
                        "aggregation": aggregation,
                        "date_range": f"{start.isoformat()}..{end.isoformat()}",
                    },
                    relevance_score=self._name_relevance(product_name, product.name),
                )
            )

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # â”€â”€ 4a. Lowest price by name (catalog + low) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get_lowest_by_name(
        self, name: str, category: str | None = None, limit: int = 5
    ) -> list[PriceResult]:
        """Return top N cheapest products matching name (across all matches).

        For each matching product, finds the minimum price across all dates.
        Sorts by price ASC so the cheapest product comes first.
        """
        if not name or len(name.strip()) < 2:
            return []

        strategies = self._build_name_strategies(name)
        seen_product_ids: set = set()
        products: list = []

        for strategy_name in strategies:
            query = self.db.query(Product).filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{strategy_name}%"),
            )
            if category:
                query = query.filter(Product.category == category)
            for p in query.limit(limit * 2).all():
                if p.id not in seen_product_ids:
                    seen_product_ids.add(p.id)
                    products.append(p)
            if len(products) >= limit:
                break

        results: list[PriceResult] = []
        for p in products:
            min_price = p.min_price()
            if min_price:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=min_price.to_decimal(),
                        currency=min_price.currency,
                        unit=p.unit,
                        source="postgres",
                        source_detail=p.sku or str(p.id),
                        price_date=min_price.price_date,
                        field_type="low",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(name, p.name),
                    )
                )
            else:
                ohlc_min = p.min_ohlc_low()
                if ohlc_min is not None:
                    results.append(
                        make_price_result(
                            product_name=p.name,
                            price=ohlc_min,
                            currency="IDR",
                            unit=p.unit,
                            source="postgres_ohlc",
                            source_detail=p.sku or str(p.id),
                            price_date=p.min_ohlc_low_date(),
                            field_type="low",
                            attributes=p.attributes or {},
                            relevance_score=self._name_relevance(name, p.name),
                        )
                    )

        results.sort(key=lambda r: (r.price, r.relevance_score))
        return results[:limit]

    # â”€â”€ 4b. Lowest price by date (timeseries + low) â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def get_lowest_by_date(
        self,
        product_name: str,
        target_date: date,
        limit: int = 5,
    ) -> list[PriceResult]:
        """Return cheapest price across matching products on exact date.

        For products with ProductPrice on that date, uses that price.
        For OHLC products, uses the `low` field on that date.
        Sorts by price ASC.
        """
        if not product_name:
            return []

        products = (
            self.db.query(Product)
            .filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{product_name.strip()}%"),
            )
            .limit(limit * 2)
            .all()
        )

        results: list[PriceResult] = []
        for p in products:
            price_row = p.price_on_date(target_date)
            if price_row:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=price_row.to_decimal(),
                        currency=price_row.currency,
                        unit=p.unit,
                        source="postgres",
                        source_detail=p.sku or str(p.id),
                        price_date=price_row.price_date,
                        field_type="low",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(product_name, p.name),
                    )
                )
                continue

            ohlc = p.ohlc_on_date(target_date)
            if ohlc and ohlc.low is not None:
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=ohlc.get_field("low"),
                        currency=ohlc.currency,
                        unit=p.unit,
                        source="postgres_ohlc",
                        source_detail=p.sku or str(p.id),
                        price_date=ohlc.trade_date,
                        field_type="low",
                        attributes=p.attributes or {},
                        relevance_score=self._name_relevance(product_name, p.name),
                    )
                )

        results.sort(key=lambda r: (r.price, r.relevance_score))
        return results[:limit]

    # â”€â”€ 4c. Lowest OHLC recent (for "hari ini"/"saat ini") â”€â”€

    def get_lowest_ohlc_recent(
        self, name: str, days: int = 30, limit: int = 5
    ) -> list[PriceResult]:
        """Return min of OHLC.low over the last N days (for 'today' fallback).

        When a user asks "harga terendah X hari ini" and today's data
        isn't in the DB, look back over the last 30 days for the lowest.
        """
        if not name or not name.strip():
            return []

        today = date.today()
        cutoff = today - timedelta(days=days)

        products = (
            self.db.query(Product)
            .filter(
                Product.is_active == True,  # noqa: E712
                Product.name.ilike(f"%{name.strip()}%"),
            )
            .limit(limit * 2)
            .all()
        )

        results: list[PriceResult] = []
        for p in products:
            low_value = (
                self.db.query(func.min(PriceOHLC.low))
                .filter(
                    PriceOHLC.product_id == p.id,
                    PriceOHLC.trade_date >= cutoff,
                    PriceOHLC.trade_date <= today,
                )
                .scalar()
            )
            if low_value is not None:
                low_decimal = Decimal(str(low_value))
                ohlc_row = (
                    self.db.query(PriceOHLC)
                    .filter(
                        PriceOHLC.product_id == p.id,
                        PriceOHLC.trade_date >= cutoff,
                        PriceOHLC.trade_date <= today,
                        PriceOHLC.low == low_value,
                    )
                    .order_by(PriceOHLC.trade_date.desc())
                    .first()
                )
                results.append(
                    make_price_result(
                        product_name=p.name,
                        price=low_decimal,
                        currency=ohlc_row.currency if ohlc_row else "IDR",
                        unit=p.unit,
                        source="postgres_ohlc",
                        source_detail=f"{p.sku or str(p.id)} | MIN low last {days}d",
                        price_date=ohlc_row.trade_date if ohlc_row else None,
                        field_type="low",
                        attributes={
                            **(p.attributes or {}),
                            "recent_days": days,
                        },
                        relevance_score=self._name_relevance(name, p.name),
                    )
                )

        results.sort(key=lambda r: (r.price, r.relevance_score))
        return results[:limit]

    # â”€â”€ 4. Multi-criteria filter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def lookup_multi_criteria(
        self,
        name: str | None = None,
        category: str | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        attribute_filters: dict[str, Any] | None = None,
        limit: int = 10,
    ) -> list[PriceResult]:
        query = self.db.query(Product).filter(Product.is_active == True)  # noqa: E712

        if name:
            query = query.filter(Product.name.ilike(f"%{name.strip()}%"))
        if category:
            query = query.filter(Product.category == category)

        products = query.limit(limit * 3).all()
        results: list[PriceResult] = []

        for p in products:
            latest = p.latest_price()
            latest_ohlc = p.latest_ohlc()
            price_dec: Decimal | None = None
            price_date: date | None = None
            field_t = ""
            if latest:
                price_dec = latest.to_decimal()
                price_date = latest.price_date
                field_t = "latest"
            elif latest_ohlc and latest_ohlc.close is not None:
                price_dec = Decimal(str(latest_ohlc.close))
                price_date = latest_ohlc.trade_date
                field_t = "close"
            if price_dec is None:
                continue
            if min_price is not None and price_dec < min_price:
                continue
            if max_price is not None and price_dec > max_price:
                continue
            if attribute_filters:
                attrs = p.attributes or {}
                if not all(attrs.get(k) == v for k, v in attribute_filters.items()):
                    continue
            results.append(
                make_price_result(
                    product_name=p.name,
                    price=price_dec,
                    currency=latest.currency if latest else latest_ohlc.currency,
                    unit=p.unit,
                    source="postgres" if latest else "postgres_ohlc",
                    source_detail=p.sku or str(p.id),
                    price_date=price_date,
                    field_type=field_t,
                    attributes=p.attributes or {},
                    relevance_score=self._name_relevance(name or "", p.name),
                )
            )
        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # â”€â”€ 5. File-system fallback (CSV/XLSX) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def search_from_files(
        self, query: str, max_files: int = 5
    ) -> list[PriceResult]:
        """Scan CSV/XLSX files in /data for matching rows."""
        if not os.path.isdir(self.data_dir):
            return []

        files = self._list_tabular_files()[:max_files]
        results: list[PriceResult] = []
        q_lower = query.lower()
        keywords = [w for w in re.split(r"\s+", q_lower) if len(w) > 2]

        for file_path in files:
            try:
                if file_path.suffix.lower() == ".csv":
                    df = pd.read_csv(file_path, encoding="utf-8", low_memory=False)
                elif file_path.suffix.lower() == ".xlsx":
                    df = pd.read_excel(file_path, sheet_name=0)
                else:
                    continue
                df = df.fillna("")
                price_col = self._find_price_column(df.columns)
                if not price_col:
                    continue
                name_col = self._find_name_column(df.columns)

                scored_rows = []
                for _, row in df.iterrows():
                    row_text = " ".join(str(v) for v in row.values).lower()
                    overlap = sum(1 for k in keywords if k in row_text)
                    if overlap == 0:
                        continue
                    scored_rows.append((overlap, row))

                scored_rows.sort(key=lambda x: x[0], reverse=True)
                for overlap, row in scored_rows[:3]:
                    try:
                        price_raw = row[price_col]
                        price_dec = self._coerce_decimal(price_raw)
                        if price_dec is None or price_dec <= 0:
                            continue
                        results.append(
                            make_price_result(
                                product_name=str(row[name_col]) if name_col else Path(file_path).stem,
                                price=price_dec,
                                currency="IDR",
                                unit=None,
                                source="csv" if file_path.suffix == ".csv" else "xlsx",
                                source_detail=file_path.name,
                                price_date=None,
                                field_type="latest",
                                attributes={},
                                relevance_score=float(overlap),
                            )
                        )
                    except Exception as e:
                        logger.debug("Row skipped in %s: %s", file_path.name, e)
                        continue
            except Exception as e:
                logger.warning("File scan failed for %s: %s", file_path.name, str(e)[:120])
                continue

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results

    # â”€â”€ Helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _list_tabular_files(self) -> list[Path]:
        if not os.path.isdir(self.data_dir):
            return []
        out: list[Path] = []
        for entry in os.listdir(self.data_dir):
            path = Path(self.data_dir) / entry
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in (".csv", ".xlsx"):
                continue
            if path.stat().st_size < 100 or path.stat().st_size > 50 * 1024 * 1024:
                continue
            out.append(path)
        return out

    @staticmethod
    def _find_price_column(columns) -> str | None:
        candidates = ("price", "harga", "biaya", "tarif", "cost", "amount", "nilai")
        for col in columns:
            col_l = str(col).strip().lower()
            if col_l in candidates:
                return col
        for col in columns:
            col_l = str(col).strip().lower()
            if any(c in col_l for c in candidates):
                return col
        return None

    @staticmethod
    def _find_name_column(columns) -> str | None:
        candidates = ("name", "nama", "product", "produk", "item", "barang", "judul")
        for col in columns:
            col_l = str(col).strip().lower()
            if col_l in candidates:
                return col
        for col in columns:
            col_l = str(col).strip().lower()
            if any(c in col_l for c in candidates):
                return col
        return None

    @staticmethod
    def _coerce_decimal(value: Any) -> Decimal | None:
        if value is None or value == "":
            return None
        try:
            if isinstance(value, (int, float, Decimal)):
                return Decimal(str(value))
            s = str(value).strip()
            s = re.sub(r"(rp|rupiah|idr|usd|\$|€|eur)", "", s, flags=re.IGNORECASE).strip()
            if "," in s and "." in s:
                if s.rfind(",") > s.rfind("."):
                    s = s.replace(".", "").replace(",", ".")
                else:
                    s = s.replace(",", "")
            elif "," in s:
                parts = s.split(",")
                if len(parts) == 2 and len(parts[1]) == 3:
                    s = s.replace(",", "")
                else:
                    s = s.replace(",", ".")
            else:
                parts = s.split(".")
                if len(parts) >= 2 and all(len(p) == 3 for p in parts[1:]) and parts[0].isdigit():
                    s = s.replace(".", "")
            if not s or not re.match(r"^-?\d+(\.\d+)?$", s):
                return None
            return Decimal(s)
        except Exception:
            return None

    @staticmethod
    def _name_relevance(query: str, target: str) -> float:
        q = set(re.findall(r"\w+", query.lower()))
        t = set(re.findall(r"\w+", target.lower()))
        if not q or not t:
            return 0.0
        return len(q & t) / max(len(q), 1)


# Common product-name synonyms (Indonesian short form -> catalog form)
# Used to bridge user query vocabulary with product catalog names.
PRODUCT_NAME_SYNONYMS: dict[str, str] = {
    "ac": "AIR COOLER",
    "kulkas": "LEMARI ES",
    "tv": "LED",
}


def _expand_synonyms(name: str) -> str | None:
    """Replace the first matched synonym token in `name` with its expansion.

    Example: "berapa harga AC Sharp" -> "berapa harga AIR COOLER Sharp"
    Only the first match is expanded (to avoid runaway expansions).
    """
    if not name:
        return None
    words = name.split()
    for i, w in enumerate(words):
        key = re.sub(r"\W+", "", w).lower()
        if key in PRODUCT_NAME_SYNONYMS:
            words[i] = PRODUCT_NAME_SYNONYMS[key]
            return " ".join(words)
    return None

