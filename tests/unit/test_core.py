from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from resume_matching.core.errors import RateLimitedError, UnauthorizedError
from resume_matching.core.logging import JsonFormatter, RedactingFilter, configure_logging
from resume_matching.core.rate_limit import TokenBucketLimiter
from resume_matching.core.redaction import mask_years, redact_pii
from resume_matching.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from tests.conftest import make_settings


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail jane.doe+cv@example.co.uk now", "mail [EMAIL] now"),
        ("call +234 801 234 5678", "call [PHONE]"),
        ("call (555) 013-2468 today", "call [PHONE] today"),
        ("tel 555-201-7788", "tel [PHONE]"),
        ("see linkedin.com/in/jane-doe-1", "see [PROFILE_URL]"),
        ("Jan 2019 - 2022 at Acme", "Jan 2019 - 2022 at Acme"),
        ("2019-2022", "2019-2022"),
        ("handled 10,000 requests", "handled 10,000 requests"),
    ],
)
def test_redact_pii(text, expected):
    assert redact_pii(text) == expected


def test_mask_years():
    assert mask_years("BSc 2014 - 2018, Python 3") == "BSc   -  , Python 3"


def test_logging_redacts_messages_args_and_extras():
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "user %s", ("a@b.io",), None)
    record.payload = {"contact": "+1 555 123 4567", "list": ["x@y.org"]}
    RedactingFilter().filter(record)
    out = json.loads(JsonFormatter().format(record))
    assert out["message"] == "user [EMAIL]"
    assert out["payload"] == {"contact": "[PHONE]", "list": ["[EMAIL]"]}
    assert "request_id" in out
    configure_logging("INFO", json_logs=False)
    configure_logging("WARNING", json_logs=True)


def test_password_hashing():
    hashed = hash_password("s3cret-password", rounds=4)
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong", hashed)
    assert not verify_password("x" * 100, hashed)
    assert not verify_password("anything", "not-a-hash")
    with pytest.raises(ValueError):
        hash_password("x" * 73, rounds=4)


def test_jwt_roundtrip_and_rejections():
    settings = make_settings()
    token, expires_in = create_access_token("user-1", "admin", settings)
    claims = decode_access_token(token, settings)
    assert claims.user_id == "user-1" and claims.role == "admin" and expires_in == 3600
    secret = settings.jwt_secret.get_secret_value()
    now = datetime.now(UTC)
    base = {"sub": "u", "iss": settings.jwt_issuer, "aud": settings.jwt_audience}
    expired = jwt.encode({**base, "role": "admin", "exp": now - timedelta(minutes=1)}, secret)
    with pytest.raises(UnauthorizedError, match="expired"):
        decode_access_token(expired, settings)
    bad_role = jwt.encode({**base, "role": "root", "exp": now + timedelta(minutes=5)}, secret)
    with pytest.raises(UnauthorizedError, match="role"):
        decode_access_token(bad_role, settings)
    forged = jwt.encode(
        {**base, "role": "admin", "exp": now + timedelta(minutes=5)}, "x" * 40, algorithm="HS256"
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(forged, settings)


def test_settings_validation():
    with pytest.raises(ValueError, match="32"):
        make_settings(jwt_secret="short")
    with pytest.raises(ValueError, match="production"):
        make_settings(
            app_env="production", jwt_secret="dev-only-insecure-secret-change-me-0123456789"
        )
    assert make_settings().is_sqlite


def test_token_bucket_refills_over_time():
    now = [0.0]
    limiter = TokenBucketLimiter(rate_per_minute=60, burst=2, clock=lambda: now[0], max_keys=2)
    assert limiter.try_acquire("a")[0]
    assert limiter.try_acquire("a")[0]
    allowed, retry = limiter.try_acquire("a")
    assert not allowed and retry == pytest.approx(1.0)
    with pytest.raises(RateLimitedError) as exc:
        limiter.check("a")
    assert exc.value.headers["Retry-After"] == "1"
    now[0] = 1.0
    assert limiter.try_acquire("a")[0]
    for key in ("b", "c", "d"):
        limiter.try_acquire(key)
    assert len(limiter._buckets) <= 3
    limiter.reset()
    assert limiter._buckets == {}
