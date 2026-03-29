"""Input/output sanitization for persisted run text (strip HTML, PII masking)."""

from __future__ import annotations

import json
import re
from html import unescape
from typing import Any

from arctis.sanitizer.pipeline import run_sanitizer_pipeline
from arctis.sanitizer.policy import SanitizerPolicy

_TAG_RE = re.compile(r"<[^>]+>")
_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)
# Loose phone pattern: optional +, groups of digits/spaces/dashes/parens.
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?)?\d{2,4}[\s.-]?\d{2,4}[\s.-]?\d{2,6}(?!\d)",
)
_CC_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")
_IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{10,30}\b")
_PASSPORT_RE = re.compile(r"\b[A-Z0-9]{6,9}\b")
_SSN_RE = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_VAT_EORI_RE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{8,17}\b")


def strip_html(text: str) -> str:
    """Remove HTML tags and unescape entities."""
    s = _TAG_RE.sub(" ", text)
    return unescape(s)


def mask_emails(text: str) -> str:
    return _EMAIL_RE.sub("[EMAIL_REDACTED]", text)


def mask_phone_numbers(text: str) -> str:
    return _PHONE_RE.sub("[PHONE_REDACTED]", text)


def canonical_json_dumps(obj: Any) -> str:
    """
    Deterministic JSON for persisted run text (sorted keys, stable for audit diffs).

    Use this for **all** governance storage fields derived from structured data.
    """

    return json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str)


def sanitize_text(text: str) -> str:
    """
    Strip HTML, trim whitespace, mask emails and phone-like sequences.
    Order: HTML → emails → phones → normalize spaces.
    """
    s = strip_html(text)
    s = mask_emails(s)
    s = mask_phone_numbers(s)
    s = " ".join(s.split())
    return s.strip()


def sanitize_structured_for_storage(obj: Any) -> str:
    """
    Canonical JSON of ``obj`` then :func:`sanitize_text` — single policy for stored
    effective payloads and output mirrors (PII/HTML stripped in text form).
    """

    return sanitize_text(canonical_json_dumps(obj))


def _digits_only(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _luhn_valid(number: str) -> bool:
    digits = _digits_only(number)
    if len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    parity = len(digits) % 2
    for idx, ch in enumerate(digits):
        d = int(ch)
        if idx % 2 == parity:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def detect_sensitive_patterns(text: str) -> dict[str, list[str]]:
    cc = [m.group(0) for m in _CC_RE.finditer(text) if _luhn_valid(m.group(0))]
    iban = [m.group(0) for m in _IBAN_RE.finditer(text)]
    ssn = [m.group(0) for m in _SSN_RE.finditer(text)]
    vat_eori = [m.group(0) for m in _VAT_EORI_RE.finditer(text)]
    # passport numbers are region-specific; keep strict length and require mixed classes.
    passport: list[str] = []
    for m in _PASSPORT_RE.finditer(text):
        token = m.group(0)
        has_alpha = any(c.isalpha() for c in token)
        has_digit = any(c.isdigit() for c in token)
        if has_alpha and has_digit:
            passport.append(token)
    return {
        "credit_card": cc,
        "iban": iban,
        "passport": passport,
        "ssn": ssn,
        "vat_eori": vat_eori,
    }


def _confidence_for_hits(count: int) -> float:
    if count <= 0:
        return 0.0
    if count == 1:
        return 0.72
    if count == 2:
        return 0.86
    return 0.95


def sanitizer_impact_metadata(text: str) -> dict[str, Any]:
    # Backward-compatible default policy keeps historical mask-first behavior while
    # adding semantic/layer-aware metadata for Sanitizer 3.0.
    result = run_sanitizer_pipeline(text, SanitizerPolicy.default())
    impact = dict(result.impact)
    # Preserve legacy schema version for existing consumers expecting v1.
    impact["schema_version"] = 1
    return impact


def sanitizer_impact_metadata_with_policy(
    text: str,
    policy: SanitizerPolicy,
) -> dict[str, Any]:
    return run_sanitizer_pipeline(text, policy).impact
