import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.config import (
    MAX_HISTORY_TURNS,
    MAX_QUERY_LENGTH,
    SESSION_TIMEOUT_MINUTES,
    SIMILARITY_THRESHOLD,
    TOP_K,
)
from app.database import get_db
from app.models.chat import ChatMessage, ChatSession
from app.schemas.chat import (
    FeedbackRequest,
    FeedbackResponse,
    QueryRequest,
    QueryResponse,
    Source,
)
from app.services.answerability import ABSTAIN_MESSAGE
from app.services.answerability import evaluate as evaluate_answerability
from app.services.audit_log import log_web_search
from app.services.embedding import generate_embedding
from app.services.groq_client import (
    expand_synonyms,
    filter_chunks_safe,
    format_context_with_ids,
    format_hybrid_context,
    generate_response,
    rerank_chunks,
    rewrite_query,
    validate_citations,
)
from app.services.intent_classifier import detect_price_intent
from app.services.marketplace_scraper import MarketplaceScraper
from app.services.price_service import PriceService, select_top_results
from app.services.qdrant_client import multi_source_search
from app.services.response_formatter import (
    PRICE_NL_SYSTEM_PROMPT,
    STRICT_SYSTEM_PROMPT,
    build_fallback_nl,
    build_llm_context,
    build_nl_response,
)
from app.services.sanitizer import (
    scan_and_redact,
    scan_for_injection,
    validate_output_strict,
)
from app.services.search_cache import cache_search_results, get_cached_results
from app.services.search_client import search_web
from app.services.structured_extractor import extract_tabular_fact
from app.services.web_filter import (
    enrich_web_with_source_score,
    filter_web_by_context,
    filter_web_by_product_match,
    pick_cheapest_web_results,
    relax_filter,
    sanitize_all_web_snippets,
)

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

logger = logging.getLogger("chatbot")

from app.services.strict_mode import get_casual_response as _get_casual

SYSTEM_PROMPT = STRICT_SYSTEM_PROMPT  # use strict KB-only prompt everywhere

FALLBACK_MESSAGE = (
    "Maaf, informasi tersebut tidak ditemukan di knowledge base maupun sumber online."
)


def _sanitize(text: str) -> str:
    text = re.sub(r"<[^>]*>", "", text)
    text = text.replace("\x00", "")
    text = re.sub(
        r"[\u200b\u200c\u200d\u200e\u200f\u2060\u2061\u2062\u2063\u2064\u2066\u2067\u2068\u2069\u202a\u202b\u202c\u202d\u202e\u2b0f\ufeff]",
        "",
        text,
    )
    text = re.sub(
        r"(?i)(ignore\s+(all\s+)?(previous|prior)\s+(instructions?|prompt)|"
        r"system\s*:\s*|\[system\]|\[assistant\]|<\|system\|>)",
        "",
        text,
    )

    text = re.sub(r"https?://\S+", "", text)

    # Fullwidth-to-halfwidth normalization — RUF001 intentionally suppressed
    text = text.translate(
        str.maketrans(
            "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ！＂＃＄％＆＇（）＊＋，－．／：；＜＝＞？＠［＼］＾＿｀｛｜｝～",  # noqa: RUF001
            "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~",
        )
    )
    text = re.sub(r"\s+", " ", text)
    return text[:MAX_QUERY_LENGTH].strip()


def get_or_create_session(session_id: str | None, db: Session) -> ChatSession:
    if session_id:
        session = (
            db.query(ChatSession)
            .filter(ChatSession.id == session_id)
            .with_for_update()
            .first()
        )
        if session:
            now = datetime.utcnow()
            if (
                session.updated_at
                and (now - session.updated_at).total_seconds() > SESSION_TIMEOUT_MINUTES * 60
            ):
                db.delete(session)
                db.commit()
                session = ChatSession(id=str(uuid.uuid4()))
                db.add(session)
                db.commit()
            return session
    session = ChatSession(id=str(uuid.uuid4()))
    db.add(session)
    db.commit()
    return session


def get_history(session_id: str, db: Session) -> str:
    turns = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(MAX_HISTORY_TURNS * 2)
        .all()
    )
    turns.reverse()
    lines = []
    for t in turns:
        prefix = "User" if t.role == "user" else "Assistant"
        lines.append(f"{prefix}: {t.content}")
    return "\n".join(lines)


