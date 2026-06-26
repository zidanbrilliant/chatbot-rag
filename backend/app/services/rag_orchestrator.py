"""RAG orchestrator.

Extracts the post-casual RAG pipeline (rewrite → embed → parallel search →
progressive fallback → answerability gate → context build → LLM generate →
citation validation) from chat.py router into a testable class.

Ponytail: thin wrapper around existing services. No new logic — just
moves the orchestration from a 313-line function into a class.
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID as _UUID

from sqlalchemy.orm import Session

from app.config import SIMILARITY_THRESHOLD, TOP_K
from app.schemas.chat import Source
from app.services.answerability import ABSTAIN_MESSAGE, AnswerabilityResult, evaluate as evaluate_answerability
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
from app.services.qdrant_client import multi_source_search
from app.services.sanitizer import validate_output_strict
from app.services.structured_extractor import extract_tabular_fact
from app.services.web_filter import sanitize_all_web_snippets

logger = logging.getLogger("chatbot")

SYSTEM_PROMPT_FALLBACK = "Maaf, informasi tersebut tidak ditemukan di knowledge base maupun sumber online."


class RagOrchestrator:
    """Orchestrates a regular RAG question through the full pipeline.

    Pipeline: rewrite + synonym expand → embed → parallel Qdrant + web →
    progressive fallback → answerability gate → context build → LLM →
    citation validation → sources.
    """

    def __init__(self, db: Session, web_search_fn, system_prompt: str, user_role: str):
        self.db = db
        self._web_search_fn = web_search_fn
        self._system_prompt = system_prompt
        self._user_role = user_role

    def run(self, query: str, history: str) -> dict:
        """Run the RAG pipeline. Returns dict with keys:
        - reply: str
        - sources: list[Source]
        - confidence: str
        - citation_data: list[dict] (for persistence)
        - out_of_context: bool
        - fallback_triggered: bool
        """
        # Rewrite + synonym expand
        if len(query.split()) > 10:
            enriched_query = query
        else:
            enriched_query = rewrite_query(query, history)
        enriched_query = expand_synonyms(enriched_query)

        # Embed
        try:
            query_embedding = generate_embedding(enriched_query)
        except Exception:
            query_embedding = None
        if query_embedding is None:
            return {
                "reply": "Maaf, layanan sedang sibuk. Silakan coba lagi sebentar ya.",
                "sources": [],
                "confidence": "abstain",
                "citation_data": [],
                "out_of_context": False,
                "fallback_triggered": True,
            }

        # Parallel: Qdrant + web
        raw_results, web_results = self._parallel_search(query_embedding, enriched_query)

        # Progressive fallback: if original query had a rewrite, try original
        if enriched_query != query:
            raw_results = self._try_original_query(query, raw_results, query_embedding, enriched_query)

        # Final fallback: lower threshold
        if not raw_results:
            raw_results = multi_source_search(
                query_vector=query_embedding, limit_per_file=3,
                score_threshold=0.0, with_vectors=True, user_role=self._user_role,
            )
            if raw_results:
                logger.info("Progressive fallback: recovered %d results", len(raw_results))

        # Build chunks from raw_results
        chunks = self._extract_chunks(raw_results, enriched_query)

        # Structured fact injection
        tabular_fact, tabular_file = extract_tabular_fact(enriched_query)
        if tabular_fact:
            logger.info("Structured fact extracted: %s", tabular_fact[:80])
            chunks.insert(0, {
                "file_name": tabular_file or "",
                "content": tabular_fact,
                "page_number": None,
                "row_index": None,
                "score": 1.0,
                "_vector": True,
            })

        # Ponytail: web only SUPPLEMENTS internal. If no internal chunks, drop web.
        # PRD: "Sistem harus menyatakan bahwa informasi tidak ditemukan dalam
        # knowledge base, bukan membuat asumsi."
        if not chunks:
            return {
                "reply": SYSTEM_PROMPT_FALLBACK,
                "sources": [],
                "confidence": "abstain",
                "citation_data": [],
                "out_of_context": True,
                "fallback_triggered": False,
            }

        # Sanitize web snippets (only when internal chunks exist)
        if web_results:
            web_results = sanitize_all_web_snippets(web_results)

        # Answerability gate (internal chunks always present now)
        gate = evaluate_answerability(chunks, query)
        if not gate.can_answer:
            return {
                "reply": ABSTAIN_MESSAGE,
                "sources": [],
                "confidence": gate.confidence,
                "citation_data": [],
                "out_of_context": True,
                "fallback_triggered": False,
            }

        # Build context + LLM
        if web_results:
            context, chunk_mapping = format_hybrid_context(chunks, web_results)
        else:
            context, chunk_mapping = format_context_with_ids(chunks)

        try:
            reply = generate_response(self._system_prompt, context, history, enriched_query)
        except Exception:
            reply = "Maaf, layanan AI sedang tidak tersedia. Silakan coba lagi nanti."

        clean_reply, citation_data = validate_citations(reply, chunk_mapping)
        clean_reply, _ = validate_output_strict(clean_reply)
        sources = self._build_sources(citation_data, chunks, web_results)

        return {
            "reply": clean_reply,
            "sources": sources,
            "confidence": gate.confidence,
            "citation_data": citation_data,
            "out_of_context": False,
            "fallback_triggered": False,
        }

    def _parallel_search(self, query_embedding, enriched_query):
        with ThreadPoolExecutor(max_workers=2) as executor:
            internal_future = executor.submit(
                multi_source_search,
                query_vector=query_embedding, limit_per_file=4,
                score_threshold=0.3, with_vectors=True, user_role=self._user_role,
            )
            web_future = executor.submit(self._web_search_fn, enriched_query)
            try:
                raw_results = internal_future.result(timeout=15)
            except Exception:
                raw_results = []
            try:
                web_results = web_future.result(timeout=15)
            except Exception:
                web_results = []
        return raw_results, web_results

    def _try_original_query(self, query, raw_results, query_embedding, enriched_query):
        try:
            original_embedding = generate_embedding(query)
        except Exception:
            return raw_results
        if original_embedding is None:
            return raw_results
        orig_results = multi_source_search(
            query_vector=original_embedding, limit_per_file=4,
            score_threshold=0.3, with_vectors=True, user_role=self._user_role,
        )
        if orig_results and (not raw_results or orig_results[0].score > raw_results[0].score):
            return orig_results
        return raw_results

    def _extract_chunks(self, raw_results, enriched_query):
        chunks = []
        for hit in raw_results:
            p = hit.payload
            if hit.score >= SIMILARITY_THRESHOLD:
                chunks.append({
                    "file_name": p.get("file_name", ""),
                    "content": p.get("content", ""),
                    "page_number": p.get("page_number"),
                    "row_index": p.get("row_index"),
                    "score": hit.score,
                    "_vector": hit.vector if hasattr(hit, "vector") else None,
                })
        if chunks:
            if len(chunks) > 5:
                chunks = rerank_chunks(enriched_query, chunks)
            chunks = [c for c in chunks if c.get("_vector") is not None]
            chunks = filter_chunks_safe(chunks, enriched_query)
        return chunks

    def _build_sources(self, citation_data, chunks, web_results) -> list[Source]:
        seen_keys: set = set()
        sources: list[Source] = []
        for cit in citation_data:
            src_type = cit.get("source_type", "internal")
            if src_type == "external":
                url = cit.get("url", "")
                if url and url not in seen_keys:
                    seen_keys.add(url)
                    sources.append(Source(source_type="external", url=url, title=cit.get("title", "")))
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
                    sources.append(Source(source_type="external", url=url, title=w.get("title", "")))
        return sources


def persist_message_citations(db: Session, message_id, citation_data: list[dict]) -> None:
    """Persist internal citations to message_citations table.

    Ponytail: extracted from chat.py — single-purpose helper.
    External citations are skipped (they have URLs, not chunk_ids).
    """
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
                message_id=message_id,
                chunk_id=chunk_id,
                document_id=doc_id,
                quote_start=None,
                quote_end=None,
            )
            db.add(mc)
        except (ValueError, AttributeError, TypeError):
            pass
    db.commit()
