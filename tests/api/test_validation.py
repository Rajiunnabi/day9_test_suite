"""Validation, from the client's side of the wire.

The rules themselves are tested in tests/unit/test_schemas_and_config.py, in
one line each. What is checked here is different and cannot be checked there:
the STATUS CODE and the BODY SHAPE a client receives when it gets something
wrong. Those are part of your public contract - a frontend parses them - so
they deserve tests of their own.

The shape comes from the RequestValidationError handler in app/api/errors.py:

    {"error": "validation_error",
     "detail": [{"field": "email", "message": "..."}]}

Not FastAPI's default. Which is exactly why it needs a test: a custom handler
is code, and code that nothing calls is code that quietly stops working.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.db]

AUTH = "/api/v1/auth"
USERS = "/api/v1/users"
PASSWORD = "Password123!"

VALID = {
    "email": "valid@example.com",
    "full_name": "Valid Person",
    "phone": "01700000000",
    "password": PASSWORD,
}


def test_a_valid_body_is_accepted(client):
    """The control case. Without it, a test file full of 422s could pass
    against an endpoint that rejects everything."""
    assert client.post(f"{AUTH}/register", json=VALID).status_code == 201


# ------------------------------------------------------------- the 422 shape


def test_the_error_body_names_the_field_that_was_wrong(client):
    response = client.post(f"{AUTH}/register", json={**VALID, "email": "not-an-email"})

    body = response.json()
    assert response.status_code == 422
    assert body["error"] == "validation_error"
    assert body["detail"][0]["field"] == "email"
    assert body["detail"][0]["message"]  # something human-readable


def test_the_field_name_has_the_source_prefix_stripped(client):
    """FastAPI's raw `loc` is ("body", "email"). The handler drops the "body"
    part, so a frontend can match the name straight against its form field."""
    response = client.post(f"{AUTH}/register", json={**VALID, "full_name": ""})

    assert response.json()["detail"][0]["field"] == "full_name"


def test_every_problem_is_reported_at_once_not_one_at_a_time(client):
    """Pydantic collects all the errors before raising. A form can highlight
    three broken fields in one round trip instead of three."""
    response = client.post(
        f"{AUTH}/register",
        json={"email": "nope", "full_name": "", "password": "short"},
    )

    fields = {problem["field"] for problem in response.json()["detail"]}
    assert {"email", "full_name", "password"} <= fields


def test_a_missing_required_field_is_reported_by_name(client):
    payload = {k: v for k, v in VALID.items() if k != "password"}

    response = client.post(f"{AUTH}/register", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "password"


def test_a_completely_empty_body_is_422_and_not_500(client):
    response = client.post(f"{AUTH}/register", json={})

    assert response.status_code == 422


def test_malformed_json_is_422_and_not_500(client):
    """Not a schema problem - the parser fails before Pydantic sees anything.
    It must still come back as a clean 422, not a stack trace."""
    response = client.post(
        f"{AUTH}/register",
        content=b"{not json at all",
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


# ------------------------------------------------- the rules, over the wire


@pytest.mark.parametrize(
    ("field", "value", "why"),
    [
        ("email", "plain-text", "no @"),
        ("email", "@example.com", "no local part"),
        ("email", "a@b", "no dot in the domain"),
        ("full_name", "   ", "blank once stripped"),
        ("full_name", "x" * 121, "over 120 characters"),
        ("password", "shrt", "under 8 characters"),
        ("password", "x" * 129, "over 128 - stops a 10 MB argon2 hash"),
        ("phone", "x" * 31, "over 30 characters"),
    ],
)
def test_bad_field_values_are_rejected(client, field: str, value: str, why: str):
    response = client.post(f"{AUTH}/register", json={**VALID, field: value})

    assert response.status_code == 422, why
    assert any(p["field"] == field for p in response.json()["detail"])


def test_whitespace_is_stripped_before_the_value_is_stored(client):
    response = client.post(
        f"{AUTH}/register",
        json={**VALID, "full_name": "  Padded Name  ", "phone": "  0171  "},
    )

    body = response.json()
    assert body["full_name"] == "Padded Name"
    assert body["phone"] == "0171"


def test_unknown_keys_are_ignored_rather_than_stored(client):
    """Pydantic's default is to drop what it does not know. That is what stops
    `{"role": "admin"}` in a registration body from meaning anything."""
    response = client.post(
        f"{AUTH}/register",
        json={**VALID, "role": "admin", "id": 1, "token_version": 99},
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"


# ------------------------------------------------ validation vs the database


def test_validation_runs_before_the_database_is_touched(
    client, query_counter, make_user
):
    """A 422 should cost nothing. If a malformed request still ran queries,
    anyone could make the database work by sending junk."""
    with query_counter:
        response = client.post(f"{AUTH}/register", json={"email": "nope"})

    assert response.status_code == 422
    assert query_counter.count == 0


def test_a_path_parameter_is_validated_before_the_route_runs(
    client, normal_user, auth_headers
):
    """`public_id: uuid.UUID` in the signature is the whole check."""
    response = client.get(f"{USERS}/not-a-uuid", headers=auth_headers(normal_user))

    assert response.status_code == 422
    assert response.json()["detail"][0]["field"] == "public_id"


def test_a_query_parameter_is_validated_too(client, normal_user, auth_headers):
    """q has min_length=1, so `?q=` is an error rather than a silent
    "search for nothing"."""
    response = client.get(f"{USERS}?q=", headers=auth_headers(normal_user))

    assert response.status_code == 422


# --------------------------------------------------- validation vs authorization


def test_an_anonymous_caller_gets_401_even_with_a_broken_body(client):
    """Order matters. Answering 422 here would tell a stranger something about
    the shape of your API before they proved who they are - and it means the
    body was parsed on an unauthenticated request."""
    response = client.post(
        f"{AUTH}/change-password", json={"nonsense": True}
    )

    assert response.status_code == 401


def test_an_authenticated_caller_with_a_broken_body_gets_422(
    client, normal_user, auth_headers
):
    """The mirror image, which is what makes the test above meaningful."""
    response = client.post(
        f"{AUTH}/change-password",
        json={"nonsense": True},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 422
