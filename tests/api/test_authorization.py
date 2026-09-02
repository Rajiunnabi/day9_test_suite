"""Who is allowed to call what.

Two different questions live here, and mixing them up is the most common
security bug in an API:

    401 - "I don't know who you are"     -> authentication failed
    403 - "I know who you are, and no"   -> authorization failed

The service tests already checked the RULES. These check the WIRING: that the
right dependency is attached to the right route. A missing `admin: AdminUser`
parameter is a one-word mistake that no service test can catch, because the
service is never reached.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.api, pytest.mark.db]

USERS = "/api/v1/users"
AUTH = "/api/v1/auth"
PASSWORD = "Password123!"


# --------------------------------------------------- 401: not authenticated


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", f"{AUTH}/me"),
        ("post", f"{AUTH}/logout"),
        ("post", f"{AUTH}/change-password"),
        ("get", USERS),
        ("post", USERS),
        ("get", f"{USERS}/00000000-0000-0000-0000-000000000000"),
        ("patch", f"{USERS}/00000000-0000-0000-0000-000000000000"),
        ("delete", f"{USERS}/00000000-0000-0000-0000-000000000000"),
        ("post", f"{USERS}/00000000-0000-0000-0000-000000000000/restore"),
        ("patch", f"{USERS}/00000000-0000-0000-0000-000000000000/role"),
    ],
)
def test_every_protected_route_refuses_an_anonymous_caller(
    client, method: str, path: str
):
    """One table, every protected endpoint. Add a route, add a line here.

    It must be 401 and never 422: an unauthenticated caller should not be told
    their body was malformed, because that would mean the body was parsed
    before anyone checked who they were.

    GET and DELETE get no `json=` argument at all. Sending a body on a GET is
    not just untidy - httpx sets Content-Type and Starlette's routing answers
    before the dependency ever runs, so the test would be measuring the wrong
    thing. This mismatch is exactly the kind of bug a parametrized table hides
    until you look at which cases fail.
    """
    kwargs = {"json": {}} if method in {"post", "patch", "put"} else {}
    response = getattr(client, method)(path, **kwargs)

    assert response.status_code == 401
    assert response.json()["error"] in {"not_authenticated", "invalid_token"}


@pytest.mark.parametrize(
    "public_routes", [f"{AUTH}/register", f"{AUTH}/login", f"{AUTH}/refresh"]
)
def test_the_public_routes_stay_public(client, public_routes: str):
    """The mirror image: these must NOT require a token. A 401 here would mean
    nobody can ever sign up."""
    response = client.post(public_routes, json={})

    assert response.status_code == 422  # bad body, not "who are you"


# ------------------------------------------------------ 403: not authorized


def test_an_ordinary_user_cannot_edit_someone_else(client, make_user, auth_headers):
    target = make_user(email="target@example.com")
    intruder = make_user(email="intruder@example.com")

    response = client.patch(
        f"{USERS}/{target.public_id}",
        json={"full_name": "Hacked"},
        headers=auth_headers(intruder),
    )

    assert response.status_code == 403
    assert response.json()["error"] == "permission_denied"


def test_an_ordinary_user_cannot_delete_someone_else(client, make_user, auth_headers):
    target = make_user(email="target@example.com")
    intruder = make_user(email="intruder@example.com")

    response = client.delete(
        f"{USERS}/{target.public_id}", headers=auth_headers(intruder)
    )

    assert response.status_code == 403


@pytest.mark.parametrize(
    ("method", "path_suffix", "body"),
    [
        ("post", "", {"email": "x@y.com", "full_name": "X", "password": PASSWORD}),
        ("post", "/{id}/restore", None),
        ("patch", "/{id}/role", {"role": "admin"}),
    ],
)
def test_admin_only_routes_reject_an_ordinary_user(
    client, make_user, normal_user, auth_headers, method, path_suffix, body
):
    """403, not 404 and not 401. The caller is authenticated; they are simply
    not allowed."""
    target = make_user(email="target@example.com")
    path = USERS + path_suffix.replace("{id}", str(target.public_id))

    response = getattr(client, method)(
        path, json=body, headers=auth_headers(normal_user)
    )

    assert response.status_code == 403


def test_an_admin_can_edit_anybody(client, admin_user, make_user, auth_headers):
    target = make_user(email="target@example.com")

    response = client.patch(
        f"{USERS}/{target.public_id}",
        json={"full_name": "Fixed By Admin"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200


def test_permission_is_checked_before_the_change_is_applied(
    client, make_user, auth_headers, db_session
):
    """A 403 that still wrote to the database would be worse than no check at
    all. This asserts the row is untouched, not just the status code."""
    target = make_user(email="target@example.com", full_name="Original Name")
    intruder = make_user(email="intruder@example.com")

    client.patch(
        f"{USERS}/{target.public_id}",
        json={"full_name": "Hacked"},
        headers=auth_headers(intruder),
    )

    db_session.refresh(target)
    assert target.full_name == "Original Name"


# ------------------------------------------------------ tokens and identity


def test_a_token_belonging_to_a_deleted_user_is_refused(
    client, make_user, auth_headers, user_service, admin_user
):
    victim = make_user(email="victim@example.com")
    headers = auth_headers(victim)
    user_service.soft_delete(admin_user, victim.public_id)

    assert client.get(f"{AUTH}/me", headers=headers).status_code == 401


def test_a_token_from_before_a_logout_is_refused(client, normal_user, auth_headers):
    headers = auth_headers(normal_user)
    client.post(f"{AUTH}/logout", headers=headers)

    assert client.get(f"{AUTH}/me", headers=headers).status_code == 401


def test_you_cannot_act_as_another_user_by_editing_the_token(
    client, make_user, auth_headers
):
    """Swap the payload of a valid token for another user's id and re-attach
    the old signature. The signature check is the only thing standing between
    this and a full account takeover."""
    victim = make_user(email="victim@example.com")
    attacker = make_user(email="attacker@example.com")

    import base64
    import json

    token = auth_headers(attacker)["Authorization"].removeprefix("Bearer ")
    header, payload, signature = token.split(".")
    claims = json.loads(base64.urlsafe_b64decode(payload + "=="))
    claims["sub"] = str(victim.public_id)
    forged_payload = (
        base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip("=")
    )

    response = client.get(
        f"{AUTH}/me",
        headers={"Authorization": f"Bearer {header}.{forged_payload}.{signature}"},
    )

    assert response.status_code == 401