def _search_web_with_cache(query: str) -> list[dict]:
    """Search web with Redis cache. Returns list of dicts with title, url, snippet."""
    cached = get_cached_results(query)
    if cached is not None:
        return cached

    t0 = time.time()
    results = search_web(query)
    latency_ms = int((time.time() - t0) * 1000)

    result_dicts = [
        {"title": r.title, "url": r.url, "snippet": r.snippet, "score": r.score}
        for r in results
    ]

    if result_dicts:
        cache_search_results(query, result_dicts)

    log_web_search(
        query=query,
        provider="duckduckgo",
        results_count=len(result_dicts),
        latency_ms=latency_ms,
    )

    return result_dicts


def _handle_price_query(
    query: str,
    db: Session,
    history: str,
) -> QueryResponse | None:
    """Handle price queries with field/date context awareness.

    Uses:
    - PriceService (Postgres) for catalog/timeseries/range/multi-criteria
    - Web strict filter for context-matched external comparison
    - Grouped response formatter (internal cards + external collapsible)

    Returns QueryResponse if query is a price query, else None.
    """
    intent = detect_price_intent(query)
    if not intent.is_price_query:
        return None

    logger.info(
        "Price query branch: type=%s field=%s target='%s' date=%s range=%s..%s agg=%s",
        intent.query_type, intent.field_type, intent.target[:50],
        intent.target_date, intent.date_range_start, intent.date_range_end,
        intent.aggregation,
    )

    service = PriceService(db)
    marketplace_scraper = MarketplaceScraper(db)

    # Parallel: postgres + file scan + marketplace + web search
    internal_results: list = []
    file_results: list = []
    web_results: list = []
    market_prices: list = []

    with ThreadPoolExecutor(max_workers=4) as executor:
        # Route to appropriate PriceService method based on intent
        if intent.has_recent_marker:
            f_pg = executor.submit(
                service.get_lowest_ohlc_recent, intent.target, 30,
            )
        elif intent.query_type == "timeseries" and intent.target_date:
            if intent.field_type == "low":
                f_pg = executor.submit(
                    service.get_lowest_by_date,
                    intent.target, intent.target_date,
                )
            elif intent.field_type in ("high", "open", "close"):
                f_pg = executor.submit(
                    service.lookup_ohlc_by_date,
                    intent.target, intent.target_date, intent.field_type,
                )
            else:
                f_pg = executor.submit(
                    service.lookup_by_date,
                    intent.target, intent.target_date, intent.field_type or "close",
                )
        elif intent.field_type == "low" and intent.query_type in ("catalog", ""):
            f_pg = executor.submit(
                service.get_lowest_by_name, intent.target, intent.category,
            )
        elif intent.query_type == "range" and intent.date_range_start and intent.date_range_end:
            f_pg = executor.submit(
                service.lookup_ohlc_by_range,
                intent.target,
                intent.date_range_start, intent.date_range_end,
                intent.field_type or "high",
                intent.aggregation or "max",
            )
        elif intent.query_type == "multi_criteria":
            f_pg = executor.submit(
                service.lookup_multi_criteria,
                name=intent.target or None,
                category=intent.category,
                min_price=None,
                max_price=None,
            )
        else:
            f_pg = executor.submit(
                service.lookup_by_name, intent.target, intent.category
            )
        f_files = executor.submit(service.search_from_files, query)
        f_web = executor.submit(_search_web_with_cache, query)
        # Marketplace scraper: searches Tokopedia/Shopee/etc. via DDG site: operator
        f_market = executor.submit(
            marketplace_scraper.search_all, intent.target, None,
        )

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

    all_internal = internal_results + file_results

    # Apply strict product match on web results (filter to same model)
    if web_results and intent.target:
        web_results = filter_web_by_product_match(web_results, intent.target)

    # Apply strict web filter based on intent context
    if web_results:
        try:
            filtered_web = filter_web_by_context(web_results, intent)
            if not filtered_web:
                # Fallback: relax filter to avoid empty results
                logger.info("Strict web filter empty — using relaxed")
                filtered_web = relax_filter(web_results, intent)
            web_results = filtered_web
        except Exception as e:
            logger.warning("Web filter failed: %s", str(e)[:120])

    # Apply marketplace scoring & sort: marketplaces first, brand stores next
    if web_results:
        web_results = enrich_web_with_source_score(web_results)

    # For lowest queries: pick only the cheapest web results
    if web_results and intent.field_type == "low":
        web_results = pick_cheapest_web_results(web_results, intent, top_n=3)

    # Log marketplace hits for debugging
    if market_prices:
        logger.info(
            "Marketplace: %d prices for '%s' (cheapest: %s %.0f)",
            len(market_prices), intent.target,
            market_prices[0].marketplace, market_prices[0].price,
        )

    if not all_internal and not web_results and not market_prices:
        return None

    # Apply smart selection: keep only top results (cheapest + freshest)
    # for focused "best deal" answer. Stale prices are demoted.
    all_internal, market_prices = select_top_results(
        all_internal,
        market_prices,
        max_internal=2,
        max_market=2,
    )

    # Limit web results to top 2 to keep the answer focused
    if web_results:
        web_results = web_results[:2]

    # Build NL response with citation registry (NO markdown table)
    nl_resp = build_nl_response(
        internal_results=all_internal,
        web_results=web_results,
        intent=intent,
        market_prices=market_prices,
    )

    if not nl_resp.sources:
        return None

    # Build LLM context with [N] citation markers
    context = build_llm_context(nl_resp, intent)

    # LLM generates NL answer with inline citations
    try:
        nl_answer = generate_response(
            PRICE_NL_SYSTEM_PROMPT,
            context=context,
            history=history,
            query=query,
        )
    except Exception as e:
        logger.warning("Price LLM generation failed: %s", str(e)[:120])
        nl_answer = ""

    # Build final reply
    if nl_answer and "tidak ditemukan" not in nl_answer.lower()[:200]:
        reply = nl_answer
    else:
        # LLM might have returned abstain — use fallback builder (no hallucination)
        reply = build_fallback_nl(nl_resp, intent)

    # Add disclaimer if not already present
    if "dapat berubah" not in reply.lower():
        reply = reply + "\n\n_Catatan: Harga dapat berubah sewaktu-waktu. Selalu verifikasi ke sumber resmi._"

    # Confidence
    if (all_internal and web_results) or all_internal:
        confidence = "high"
    elif web_results:
        confidence = "medium"
    else:
        confidence = "low"

    # Build minimal sources for backward compat (not used by new NL UI)
    sources: list[Source] = []
    seen: set = set()
    for r in all_internal[:5]:
        key = r.source_detail
        if key and key not in seen:
            seen.add(key)
            sources.append(Source(
                file_name=r.source_detail,
                source_type="internal",
            ))
    for w in web_results[:3]:
        url = w.get("url", "")
        if url and url not in seen:
            seen.add(url)
            sources.append(Source(
                source_type="external",
                url=url,
                title=w.get("title", ""),
            ))

    return QueryResponse(
        session_id="",
        reply=reply,
        sources=sources,
        confidence=confidence,
        metadata={
            # New: source list for inline citation rendering
            "nl_sources": [s.to_dict() for s in nl_resp.sources],
            "intent": nl_resp.intent,
            "query_summary": nl_resp.query_summary,
            "market_prices": [m.to_dict() for m in market_prices],
        },
    )


