"""Prompt Injection Guard — detects and filters prompt injection attempts.

Used to sanitize user input, web snippets, and KB chunks before they
reach the LLM context. Pattern-based with confidence scoring.

Detection categories:
- instruction_override: "ignore previous instructions", "act as"
- role_impersonation: "you are now a", "system:"
- creative_task: "tulis pantun", "buatkan resep"
- developer_mode: "dan mode", "godmode", "developer mode"
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger("chatbot")


@dataclass
class InjectionResult:
    is_injection: bool
    confidence: float  # 0.0-1.0
    patterns_matched: list[str] = field(default_factory=list)
    category: str = ""

    def __bool__(self) -> bool:
        return self.is_injection


# ── Injection patterns by category ──────────────────────

INSTRUCTION_OVERRIDE_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above|sebelumnya)\s+(instructions?|prompts?|rules?|aturans?|perintah)", re.IGNORECASE),
    re.compile(r"disregard\s+(the\s+)?(rules?|instructions?|system|aturan|perintah)", re.IGNORECASE),
    re.compile(r"abaikan\s+(semua\s+)?(instruksi|perintah|aturan|prompt)\s+(sebelumnya|di\s+atas|yang\s+lalu)", re.IGNORECASE),
    re.compile(r"lupakan\s+(semua\s+)?(instruksi|perintah|aturan)", re.IGNORECASE),
    re.compile(r"jangan\s+ikuti\s+(instruksi|perintah|aturan)", re.IGNORECASE),
    re.compile(r"override\s+(system\s+)?(prompt|instructions?|rules?)", re.IGNORECASE),
    re.compile(r"new\s+(instructions?|rules?|prompt)\s*[:=]", re.IGNORECASE),
    re.compile(r"(instructions?|rules?|prompt)\s*[:=]\s*\n?", re.IGNORECASE),
    re.compile(r"do\s+not\s+(follow|obey|comply)", re.IGNORECASE),
]

ROLE_IMPERSONATION_PATTERNS = [
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+(?!chatbot|assistant|knowledge\s+base)[\w\s]+", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a|an|the)\s+(?!chatbot|assistant|knowledge\s+base)[\w\s]+", re.IGNORECASE),
    re.compile(r"sekarang\s+kamu\s+adalah\s+(?!asisten|chatbot|knowledge\s+base)[\w\s]+", re.IGNORECASE),
    re.compile(r"bersikaplah\s+sebagai\s+[\w\s]+", re.IGNORECASE),
    re.compile(r"^\s*(system|sys)\s*[:>]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"<\s*(system|sys)\s*>", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]", re.IGNORECASE),
    re.compile(r"\[SYS\]|\[/SYS\]", re.IGNORECASE),
    re.compile(r"your\s+system\s+prompt\s+is", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
]

CREATIVE_TASK_PATTERNS = [
    re.compile(r"tulis(?:kan|lah)?\s+(?:sebuah\s+)?(pantun|puisi|sajak|syair)\b", re.IGNORECASE),
    re.compile(r"buat(?:kan|lah)?\s+(?:sebuah\s+)?(pantun|puisi|sajak|syair)\b", re.IGNORECASE),
    re.compile(r"tulis(?:kan|lah)?\s+(?:sebuah\s+)?resep\s+(?:masakan|makanan|kue|soto|rendang|nasi)", re.IGNORECASE),
    re.compile(r"buat(?:kan|lah)?\s+(?:sebuah\s+)?resep\b", re.IGNORECASE),
    re.compile(r"beri(?:kan)?\s+saya\s+(?:sebuah\s+)?resep", re.IGNORECASE),
    re.compile(r"write\s+(?:me\s+)?(?:a\s+)?(poem|song|story|joke|recipe|pantun)", re.IGNORECASE),
    re.compile(r"tell\s+me\s+a\s+(joke|story|riddle)", re.IGNORECASE),
    re.compile(r"compose\s+(a|an)\s+(poem|song)", re.IGNORECASE),
    re.compile(r"generate\s+(a|an)\s+(poem|song|story)", re.IGNORECASE),
    re.compile(r"ceritakan\s+(?:saya\s+)?(?:sebuah\s+)?cerita", re.IGNORECASE),
    re.compile(r"nyanyi(?:kan)?\s+lagu", re.IGNORECASE),
]

DEVELOPER_MODE_PATTERNS = [
    re.compile(r"(?:dan|dev|developer)\s*mode", re.IGNORECASE),
    re.compile(r"god\s*mode", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"unleash(?:ed)?\s*version", re.IGNORECASE),
    re.compile(r"no\s+restrictions?", re.IGNORECASE),
    re.compile(r"bypass\s+(?:the\s+)?(?:content\s+)?filter", re.IGNORECASE),
    re.compile(r"remove\s+(?:all\s+)?(?:safeguards?|limitations?)", re.IGNORECASE),
]

# Combine all categories for full scan
ALL_INJECTION_PATTERNS = (
    INSTRUCTION_OVERRIDE_PATTERNS
    + ROLE_IMPERSONATION_PATTERNS
    + CREATIVE_TASK_PATTERNS
    + DEVELOPER_MODE_PATTERNS
)

# Patterns to strip (replace with placeholder)
STRIP_PATTERNS = [
    (re.compile(r"<\s*(system|sys|instruction|prompt)[^>]*>.*?</\s*(system|sys|instruction|prompt)\s*>", re.IGNORECASE | re.DOTALL), ""),
    (re.compile(r"(ignore|abaikan|lupakan|disregard).*?(instructions?|prompts?|rules?|instruksi|perintah|aturan).*?(?:\.|$)", re.IGNORECASE), "[FILTERED]."),
    (re.compile(r"\[INST\].*?\[/INST\]", re.IGNORECASE), "[FILTERED]"),
    (re.compile(r"\[SYS\].*?\[/SYS\]", re.IGNORECASE), "[FILTERED]"),
]


def detect_injection(text: str) -> InjectionResult:
    """Detect prompt injection in a given text. Returns InjectionResult."""
    if not text or not text.strip():
        return InjectionResult(False, 0.0)

    matched: list[str] = []
    categories: set[str] = set()

    for pat in INSTRUCTION_OVERRIDE_PATTERNS:
        if pat.search(text):
            matched.append("instruction_override")
            categories.add("instruction_override")
            break

    for pat in ROLE_IMPERSONATION_PATTERNS:
        if pat.search(text):
            matched.append("role_impersonation")
            categories.add("role_impersonation")
            break

    for pat in CREATIVE_TASK_PATTERNS:
        if pat.search(text):
            matched.append("creative_task")
            categories.add("creative_task")
            break

    for pat in DEVELOPER_MODE_PATTERNS:
        if pat.search(text):
            matched.append("developer_mode")
            categories.add("developer_mode")
            break

    if not matched:
        return InjectionResult(False, 0.0)

    # Confidence: more categories = higher confidence
    confidence = min(len(categories) * 0.3, 1.0)
    category = ", ".join(sorted(categories))

    logger.info(
        "PromptGuard: injection detected (conf=%.1f, cats=[%s], patterns=%s)",
        confidence, category, matched,
    )
    return InjectionResult(True, confidence, matched, category)


def strip_injection(text: str) -> tuple[str, bool]:
    """Strip injection patterns from text. Returns (cleaned, was_stripped)."""
    if not text:
        return text, False

    stripped = text
    was_stripped = False

    for pat, replacement in STRIP_PATTERNS:
        new_text = pat.sub(replacement, stripped)
        if new_text != stripped:
            was_stripped = True
            stripped = new_text

    if was_stripped:
        logger.info("PromptGuard: stripped injection from text (%d chars -> %d chars)",
                     len(text), len(stripped))

    return stripped, was_stripped
