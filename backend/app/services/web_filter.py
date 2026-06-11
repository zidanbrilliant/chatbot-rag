"""Web search strict filter — context-matched filtering.

Filters web search results based on intent's field_type and date context.
Only returns results whose extracted prices match the intent context.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services.intent_classifier import PriceIntent
from app.services.price_parser import ExtractedPrice, extract_prices_from_snippet

logger = logging.getLogger("chatbot")


def filter_web_by_context(
    web_results: list[dict[str, Any]],
    intent: PriceIntent,
) -> list[dict[str, Any]]:
    """Strict filter: keep only web results matching intent's field/date.

    Each result is enriched with:
    - context_prices: list of ExtractedPrice matching the context
    - best_price: top ExtractedPrice from context_prices

    Strict mode: if intent.field_type or intent.target_date is set,
    results without matching context are dropped.

    Returns:
        Filtered list (may be empty if no matches).
    """
    if not web_results:
        return []

    target_field = intent.field_type
    target_date = ""
    if intent.target_date:
        target_date = intent.target_date.isoformat()
    elif intent.date_range_start and intent.date_range_end:
        # For range, match any date within range
        target_date = (
            f"{intent.date_range_start.isoformat()}/{intent.date_range_end.isoformat()}"
        )

    filtered: list[dict[str, Any]] = []
    for w in web_results:
        snippet = w.get("snippet", "")
        if not snippet:
            continue

        prices = extract_prices_from_snippet(
            snippet,
            default_currency=intent.currency,
            target_field=target_field,
            target_date=target_date,
        )
        if not prices:
            continue

        # STRICT: filter by field if target_field set
        if target_field:
            matching = [p for p in prices if p.field_type == target_field]
            if not matching:
                # No matching field, drop this result
                continue
            prices = matching

        # STRICT: filter by date if target_date set
        if target_date and "/" not in target_date:
            dated = [p for p in prices if p.date_context == target_date]
            if not dated:
                # No exact date match, drop
                continue
            prices = dated
        elif target_date and "/" in target_date:
            # Range match
            range_start, range_end = target_date.split("/")
            dated = [
                p for p in prices
                if p.date_context and range_start <= p.date_context <= range_end
            ]
            if not dated:
                # No date in range, drop
                continue
            prices = dated

        w_enriched = dict(w)
        w_enriched["context_prices"] = prices
        w_enriched["best_price"] = prices[0]
        filtered.append(w_enriched)

    logger.info(
        "Web strict filter: %d -> %d (field=%s, date=%s)",
        len(web_results), len(filtered), target_field or "any", target_date or "any",
    )
    return filtered


def relax_filter(
    web_results: list[dict[str, Any]],
    intent: PriceIntent,
) -> list[dict[str, Any]]:
    """Fallback: if strict filter returns empty, use loose filter.

    Returns all results, but marks which ones have matching context.
    """
    if not web_results:
        return []

    relaxed: list[dict[str, Any]] = []
    for w in web_results:
        snippet = w.get("snippet", "")
        if not snippet:
            continue
        prices = extract_prices_from_snippet(
            snippet,
            default_currency=intent.currency,
            target_field=intent.field_type,
            target_date=(
                intent.target_date.isoformat() if intent.target_date else ""
            ),
        )
        if not prices:
            continue
        w_enriched = dict(w)
        w_enriched["context_prices"] = prices
        w_enriched["best_price"] = prices[0]
        relaxed.append(w_enriched)
    return relaxed
