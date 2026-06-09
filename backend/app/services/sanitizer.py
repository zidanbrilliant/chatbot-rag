import logging
import re

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
