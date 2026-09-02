"""app/core/security.py - pure functions, so the purest tests in the suite.

No database, no app, no client. If these are slow it is only because argon2 is
deliberately slow, which is the one case where slow is the feature.
"""

from __future__ import annotations

import datetime as dt
import uuid

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import InvalidToken
from app.core.security import (
    create_token_pair,
    decode_token,
    dummy_verify,
    hash_password,
    subject_from_claims,
    verify_password,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- passwords


def test_hash_is_not_the_password():
    hashed = hash_password("correct horse battery staple")
    assert "correct horse" not in hashed
    assert hashed.startswith("$argon2")


def test_same_password_hashes_differently_every_time():
    """Random salt per hash. Two users with the same password must not have
    the same row value - otherwise one cracked hash reveals both."""
    a = hash_password("Password123!")
    b = hash_password("Password123!")
    assert a != b
    assert verify_password("Password123!", a)
    assert verify_password("Password123!", b)


@pytest.mark.parametrize(
    ("attempt", "expected"),
    [
        ("Password123!", True),
        ("password123!", False),  # case matters
        ("Password123", False),  # one character short
        ("", False),
        (" Password123!", False),  # no accidental stripping
    ],
)
def test_verify_password(attempt: str, expected: bool):
    """One test function, five cases, five separate PASS/FAIL lines.

    Parametrize instead of five asserts in one test: when case 3 breaks you
    want the report to say which one, not just "test_verify_password failed".
    """
    stored = hash_password("Password123!")
    assert verify_password(attempt, stored) is expected


@pytest.mark.parametrize("stored", [None, "", "not-a-real-hash", "$argon2id$broken"])
def test_verify_password_survives_a_bad_stored_value(stored: str | None):
    """Rows created before auth existed have hashed_password = NULL, and a
    corrupted value should read as "wrong password", never as a 500."""
    assert verify_password("anything", stored) is False


def test_dummy_verify_does_not_raise():
    """Called on the unknown-email path so timing does not reveal which emails
    are registered. It only has to not explode."""
    dummy_verify()


# ------------------------------------------------------------------- tokens


def test_token_pair_carries_subject_and_version():
    public_id = uuid.uuid4()
    pair = create_token_pair(public_id, token_version=3)

    claims = decode_token(pair.access_token, "access")
    assert claims["sub"] == str(public_id)
    assert claims["typ"] == "access"
    assert claims["ver"] == 3
    assert pair.expires_in == get_settings().access_token_expire_minutes * 60


def test_access_and_refresh_tokens_are_different_strings():
    pair = create_token_pair(uuid.uuid4(), token_version=0)
    assert pair.access_token != pair.refresh_token


def test_refresh_token_is_rejected_where_an_access_token_is_expected():
    """The `typ` claim is the guard. Without it a leaked long-lived refresh
    token would work on every protected route."""
    pair = create_token_pair(uuid.uuid4(), token_version=0)

    with pytest.raises(InvalidToken):
        decode_token(pair.refresh_token, "access")


def test_expired_token_is_rejected():
    """Sign a token by hand with an exp in the past - no waiting, no clock
    mocking, and it exercises the same jwt.decode path as a real one."""
    settings = get_settings()
    past = dt.datetime.now(dt.UTC) - dt.timedelta(hours=1)
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "ver": 0,
            "iat": past,
            "exp": past + dt.timedelta(minutes=1),
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )

    with pytest.raises(InvalidToken) as err:
        decode_token(token, "access")
    assert "expired" in str(err.value).lower()


def test_token_signed_with_another_secret_is_rejected():
    """The signature check in one line. If this ever passes, anyone can mint a
    token for any user."""
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "ver": 0,
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        },
        "an-attacker-chosen-secret-that-is-long-enough",
        algorithm="HS256",
    )

    with pytest.raises(InvalidToken):
        decode_token(token, "access")


def test_unsigned_alg_none_token_is_rejected():
    """The classic JWT attack: re-send the token with alg "none" and no
    signature. decode_token passes an explicit algorithms list, which is what
    stops it."""
    token = jwt.encode(
        {
            "sub": str(uuid.uuid4()),
            "typ": "access",
            "ver": 0,
            "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )

    with pytest.raises(InvalidToken):
        decode_token(token, "access")


@pytest.mark.parametrize("missing", ["sub", "typ", "ver", "exp"])
def test_token_missing_a_required_claim_is_rejected(missing: str):
    settings = get_settings()
    claims = {
        "sub": str(uuid.uuid4()),
        "typ": "access",
        "ver": 0,
        "exp": dt.datetime.now(dt.UTC) + dt.timedelta(minutes=5),
    }
    claims.pop(missing)
    token = jwt.encode(claims, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    with pytest.raises(InvalidToken):
        decode_token(token, "access")


def test_tampered_payload_is_rejected():
    """Flip a character in the payload segment; the signature no longer matches."""
    pair = create_token_pair(uuid.uuid4(), token_version=0)
    header, payload, signature = pair.access_token.split(".")
    broken = f"{header}.{payload[:-2]}XY.{signature}"

    with pytest.raises(InvalidToken):
        decode_token(broken, "access")


@pytest.mark.parametrize(
    "claims",
    [
        {},  # no sub at all
        {"sub": "not-a-uuid"},
        {"sub": None},
    ],
)
def test_subject_from_claims_rejects_anything_that_is_not_a_uuid(claims: dict):
    """Note a small gap found while writing this: {"sub": 12345} raises
    AttributeError, not InvalidToken, because subject_from_claims catches
    (KeyError, ValueError, TypeError) and uuid.UUID(int_value) raises
    AttributeError. Harmless today - only this codebase signs tokens, and it
    always writes a string - but adding AttributeError to that except clause
    would close it."""
    with pytest.raises(InvalidToken):
        subject_from_claims(claims)


def test_subject_from_claims_returns_a_uuid():
    public_id = uuid.uuid4()
    assert subject_from_claims({"sub": str(public_id)}) == public_id
