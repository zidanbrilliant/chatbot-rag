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


def pick_cheapest_web_results(
    web_results: list[dict[str, Any]],
    intent: PriceIntent,
    top_n: int = 3,
) -> list[dict[str, Any]]:
    """For lowest-price queries: keep only the cheapest N web results.

    Each result is expected to have a 'best_price' ExtractedPrice set by
    filter_web_by_context or relax_filter. Results are sorted by best_price.value
    ascending, and only the top N are kept.

    For non-lowest queries: returns all results unchanged.
    """
    if not web_results or intent.field_type != "low":
        return web_results

    # Collect results that have a best_price with a valid value
    priced: list[tuple[float, dict[str, Any]]] = []
    for w in web_results:
        best = w.get("best_price")
        if best is None or not hasattr(best, "value") or best.value <= 0:
            continue
        priced.append((best.value, w))

    if not priced:
        return []

    priced.sort(key=lambda x: x[0])
    cheapest = [w for _, w in priced[:top_n]]

    logger.info(
        "Cheapest web picker: %d -> %d (field=%s)",
        len(web_results), len(cheapest), intent.field_type,
    )
    return cheapest


# ── Strict product matching (NEW) ───────────────────────


import re as _re
from typing import Iterable

# Marketplace domain patterns for source scoring
MARKETPLACE_URL_PATTERNS: dict[str, list[str]] = {
    "tokopedia": [r"tokopedia\.com"],
    "shopee": [r"shopee\.co\.id", r"shopee\.com"],
    "lazada": [r"lazada\.co\.id", r"lazada\.com"],
    "bukalapak": [r"bukalapak\.com"],
    "bhinneka": [r"bhinneka\.com"],
    "blibli": [r"blibli\.com"],
    "brand_store": [
        r"polytron\.co\.id",
        r"sharp(?:indonesia|.*\.com/id)",
        r"lg\.com/id",
        r"samsung\.com/id",
        r"aqua\.co\.id",
        r"mi\.co\.id",
    ],
}


def extract_model_tokens(product_name: str) -> list[str]:
    """Extract probable model numbers from a product name.

    Examples:
        "Polytron PAS 8C28" -> ["PAS 8C28", "8C28", "8C28"]
        "Samsung Galaxy S24" -> ["Galaxy S24", "S24"]
        "LED 24V123"        -> ["24V123"]
        "Sony WH-1000XM4"   -> ["WH-1000XM4", "1000XM4"]

    Tokens are returned in priority order: longest first (more specific).
    """
    if not product_name:
        return []

    candidates: list[str] = []

    # First pass: extract word-level tokens (contain a digit + a letter, OR pure alphanumeric)
    word_tokens = _re.findall(r"\S+", product_name)
    for tok in word_tokens:
        if not _re.search(r"\d", tok):
            continue
        if _re.search(r"[A-Za-z]", tok):
            candidates.append(tok)

    # Second pass: try to capture multi-word model numbers
    # e.g., "PAS 8C28" -> "PAS 8C28" (letter prefix + digit model joined by space)
    # We join adjacent word pairs where the first has letters and the second has digits
    for i in range(len(word_tokens) - 1):
        a, b = word_tokens[i], word_tokens[i + 1]
        if _re.search(r"[A-Za-z]", a) and _re.search(r"\d", b) and not _re.search(r"\d", a):
            joined = f"{a} {b}"
            if _re.search(r"\d", joined) and joined not in candidates:
                candidates.append(joined)

    # Sort longest first (more specific)
    candidates.sort(key=lambda s: -len(s))
    return candidates


def filter_web_by_product_match(
    web_results: list[dict[str, Any]],
    product_name: str,
) -> list[dict[str, Any]]:
    """Keep only web results that mention the product's model number.

    Prevents generic "Polytron speaker" blog results from polluting
    "berapa harga Polytron PAS 8C28" queries.

    Strategy:
    1. Extract model tokens from product_name (e.g., "PAS 8C28", "8C28")
    2. For each web result, check if ANY token appears in title+snippet+url
    3. If at least one token matches (case-insensitive), keep the result
    4. Tag the result with the matched token for downstream use
    """
    if not web_results or not product_name:
        return web_results
    tokens = extract_model_tokens(product_name)
    if not tokens:
        return web_results

    filtered: list[dict[str, Any]] = []
    for w in web_results:
        text = " ".join(
            str(w.get(k, "")) for k in ("title", "snippet", "url")
        ).lower()
        matched = next((t for t in tokens if t.lower() in text), None)
        if not matched:
            continue
        w_enriched = dict(w)
        w_enriched["model_matched"] = matched
        filtered.append(w_enriched)

    logger.info(
        "Strict product match: %d -> %d (tokens=%s, target='%s')",
        len(web_results), len(filtered), tokens[:3], product_name[:40],
    )
    return filtered


def score_web_source(url: str) -> tuple[str, float]:
    """Return (source_subtype, boost) for a web result URL.

    source_subtype examples: 'marketplace:tokopedia', 'brand_store', 'generic_blog'
    boost is a multiplier applied to best_price.confidence.
    """
    if not url:
        return "generic_blog", 0.7
    url_lower = url.lower()
    for subtype, patterns in MARKETPLACE_URL_PATTERNS.items():
        for pat in patterns:
            if _re.search(pat, url_lower):
                if subtype == "brand_store":
                    return "brand_store", 1.2
                return f"marketplace:{subtype}", 1.5
    return "generic_blog", 0.7


def enrich_web_with_source_score(
    web_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add source_subtype and boost to each web result. Mutates in place."""
    for w in web_results:
        url = w.get("url", "")
        subtype, boost = score_web_source(url)
        w["source_subtype"] = subtype
        w["source_boost"] = boost
        # Apply boost to best_price.confidence if available
        best = w.get("best_price")
        if best is not None and hasattr(best, "confidence"):
            best.confidence = min(best.confidence * boost, 1.0)
    # Sort marketplace results to the top
    web_results.sort(
        key=lambda w: (
            0 if w.get("source_subtype", "").startswith("marketplace:") else
            1 if w.get("source_subtype") == "brand_store" else
            2
        )
    )
    return web_results
