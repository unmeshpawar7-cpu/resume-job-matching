"""PII redaction for logs and persisted free text.

Deliberately conservative regexes: emails, phone numbers (international and national
formats with at least 9 digits) and LinkedIn/GitHub profile URLs. Redaction is applied to

* every log record (see :class:`resume_matching.core.logging.RedactingFilter`);
* stored resume text / section text when ``REDACT_ANALYSIS_PAYLOADS=true`` (default);
* evidence snippets shown in API responses;
* text sent to embedding providers.
"""

from __future__ import annotations

import re

EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
# Phone: optional +country, groups of digits separated by space/dot/dash/parentheses,
# 9-15 digits in total. Year ranges ("2019 - 2022") have only 8 digits and are not matched.
PHONE_RE = re.compile(r"(?<![\w+])(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,5}\)?[\s.-]?){2,5}\d{2,5}(?!\w)")
PROFILE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in|github\.com)/[\w-]+/?", re.IGNORECASE
)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _phone_sub(match: re.Match[str]) -> str:
    digits = sum(ch.isdigit() for ch in match.group(0))
    return "[PHONE]" if 9 <= digits <= 15 else match.group(0)


def redact_pii(text: str) -> str:
    """Replace emails, phone numbers and profile URLs with placeholders."""
    if not text:
        return text
    text = EMAIL_RE.sub("[EMAIL]", text)
    text = PROFILE_URL_RE.sub("[PROFILE_URL]", text)
    return PHONE_RE.sub(_phone_sub, text)


def mask_years(text: str) -> str:
    """Remove four-digit years before embedding (graduation years are an age proxy)."""
    return _YEAR_RE.sub(" ", text)
