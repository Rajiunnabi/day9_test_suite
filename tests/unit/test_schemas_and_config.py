"""Schemas and settings - the two places bad input is supposed to stop.

Testing schemas directly, rather than only through the API, means a validation
rule can be checked in one line instead of a full request. The API side still
gets its own tests (tests/api/test_validation.py) to confirm the 422 body
shape, but the rules themselves belong here.
"""

from __future__ import annotations

import datetime as dt
import uuid

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.enums import UserRole
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserOut, UserUpdate

pytestmark = pytest.mark.unit


# ------------------------------------------------------------- UserCreate


def test_a_valid_payload_is_accepted():
    payload = UserCreate(
        email="a@b.com", full_name="Real Name", phone="0123", password="Password123!"
    )
    assert payload.email == "a@b.com"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("email", "missing@tld"),
        ("email", ""),
        ("full_name", ""),
        ("full_name", "   "),  # blank after stripping
        ("full_name", "x" * 121),
        ("password", "short"),  # under the 8-char minimum
        ("password", "x" * 129),  # over the max, so argon2 never sees 10 MB
        ("phone", "x" * 31),
    ],
)
def test_bad_values_are_rejected(field: str, value: str):
    data = {
        "email": "a@b.com",
        "full_name": "Real Name",
        "phone": "0123",
        "password": "Password123!",
    }
    data[field] = value

    with pytest.raises(ValidationError) as err:
        UserCreate(**data)

    assert any(field in str(e["loc"]) for e in err.value.errors())


def test_whitespace_is_stripped_before_the_blank_check():
    """min_length=1 alone would let "   " through - the validator runs after
    the strip, which is why order matters here."""
    payload = UserCreate(
        email="a@b.com", full_name="  Real Name  ", phone=" 0123 ", password="Password1"
    )
    assert payload.full_name == "Real Name"
    assert payload.phone == "0123"


def test_a_client_cannot_send_its_own_role():
    """UserCreate has no `role` field. Pydantic ignores unknown keys by
    default, so the extra key is dropped rather than becoming an admin."""
    payload = UserCreate(
        email="a@b.com",
        full_name="Sneaky",
        password="Password123!",
        role="admin",
    )
    assert not hasattr(payload, "role")


# -------------------------------------------------------------- UserUpdate


def test_exclude_unset_is_what_makes_patch_partial():
    """The single most important line in the PATCH endpoint. Without
    exclude_unset the omitted fields arrive as None and wipe stored values."""
    payload = UserUpdate(full_name="Only This")

    assert payload.model_dump(exclude_unset=True) == {"full_name": "Only This"}
    # ...and for contrast, what would be sent without it:
    assert payload.model_dump() == {
        "email": None,
        "full_name": "Only This",
        "phone": None,
    }


def test_an_explicit_null_is_still_a_change():
    """Sending phone: null means "clear my phone number", and exclude_unset
    keeps that distinct from not sending phone at all."""
    payload = UserUpdate(phone=None)
    assert payload.model_dump(exclude_unset=True) == {"phone": None}


# ------------------------------------------------------------------ UserOut


def test_user_out_cannot_leak_a_password_hash():
    """The response model is the last line of defence: even if a route returns
    the whole ORM object, anything not declared here is dropped."""
    assert "hashed_password" not in UserOut.model_fields
    assert "deleted_at" not in UserOut.model_fields
    assert "id" not in UserOut.model_fields  # internal bigint stays internal
    assert "token_version" not in UserOut.model_fields


def test_user_out_reads_straight_off_an_orm_object():
    """from_attributes=True is what lets a route `return user`."""

    class FakeRow:
        public_id = uuid.uuid4()
        email = "a@b.com"
        full_name = "Real Name"
        phone = None
        role = UserRole.USER
        created_at = dt.datetime.now(dt.UTC)
        updated_at = dt.datetime.now(dt.UTC)
        hashed_password = "$argon2id$secret"  # must not appear in the output

    out = UserOut.model_validate(FakeRow())
    assert "argon2" not in out.model_dump_json()


# --------------------------------------------------------------------- Page


def test_page_envelope_keeps_the_paging_numbers():
    page = Page[UserOut](items=[], total=42, limit=20, offset=20)
    assert page.total == 42 and page.limit == 20 and page.offset == 20


# ----------------------------------------------------------------- Settings


def test_a_short_jwt_secret_stops_the_app_from_starting():
    """Config errors should fail at startup, loudly, not at 3am on the first
    request. This is the test for that promise."""
    with pytest.raises(ValidationError) as err:
        Settings(database_url="postgresql+psycopg://x/y", jwt_secret="too-short")

    assert "at least 32" in str(err.value)


@pytest.mark.parametrize("placeholder", ["changeme", "secret", "your-secret-key"])
def test_the_placeholder_secret_is_rejected(placeholder: str):
    """These are all rejected - though note they are caught by the LENGTH rule,
    not the placeholder rule, because every placeholder in that set is shorter
    than 32 characters. The placeholder branch in Settings can never actually
    run today. Harmless, but worth knowing: it is untestable dead code, and if
    you ever want it to mean something the values need to be 32+ chars long
    (e.g. "replace-me-with-48-random-characters-..." from .env.example)."""
    with pytest.raises(ValidationError):
        Settings(database_url="postgresql+psycopg://x/y", jwt_secret=placeholder)


def test_cors_origins_are_split_and_trimmed():
    settings = Settings(
        database_url="postgresql+psycopg://x/y",
        jwt_secret="a" * 40,
        cors_origins="http://a.com , http://b.com,",
    )
    assert settings.cors_origin_list == ["http://a.com", "http://b.com"]


@pytest.mark.parametrize(
    ("environment", "expected"),
    [("local", False), ("staging", False), ("production", True)],
)
def test_is_production_flag(environment: str, expected: bool):
    settings = Settings(
        database_url="postgresql+psycopg://x/y",
        jwt_secret="a" * 40,
        environment=environment,
    )
    assert settings.is_production is expected


def test_an_unknown_environment_is_rejected():
    with pytest.raises(ValidationError):
        Settings(
            database_url="postgresql+psycopg://x/y",
            jwt_secret="a" * 40,
            environment="prod",  # typo - must not silently mean production
        )