@router.post("/query", response_model=QueryResponse)
def chat_query(req: QueryRequest, db: Session = Depends(get_db)):
    query = _sanitize(req.query)
    query, _ = scan_and_redact(query)

    # Layer 1: scan for prompt injection in user input
    query, was_injected = scan_for_injection(query)
    if was_injected:
        logger.warning("Injection stripped from query: %s", req.query[:60])

    if not query:
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Silakan ketik pertanyaan yang jelas ya.",
        )

    # Layer 1b: reject creative/suspicious queries outright
    from app.services.prompt_guard import detect_injection
    inject_result = detect_injection(query)
    if inject_result.is_injection and inject_result.confidence >= 0.3:
        logger.warning(
            "Injection rejected: confidence=%.2f cat=%s query=%s",
            inject_result.confidence, inject_result.category, req.query[:60],
        )
        return QueryResponse(
            session_id=req.session_id or "",
            reply="Maaf, saya hanya dapat membantu pertanyaan seputar informasi harga produk, perbandingan harga, dan konten dokumen di knowledge base. Silakan tanyakan hal yang lebih spesifik.",
        )

    session = get_or_create_session(req.session_id, db)
    session.updated_at = datetime.utcnow()
    db.commit()

    db.add(ChatMessage(session_id=session.session_id, role="user", content=query))
    db.commit()

    # Layer 2: handle casual greetings with fixed safe responses
    casual_response = _get_casual(query)
    if casual_response:
        db.add(ChatMessage(session_id=session.session_id, role="assistant", content=casual_response))
        db.commit()
        return QueryResponse(
            session_id=session.session_id, reply=casual_response
        )

    history = get_history(session.session_id, db)

    # ── Price query branch (BEFORE regular RAG) ──
    price_response = _handle_price_query(query, db, history)
    if price_response is not None:
        # Layer 3: validate output for injection artifacts
        clean_reply, violations = validate_output_strict(price_response.reply)
        if violations:
            price_response.reply = clean_reply

        price_response.session_id = session.session_id
        assistant_msg = ChatMessage(
            session_id=session.session_id,
            role="assistant",
            content=price_response.reply,
        )
        db.add(assistant_msg)
        db.commit()
        price_response.message_id = str(assistant_msg.id)
        return price_response

    if len(query.split()) > 10:
        enriched_query = query
    else:
        enriched_query = rewrite_query(query, history)
    enriched_query = expand_synonyms(enriched_query)

    try:
        query_embedding = generate_embedding(enriched_query)
    except Exception:
        query_embedding = None

    if query_embedding is None:
        reply = "Maaf, layanan sedang sibuk. Silakan coba lagi sebentar ya."
        assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
        db.add(assistant_msg)
        db.commit()
        return QueryResponse(
            session_id=session.session_id, reply=reply, message_id=str(assistant_msg.id)
        )

    # ── Parallel: internal search (Qdrant) + web search (DuckDuckGo) ──
    web_results: list[dict] = []
    internal_future = None

    with ThreadPoolExecutor(max_workers=2) as executor:
        internal_future = executor.submit(
            multi_source_search,
            query_vector=query_embedding,
            limit_per_file=4,
            score_threshold=0.3,
            with_vectors=True,
        )
        web_future = executor.submit(_search_web_with_cache, enriched_query)

        try:
            raw_results = internal_future.result(timeout=15)
        except Exception:
            raw_results = []

        try:
            web_results = web_future.result(timeout=15)
        except Exception:
            web_results = []

    if enriched_query != query:
        try:
            original_embedding = generate_embedding(query)
        except Exception:
            original_embedding = None
        if original_embedding is not None:
            orig_results = multi_source_search(
                query_vector=original_embedding,
                limit_per_file=4,
                score_threshold=0.3,
                with_vectors=True,
            )
            if orig_results and (not raw_results or orig_results[0].score > raw_results[0].score):
                raw_results = orig_results
                enriched_query = query

    if not raw_results:
        raw_results = multi_source_search(
            query_vector=query_embedding,
            limit_per_file=3,
            score_threshold=0.0,
            with_vectors=True,
        )
        if raw_results:
            logger.info("Progressive fallback: recovered %d results", len(raw_results))

    chunks = []
    for hit in raw_results:
        p = hit.payload
        if hit.score >= SIMILARITY_THRESHOLD:
            chunks.append(
                {
                    "file_name": p.get("file_name", ""),
                    "content": p.get("content", ""),
                    "page_number": p.get("page_number"),
                    "row_index": p.get("row_index"),
                    "score": hit.score,
                    "_vector": hit.vector if hasattr(hit, "vector") else None,
                }
            )

    if chunks:
        if len(chunks) > 5:
            chunks = rerank_chunks(enriched_query, chunks)
        chunks = [c for c in chunks if c.get("_vector") is not None]
        # Layer: chunk safety filter — remove injection-containing chunks
        chunks = filter_chunks_safe(chunks, enriched_query)

    # Layer: sanitize web snippets for injection patterns
    if web_results:
        web_results = sanitize_all_web_snippets(web_results)

    tabular_fact, tabular_file = extract_tabular_fact(enriched_query)
    if tabular_fact:
        logger.info("Structured fact extracted: %s", tabular_fact[:80])
        chunks.insert(0, {
            "file_name": tabular_file or "",
            "content": tabular_fact,
            "page_number": None,
            "row_index": None,
            "score": 1.0,
            "_vector": True
        })

    # ── Hybrid context: internal chunks + web results ──
    has_content = bool(chunks) or bool(web_results)
    if not has_content:
        assistant_msg = ChatMessage(
            session_id=session.session_id, role="assistant", content=FALLBACK_MESSAGE
        )
        db.add(assistant_msg)
        db.commit()
        return QueryResponse(
            session_id=session.session_id,
            reply=FALLBACK_MESSAGE,
            message_id=str(assistant_msg.id),
            confidence="abstain",
            fallback_triggered=True,
        )

    # Answerability gate (only for internal chunks — web results always pass)
    if chunks:
        gate = evaluate_answerability(chunks, query)
        if not gate.can_answer and not web_results:
            reply = ABSTAIN_MESSAGE
            assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=reply)
            db.add(assistant_msg)
            db.commit()
            return QueryResponse(
                session_id=session.session_id,
                reply=reply,
                message_id=str(assistant_msg.id),
                sources=[],
                confidence=gate.confidence,
                out_of_context=True,
            )
    else:
        from app.services.answerability import AnswerabilityResult
        gate = AnswerabilityResult(can_answer=True, confidence="medium", reason="web-only")

    if web_results:
        context, chunk_mapping = format_hybrid_context(chunks, web_results)
    else:
        context, chunk_mapping = format_context_with_ids(chunks)

    try:
        reply = generate_response(SYSTEM_PROMPT, context, history, enriched_query)
    except Exception:
        reply = "Maaf, layanan AI sedang tidak tersedia. Silakan coba lagi nanti."

    clean_reply, citation_data = validate_citations(reply, chunk_mapping)

    # Layer: strict output validation — strip any injection artifacts from LLM reply
    clean_reply, violations = validate_output_strict(clean_reply)
    if violations:
        logger.warning("Output validation found %d violations in RAG reply", len(violations))

    # Build sources from citations (both internal and external)
    seen_keys = set()
    sources = []
    for cit in citation_data:
        src_type = cit.get("source_type", "internal")
        if src_type == "external":
            url = cit.get("url", "")
            if url and url not in seen_keys:
                seen_keys.add(url)
                sources.append(Source(
                    source_type="external",
                    url=url,
                    title=cit.get("title", ""),
                ))
        else:
            fn = cit.get("file_name", "")
            if fn and fn not in seen_keys:
                seen_keys.add(fn)
                sources.append(Source(
                    file_name=fn,
                    page_number=cit.get("page_number"),
                    row_index=cit.get("row_index"),
                    source_type="internal",
                ))

    if not sources:
        for c in chunks[:TOP_K]:
            fn = c.get("file_name", "")
            if fn and fn not in seen_keys:
                seen_keys.add(fn)
                sources.append(Source(file_name=fn, source_type="internal"))
        for w in web_results[:3]:
            url = w.get("url", "")
            if url and url not in seen_keys:
                seen_keys.add(url)
                sources.append(Source(
                    source_type="external",
                    url=url,
                    title=w.get("title", ""),
                ))

    assistant_msg = ChatMessage(session_id=session.session_id, role="assistant", content=clean_reply)
    db.add(assistant_msg)
    db.commit()

    from uuid import UUID as _UUID

    from app.models.chat import MessageCitation

    for cit in citation_data:
        if cit.get("source_type") == "external":
            continue
        try:
            cid_raw = cit.get("chunk_id")
            did_raw = cit.get("document_id")
            if not cid_raw or not did_raw:
                continue
            chunk_id = _UUID(cid_raw) if isinstance(cid_raw, str) else cid_raw
            doc_id = _UUID(did_raw) if isinstance(did_raw, str) else did_raw
            mc = MessageCitation(
                message_id=assistant_msg.id,
                chunk_id=chunk_id,
                document_id=doc_id,
                quote_start=None,
                quote_end=None,
            )
            db.add(mc)
        except (ValueError, AttributeError, TypeError):
            pass
    db.commit()

    return QueryResponse(
        session_id=session.session_id,
        reply=clean_reply,
        message_id=str(assistant_msg.id),
        sources=sources,
        confidence=gate.confidence,
    )


@router.post("/feedback", response_model=FeedbackResponse)
def chat_feedback(req: FeedbackRequest, db: Session = Depends(get_db)):
    if req.feedback not in ("positive", "negative"):
        raise HTTPException(400, "Feedback harus 'positive' atau 'negative'")

    if not req.message_id or not req.message_id.strip():
        raise HTTPException(400, "message_id tidak boleh kosong")

    msg = db.query(ChatMessage).filter(ChatMessage.id == req.message_id).first()
    if not msg:
        raise HTTPException(404, "Pesan tidak ditemukan")

    msg.feedback = req.feedback
    db.commit()
    return FeedbackResponse(message="Feedback tersimpan")
