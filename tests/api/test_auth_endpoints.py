"""The /api/v1/auth endpoints, through TestClient.

TestClient sends requests straight into the ASGI app in the same process - no
server, no port, no network. Middleware, dependencies, response models and
error handlers all run for real; only the socket is missing.

What these tests are for, given the services already have their own tests:
status codes, request and response SHAPES, and the wiring in between. A rule
can be perfectly implemented in a service and still be attached to the wrong
route, or return 200 where it should return 201, or leak a field.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.db]

PASSWORD = "Password123!"
AUTH = "/api/v1/auth"


# ------------------------------------------------------------------ register


def test_register_returns_201_and_the_new_user(client):
    response = client.post(
        f"{AUTH}/register",
        json={
            "email": "new@example.com",
            "full_name": "New User",
            "phone": "01700000000",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "new@example.com"
    assert body["role"] == "user"
    assert "public_id" in body


def test_register_never_returns_the_password_or_the_hash(client):
    """The response model is the guard. This is the test that stops a future
    refactor from returning the ORM object through a bare `dict`."""
    response = client.post(
        f"{AUTH}/register",
        json={
            "email": "leak@example.com",
            "full_name": "Leak Check",
            "password": PASSWORD,
        },
    )

    raw = response.text
    assert PASSWORD not in raw
    assert "argon2" not in raw
    for forbidden in ("hashed_password", "password", "token_version", "deleted_at"):
        assert forbidden not in response.json()


def test_register_rejects_a_duplicate_email_with_409(client, make_user):
    make_user(email="taken@example.com")

    response = client.post(
        f"{AUTH}/register",
        json={
            "email": "taken@example.com",
            "full_name": "Impostor",
            "password": PASSWORD,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"] == "email_taken"


def test_a_registered_user_can_immediately_log_in(client):
    """Two endpoints, one flow. Neither service test can catch a break in the
    seam between them."""
    client.post(
        f"{AUTH}/register",
        json={
            "email": "flow@example.com",
            "full_name": "Flow",
            "password": PASSWORD,
        },
    )

    response = client.post(
        f"{AUTH}/login", json={"email": "flow@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]


# --------------------------------------------------------------------- login


def test_login_returns_both_tokens_and_an_expiry(client, make_user):
    make_user(email="a@b.com")

    response = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": PASSWORD}
    )

    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("a@b.com", "WrongPassword1"),
        ("nobody@example.com", PASSWORD),
    ],
)
def test_bad_credentials_return_401_with_the_same_message(
    client, make_user, email: str, password: str
):
    """Identical responses for "wrong password" and "no such user". A different
    message would let anyone check which email addresses have accounts."""
    make_user(email="a@b.com")

    response = client.post(f"{AUTH}/login", json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json() == {
        "error": "invalid_credentials",
        "detail": "Incorrect email or password",
    }


def test_a_401_carries_the_www_authenticate_header(client, make_user):
    make_user(email="a@b.com")

    response = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": "nope"}
    )

    assert response.headers["www-authenticate"] == "Bearer"


def test_too_many_failed_logins_return_429(client, make_user):
    """The throttle fixture is set to 3 attempts, so this stays quick. The
    endpoint must also stop answering 401 at that point, or the lockout is
    invisible to the client."""
    make_user(email="brute@example.com")
    payload = {"email": "brute@example.com", "password": "wrong-every-time"}

    for _ in range(3):
        assert client.post(f"{AUTH}/login", json=payload).status_code == 401

    locked = client.post(f"{AUTH}/login", json=payload)

    assert locked.status_code == 429
    assert locked.json()["error"] == "too_many_attempts"


def test_the_lockout_applies_even_to_the_correct_password(client, make_user):
    """Otherwise an attacker who guesses right on attempt 6 still gets in."""
    make_user(email="brute@example.com")
    for _ in range(3):
        client.post(
            f"{AUTH}/login", json={"email": "brute@example.com", "password": "wrong"}
        )

    response = client.post(
        f"{AUTH}/login", json={"email": "brute@example.com", "password": PASSWORD}
    )

    assert response.status_code == 429


def test_one_users_lockout_does_not_affect_another(client, make_user):
    make_user(email="victim@example.com")
    make_user(email="bystander@example.com")
    for _ in range(3):
        client.post(
            f"{AUTH}/login", json={"email": "victim@example.com", "password": "wrong"}
        )

    response = client.post(
        f"{AUTH}/login", json={"email": "bystander@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200


# ------------------------------------------------------------------- refresh


def test_refresh_swaps_a_refresh_token_for_a_new_pair(client, make_user):
    make_user(email="a@b.com")
    tokens = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": PASSWORD}
    ).json()

    response = client.post(
        f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200
    assert response.json()["refresh_token"] != tokens["refresh_token"]  # rotated


def test_an_access_token_is_not_accepted_at_the_refresh_endpoint(client, make_user):
    make_user(email="a@b.com")
    tokens = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": PASSWORD}
    ).json()

    response = client.post(
        f"{AUTH}/refresh", json={"refresh_token": tokens["access_token"]}
    )

    assert response.status_code == 401


def test_refresh_needs_no_authorization_header(client, make_user):
    """On purpose: by the time a client refreshes, its access token has usually
    expired, so the refresh token is the only credential it has left."""
    make_user(email="a@b.com")
    tokens = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": PASSWORD}
    ).json()

    response = client.post(
        f"{AUTH}/refresh", json={"refresh_token": tokens["refresh_token"]}
    )

    assert response.status_code == 200


# ------------------------------------------------------------------------ me


def test_me_returns_the_authenticated_user(client, normal_user, auth_headers):
    response = client.get(f"{AUTH}/me", headers=auth_headers(normal_user))

    assert response.status_code == 200
    assert response.json()["public_id"] == str(normal_user.public_id)


@pytest.mark.parametrize(
    ("headers", "why"),
    [
        ({}, "no header at all"),
        ({"Authorization": "Bearer not-a-token"}, "not a JWT"),
        ({"Authorization": "Basic abc123"}, "wrong scheme"),
        ({"Authorization": "Bearer "}, "empty token"),
    ],
)
def test_me_refuses_anything_that_is_not_a_valid_bearer_token(
    client, headers: dict, why: str
):
    response = client.get(f"{AUTH}/me", headers=headers)

    assert response.status_code == 401, why
    assert response.json()["error"] in {"not_authenticated", "invalid_token"}


# --------------------------------------------------------- change-password


def test_change_password_requires_the_current_one(client, normal_user, auth_headers):
    response = client.post(
        f"{AUTH}/change-password",
        json={"current_password": "wrong", "new_password": "BrandNewPass1!"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 401
    assert response.json()["error"] == "invalid_credentials"


def test_changing_the_password_invalidates_the_old_token(
    client, normal_user, auth_headers
):
    """End to end: change password, then try the token you were using a
    moment ago. This is the behaviour a service test cannot fully prove,
    because it depends on get_current_user reading the row every request."""
    headers = auth_headers(normal_user)

    changed = client.post(
        f"{AUTH}/change-password",
        json={"current_password": PASSWORD, "new_password": "BrandNewPass1!"},
        headers=headers,
    )
    assert changed.status_code == 200

    assert client.get(f"{AUTH}/me", headers=headers).status_code == 401

    # ...and the new password works
    login = client.post(
        f"{AUTH}/login",
        json={"email": normal_user.email, "password": "BrandNewPass1!"},
    )
    assert login.status_code == 200


# ------------------------------------------------------------------- logout


def test_logout_invalidates_every_existing_token(client, normal_user, auth_headers):
    first = auth_headers(normal_user)
    second = auth_headers(normal_user)  # a "second device"

    assert client.post(f"{AUTH}/logout", headers=first).status_code == 200

    assert client.get(f"{AUTH}/me", headers=first).status_code == 401
    assert client.get(f"{AUTH}/me", headers=second).status_code == 401


def test_logout_requires_authentication(client):
    assert client.post(f"{AUTH}/logout").status_code == 401
