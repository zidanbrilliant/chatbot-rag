import logging
import re

from app.services.prompt_guard import detect_injection, strip_injection

logger = logging.getLogger("chatbot")

ID_CARD_PATTERN = re.compile(r"\b\d{16}\b")
PHONE_PATTERN = re.compile(r"(?:\+62|62|0)\s?\d{2,3}[\s-]?\d{3,4}[\s-]?\d{3,5}")
EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
NPWP_PATTERN = re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d{1}-\d{3}\.\d{3}\b")
BANK_ACCOUNT_PATTERN = re.compile(r"\b\d{10,16}\b")

REDACTION_REPLACEMENT = "[REDACTED]"


def detect_pii(text: str) -> list[str]:
    findings = []
    if ID_CARD_PATTERN.search(text):
        findings.append("NIK/KTP")
    if PHONE_PATTERN.search(text):
        findings.append("phone_number")
    if EMAIL_PATTERN.search(text):
        findings.append("email")
    if NPWP_PATTERN.search(text):
        findings.append("NPWP")
    if BANK_ACCOUNT_PATTERN.search(text):
        findings.append("bank_account")
    return findings


def redact_pii(text: str) -> str:
    text = ID_CARD_PATTERN.sub(REDACTION_REPLACEMENT, text)
    text = PHONE_PATTERN.sub(REDACTION_REPLACEMENT, text)
    text = EMAIL_PATTERN.sub(REDACTION_REPLACEMENT, text)
    text = NPWP_PATTERN.sub(REDACTION_REPLACEMENT, text)
    text = BANK_ACCOUNT_PATTERN.sub(REDACTION_REPLACEMENT, text)
    return text


def scan_and_redact(text: str) -> tuple[str, list[str]]:
    findings = detect_pii(text)
    if findings:
        logger.info("PII detected: %s", ", ".join(findings))
        return redact_pii(text), findings
    return text, []


# ── Prompt injection detection + stripping ──────────────


def scan_for_injection(text: str) -> tuple[str, bool]:
    """Scan user input for prompt injection attempts.
    
    Returns (cleaned_text, was_modified).
    If injection detected, the offending parts are stripped/replaced.
    """
    if not text:
        return text, False
    
    result = detect_injection(text)
    cleaned = text
    was_stripped = False
    
    if result.is_injection:
        logger.warning(
            "Prompt injection detected in input: confidence=%.2f category=%s",
            result.confidence, result.category,
        )
        cleaned, was_stripped = strip_injection(text)
    
    return cleaned, was_stripped


# ── Output validation ──────────────────────────────────


OUTPUT_BLOCKED_PATTERNS = [
    # LLM leaked meta-tokens
    (re.compile(r"\[INST\]|\[/INST\]|\[SYS\]|\[/SYS\]"), "leaked_llama_tokens"),
    (re.compile(r"&lt;system&gt;|&lt;sys&gt;"), "leaked_system_tags"),
    # Creative content in a non-creative answer
    (re.compile(r"\b(pantun|puisi|sajak|syair)\b.*\n", re.IGNORECASE), "creative_content"),
    (re.compile(r"\bresep\s+(masakan|makanan|soto|rendang)\b.*\n", re.IGNORECASE), "creative_content"),
    # Refusal to follow instructions (acceptable)
    (re.compile(r"^I\s+(cannot|can't|will not|won't|refuse)\s+", re.IGNORECASE), "refusal"),
    # Excessive markdown (shouldn't happen with strict prompt)
    (re.compile(r"```[a-z]*\n.*?\n```", re.DOTALL), "code_block"),
]


def validate_output_strict(reply: str) -> tuple[str, list[str]]:
    """Validate LLM output for prompt injection artifacts.
    
    Returns (cleaned_reply, violations).
    violations = list of violation types found.
    """
    if not reply:
        return reply, []
    
    violations = []
    cleaned = reply
    
    for pattern, vtype in OUTPUT_BLOCKED_PATTERNS:
        if pattern.search(cleaned):
            if vtype in ("refusal",):
                continue  # acceptable
            violations.append(vtype)
            cleaned = pattern.sub("[FILTERED]", cleaned)
    
    if violations:
        logger.warning(
            "Output validation: %d violations found: %s",
            len(violations), ", ".join(violations),
        )
    
    return cleaned, violations


def sanitize_web_snippet(snippet: str) -> tuple[str, bool]:
    """Sanitize a web snippet for prompt injection attempts.
    
    Returns (cleaned_snippet, was_modified).
    """
    if not snippet:
        return snippet, False
    
    result = detect_injection(snippet)
    if not result.is_injection:
        return snippet, False
    
    cleaned, was_stripped = strip_injection(snippet)
    
    # If too many filters were applied, the snippet is likely unusable
    if cleaned.count("[FILTERED]") > 3:
        logger.info("Web snippet heavily filtered — returning generic placeholder")
        return "[Filtered web content — suspected injection]", True
    
    if was_stripped:
        logger.info("Web snippet sanitized for injection (cat=%s)", result.category)
    
    return cleaned, was_stripped
