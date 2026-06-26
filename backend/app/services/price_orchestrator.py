"""Price query orchestrator.

Extracts the price-query pipeline (4-way parallel search + smart selection +
NL response build + LLM generation) from chat.py router into a testable class.

Ponytail: thin wrapper around existing services. No new logic — just
moves the orchestration from a 240-line function into a class.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.orm import Session

from app.schemas.chat import QueryResponse, Source
from app.services.intent_classifier import detect_price_intent
from app.services.marketplace_scraper import MarketplaceScraper
from app.services.price_service import PriceService, select_top_results
from app.services.response_formatter import (
    PRICE_NL_SYSTEM_PROMPT,
    build_fallback_nl,
    build_llm_context,
    build_nl_response,
)
from app.services.groq_client import generate_response
from app.services.web_filter import (
    enrich_web_with_source_score,
    filter_web_by_context,
    filter_web_by_product_match,
    pick_cheapest_web_results,
    relax_filter,
)

logger = logging.getLogger("chatbot")


class PriceQueryOrchestrator:
    """Orchestrates a price query through the full pipeline.

    Pipeline: detect intent → 4-way parallel search (postgres + file +
    web + marketplace) → strict filtering → smart selection → NL
    response build → LLM generation.
    """

    def __init__(self, db: Session, web_search_fn):
        self.db = db
        self._web_search_fn = web_search_fn
        self._price_service = PriceService(db)
        self._marketplace = MarketplaceScraper(db)

    def run(self, query: str, history: str) -> QueryResponse | None:
        intent = detect_price_intent(query)
        if not intent.is_price_query:
            return None

        logger.info(
            "Price query: type=%s field=%s target='%s' date=%s range=%s..%s agg=%s",
            intent.query_type, intent.field_type, intent.target[:50],
            intent.target_date, intent.date_range_start, intent.date_range_end,
            intent.aggregation,
        )

        internal_results, file_results, web_results, market_prices = self._parallel_search(query, intent)

        all_internal = internal_results + file_results
        web_results = self._filter_web(web_results, intent)

        if not all_internal and not web_results and not market_prices:
            return None

        all_internal, market_prices = select_top_results(
            all_internal, market_prices, max_internal=2, max_market=2,
        )
        if web_results:
            web_results = web_results[:2]

        nl_resp = build_nl_response(
            internal_results=all_internal,
            web_results=web_results,
            intent=intent,
            market_prices=market_prices,
        )
        if not nl_resp.sources:
            return None

        context = build_llm_context(nl_resp, intent)
        reply = self._generate_reply(context, history, query, nl_resp, intent)

        if (all_internal and web_results) or all_internal:
            confidence = "high"
        elif web_results:
            confidence = "medium"
        else:
            confidence = "low"

        sources = self._build_legacy_sources(all_internal, web_results)

        return QueryResponse(
            session_id="",
            reply=reply,
            sources=sources,
            confidence=confidence,
            metadata={
                "nl_sources": [s.to_dict() for s in nl_resp.sources],
                "intent": nl_resp.intent,
                "query_summary": nl_resp.query_summary,
                "market_prices": [m.to_dict() for m in market_prices],
            },
        )

    def _parallel_search(self, query: str, intent) -> tuple[list, list, list, list]:
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_pg = executor.submit(self._postgres_search, intent)
            f_files = executor.submit(self._price_service.search_from_files, query)
            f_web = executor.submit(self._web_search_fn, query)
            f_market = executor.submit(self._marketplace.search_all, intent.target, None)

            try:
                internal_results = f_pg.result(timeout=10) or []
            except Exception as e:
                logger.warning("PriceService postgres failed: %s", str(e)[:120])
                internal_results = []
            try:
                file_results = f_files.result(timeout=10) or []
            except Exception as e:
                logger.warning("PriceService files failed: %s", str(e)[:120])
                file_results = []
            try:
                web_results = f_web.result(timeout=15) or []
            except Exception as e:
                logger.warning("PriceService web failed: %s", str(e)[:120])
                web_results = []
            try:
                market_prices = f_market.result(timeout=20) or []
            except Exception as e:
                logger.warning("Marketplace scraper failed: %s", str(e)[:120])
                market_prices = []

        return internal_results, file_results, web_results, market_prices

    def _postgres_search(self, intent):
        if intent.has_recent_marker:
            return self._price_service.get_lowest_ohlc_recent(intent.target, 30)
        if intent.query_type == "timeseries" and intent.target_date:
            if intent.field_type == "low":
                return self._price_service.get_lowest_by_date(intent.target, intent.target_date)
            if intent.field_type in ("high", "open", "close"):
                return self._price_service.lookup_ohlc_by_date(intent.target, intent.target_date, intent.field_type)
            return self._price_service.lookup_by_date(intent.target, intent.target_date, intent.field_type or "close")
        if intent.field_type == "low" and intent.query_type in ("catalog", ""):
            return self._price_service.get_lowest_by_name(intent.target, intent.category)
        if intent.query_type == "range" and intent.date_range_start and intent.date_range_end:
            return self._price_service.lookup_ohlc_by_range(
                intent.target, intent.date_range_start, intent.date_range_end,
                intent.field_type or "high", intent.aggregation or "max",
            )
        if intent.query_type == "multi_criteria":
            return self._price_service.lookup_multi_criteria(
                name=intent.target or None, category=intent.category,
                min_price=None, max_price=None,
            )
        return self._price_service.lookup_by_name(intent.target, intent.category)

    def _filter_web(self, web_results, intent) -> list:
        if not web_results:
            return []
        if intent.target:
            web_results = filter_web_by_product_match(web_results, intent.target)
        if web_results:
            try:
                filtered = filter_web_by_context(web_results, intent)
                if not filtered:
                    logger.info("Strict web filter empty — using relaxed")
                    filtered = relax_filter(web_results, intent)
                web_results = filtered
            except Exception as e:
                logger.warning("Web filter failed: %s", str(e)[:120])
        if web_results:
            web_results = enrich_web_with_source_score(web_results)
        if web_results and intent.field_type == "low":
            web_results = pick_cheapest_web_results(web_results, intent, top_n=3)
        return web_results

    def _generate_reply(self, context, history, query, nl_resp, intent) -> str:
        try:
            nl_answer = generate_response(
                PRICE_NL_SYSTEM_PROMPT, context=context, history=history, query=query,
            )
        except Exception as e:
            logger.warning("Price LLM generation failed: %s", str(e)[:120])
            nl_answer = ""

        if nl_answer and "tidak ditemukan" not in nl_answer.lower()[:200]:
            reply = nl_answer
        else:
            reply = build_fallback_nl(nl_resp, intent)

        if "dapat berubah" not in reply.lower():
            reply = reply + "\n\n_Catatan: Harga dapat berubah sewaktu-waktu. Selalu verifikasi ke sumber resmi._"
        return reply

    def _build_legacy_sources(self, all_internal, web_results) -> list[Source]:
        sources: list[Source] = []
        seen: set = set()
        for r in all_internal[:5]:
            key = r.source_detail
            if key and key not in seen:
                seen.add(key)
                sources.append(Source(file_name=r.source_detail, source_type="internal"))
        for w in web_results[:3]:
            url = w.get("url", "")
            if url and url not in seen:
                seen.add(url)
                sources.append(Source(source_type="external", url=url, title=w.get("title", "")))
        return sources
