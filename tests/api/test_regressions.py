"""The regression file.

Every other file in this suite tests behaviour someone designed. This one
tests behaviour someone BROKE - each test here exists because a specific
mistake is easy to make, cheap to miss in review, and expensive in production.

The convention: when a bug is found, the fix comes with a test in here named
after the bug, not after the function. In six months nobody remembers what
`test_update_user_3` was for, but `test_patch_does_not_wipe_omitted_fields`
explains itself and tells the next person not to "simplify" it away.

These are deliberately end-to-end. A regression test should fail if the bug
comes back ANYWHERE - in the schema, the service, the repository or the route -
so it goes through the front door rather than poking at one layer.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.regression, pytest.mark.db]

USERS = "/api/v1/users"
AUTH = "/api/v1/auth"
PASSWORD = "Password123!"


def test_patch_does_not_wipe_omitted_fields(client, make_user, auth_headers):
    """BUG: dropping `exclude_unset=True` from the router.

    Without it, every field the client did not send arrives as None and
    overwrites the stored value. The endpoint still returns 200, so this only
    shows up as users complaining their phone number vanished.
    """
    user = make_user(email="wipe@example.com", phone="01711111111")

    response = client.patch(
        f"{USERS}/{user.public_id}",
        json={"full_name": "New Name"},
        headers=auth_headers(user),
    )

    assert response.json()["phone"] == "01711111111"


def test_a_soft_deleted_user_cannot_log_back_in(client, make_user):
    """BUG: a repository query that forgets `deleted_at IS NULL`.

    On Day 7 that filter was copy-pasted into five route functions. Miss it in
    the login path and a deleted account keeps working forever.
    """
    make_user(email="deleted@example.com", deleted=True)

    response = client.post(
        f"{AUTH}/login", json={"email": "deleted@example.com", "password": PASSWORD}
    )

    assert response.status_code == 401


def test_saving_your_own_profile_without_changing_your_email_is_not_a_conflict(
    client, make_user, auth_headers
):
    """BUG: dropping `exclude_id` from UserRepository.email_taken().

    Then the user's own row counts as "someone already has this email" and
    nobody can ever save their profile again. 409 on a no-op update.
    """
    user = make_user(email="mine@example.com")

    response = client.patch(
        f"{USERS}/{user.public_id}",
        json={"email": "mine@example.com", "full_name": "Same Email"},
        headers=auth_headers(user),
    )

    assert response.status_code == 200


def test_the_total_in_a_page_counts_every_match_not_just_the_page(
    client, normal_user, auth_headers, make_user
):
    """BUG: counting after applying limit/offset.

    `total` then always equals the page size, and every "page 3 of 7" in the
    frontend is wrong. Easy to write, invisible until someone counts.
    """
    for i in range(6):
        make_user(email=f"total{i}@example.com")

    response = client.get(f"{USERS}?limit=2", headers=auth_headers(normal_user))

    body = response.json()
    assert len(body["items"]) == 2
    assert body["total"] == 7  # 6 + the caller


def test_a_password_hash_never_appears_in_any_response(
    client, admin_user, auth_headers, make_user
):
    """BUG: returning the ORM object through a route with no response_model.

    Checks every user-shaped endpoint at once, so adding a new one without a
    response_model gets caught here rather than in a breach report.
    """
    target = make_user(email="hash@example.com")
    headers = auth_headers(admin_user)

    responses = [
        client.get(f"{AUTH}/me", headers=headers),
        client.get(USERS, headers=headers),
        client.get(f"{USERS}/{target.public_id}", headers=headers),
        client.patch(
            f"{USERS}/{target.public_id}", json={"full_name": "X"}, headers=headers
        ),
        client.post(
            f"{AUTH}/register",
            json={"email": "new@example.com", "full_name": "N", "password": PASSWORD},
        ),
    ]

    for response in responses:
        assert "argon2" not in response.text
        assert "hashed_password" not in response.text
        assert "token_version" not in response.text


def test_registration_cannot_smuggle_in_an_admin_role(client):
    """BUG: adding `role` to UserCreate, or passing **payload.model_dump()
    straight into the User model.

    Privilege escalation via a single extra JSON key. The service decides the
    role; the client never gets a vote.
    """
    response = client.post(
        f"{AUTH}/register",
        json={
            "email": "sneaky@example.com",
            "full_name": "Sneaky",
            "password": PASSWORD,
            "role": "admin",
            "token_version": 99,
        },
    )

    assert response.status_code == 201
    assert response.json()["role"] == "user"


def test_the_last_admin_cannot_demote_themselves(client, admin_user, auth_headers):
    """BUG: removing the self-demotion guard from UserService.set_role.

    One request and nobody can reach any admin endpoint again, with no way back
    in through the API - you would be fixing it in psql.
    """
    response = client.patch(
        f"{USERS}/{admin_user.public_id}/role",
        json={"role": "user"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 403


def test_logging_out_really_invalidates_the_token(client, normal_user, auth_headers):
    """BUG: forgetting the token_version bump, or checking `ver` against the
    token instead of the row.

    JWTs are stateless - the server cannot delete one it has already issued.
    The version check is the only thing that makes logout mean anything, so a
    silent break here leaves every "logged out" session fully alive.
    """
    headers = auth_headers(normal_user)
    client.post(f"{AUTH}/logout", headers=headers)

    assert client.get(f"{AUTH}/me", headers=headers).status_code == 401


def test_a_refresh_token_is_not_accepted_as_an_access_token(
    client, normal_user, auth_headers
):
    """BUG: dropping the `typ` check from decode_token.

    Refresh tokens live for 7 days, access tokens for 15 minutes. Without the
    check, a leaked refresh token is a week-long master key to every protected
    route.
    """
    tokens = client.post(
        f"{AUTH}/login", json={"email": normal_user.email, "password": PASSWORD}
    ).json()

    response = client.get(
        f"{AUTH}/me",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )

    assert response.status_code == 401


def test_login_failures_are_still_counted(client, make_user):
    """BUG: an early `return` that skips throttle.record_failure(), or a
    throttle that is rebuilt per request instead of shared.

    Either way the lockout silently stops existing and the login endpoint
    becomes an unlimited password-guessing oracle. The failure mode is that
    everything still works, which is exactly why it needs a test.
    """
    make_user(email="brute@example.com")
    payload = {"email": "brute@example.com", "password": "wrong"}

    statuses = [client.post(f"{AUTH}/login", json=payload).status_code for _ in range(4)]

    assert statuses == [401, 401, 401, 429]


def test_the_page_size_cap_still_applies(client, normal_user, auth_headers):
    """BUG: dropping the min() in the Pagination dependency.

    ?limit=1000000 then becomes a legal request and one caller can pull the
    whole table - a denial of service you built yourself.
    """
    response = client.get(f"{USERS}?limit=100000", headers=auth_headers(normal_user))

    assert response.json()["limit"] == 100


def test_an_unknown_user_id_is_a_404_not_a_500(client, normal_user, auth_headers):
    """BUG: a service returning None where the route expects a User.

    The response model then fails to serialise and the client gets a 500 - an
    "our fault" status code for what is plainly the caller's mistake.
    """
    import uuid

    response = client.get(f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user))

    assert response.status_code == 404
    assert response.json()["error"] == "user_not_found"


def test_error_responses_keep_their_shape(client):
    """BUG: raising a bare HTTPException somewhere in a service.

    FastAPI renders those as {"detail": ...} with no "error" key, so clients
    that switch on `error` break on one endpoint and nobody notices until a
    support ticket arrives.
    """
    response = client.post(f"{AUTH}/login", json={"email": "a@b.com", "password": "x"})

    body = response.json()
    assert set(body) == {"error", "detail"}
    assert isinstance(body["error"], str)
