"""Answerability Gate — determines whether evidence is sufficient to answer a query.

Returns a structured decision with confidence level:
  - high   : multiple chunks, high scores, clear answer
  - medium : some evidence but might be incomplete
  - low    : weak evidence, borderline
  - abstain: no evidence or clearly out of scope
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.config import SIMILARITY_THRESHOLD

logger = logging.getLogger("chatbot")

# Minimum score to consider a chunk "strong"
STRONG_SCORE = 0.50
# Minimum number of relevant chunks for medium confidence
MIN_CHUNKS_MEDIUM = 2
# Maximum score of retrieved chunks below which we abstain
ABSTAIN_MAX_SCORE = 0.30


@dataclass
class AnswerabilityResult:
    can_answer: bool
    confidence: str  # high | medium | low | abstain
    reason: str


def evaluate(
    chunks: list[dict],
    original_query: str,
    has_tabular_fact: bool = False,
) -> AnswerabilityResult:
    """Evaluate whether the retrieved evidence is sufficient to answer the query."""

    # ── Rule 0: structured extractor found exact fact ──
    if has_tabular_fact:
        return AnswerabilityResult(
            can_answer=True, confidence="high", reason="structured fact extracted"
        )

    # ── Rule 1: no candidates at all ──
    if not chunks:
        return AnswerabilityResult(
            can_answer=False,
            confidence="abstain",
            reason="Tidak ada dokumen relevan ditemukan dalam knowledge base.",
        )

    # ── Rule 2: all scores below abstain threshold ──
    scores = [c.get("score", 0) for c in chunks]
    max_score = max(scores) if scores else 0

    if max_score < ABSTAIN_MAX_SCORE:
        return AnswerabilityResult(
            can_answer=False,
            confidence="abstain",
            reason="Skor relevansi terlalu rendah — kemungkinan di luar konteks dokumen.",
        )

    # ── Rule 3: top score below SIMILARITY_THRESHOLD ──
    if max_score < SIMILARITY_THRESHOLD:
        return AnswerabilityResult(
            can_answer=False,
            confidence="abstain",
            reason="Tidak ditemukan potongan dokumen dengan relevansi cukup.",
        )

    # ── Rule 4: only one weak chunk ──
    if len(chunks) == 1 and max_score < STRONG_SCORE:
        return AnswerabilityResult(
            can_answer=True,
            confidence="low",
            reason="Hanya satu potongan relevan dengan skor rendah.",
        )

    # ── Rule 5: multiple strong chunks → high confidence ──
    strong_chunks = [c for c in chunks if c.get("score", 0) >= STRONG_SCORE]
    if len(strong_chunks) >= MIN_CHUNKS_MEDIUM and max_score >= STRONG_SCORE:
        return AnswerabilityResult(
            can_answer=True,
            confidence="high",
            reason=f"{len(strong_chunks)} potongan relevan dengan skor tinggi.",
        )

    # ── Rule 6: medium confidence (some evidence) ──
    if len(chunks) >= MIN_CHUNKS_MEDIUM:
        return AnswerabilityResult(
            can_answer=True,
            confidence="medium",
            reason=f"{len(chunks)} potongan relevan tersedia.",
        )

    # ── Rule 7: borderline ──
    return AnswerabilityResult(
        can_answer=True,
        confidence="low",
        reason="Evidence terbatas — jawaban mungkin kurang lengkap.",
    )


# ── User-facing messages ──────────────────────────────────

ABSTAIN_MESSAGE = (
    "Maaf, saya belum menemukan informasi yang cukup dalam knowledge base internal "
    "untuk menjawab pertanyaan tersebut. Silakan unggah dokumen terkait atau perjelas pertanyaan Anda."
)

CLARIFY_MESSAGE = (
    "Maaf, pertanyaan Anda agak ambigu. "
    "Bisakah Anda memberikan detail lebih spesifik tentang apa yang ingin diketahui?"
)
