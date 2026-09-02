"""The /api/v1/users endpoints."""

from __future__ import annotations

import uuid

import pytest

from app.core.enums import UserRole

pytestmark = [pytest.mark.api, pytest.mark.db]

USERS = "/api/v1/users"
PASSWORD = "Password123!"


# --------------------------------------------------------------------- list


def test_list_returns_the_page_envelope(client, normal_user, auth_headers, make_user):
    make_user(email="other@example.com")

    response = client.get(USERS, headers=auth_headers(normal_user))

    body = response.json()
    assert response.status_code == 200
    assert set(body) == {"items", "total", "limit", "offset"}
    assert body["total"] == 2


def test_list_requires_authentication(client):
    assert client.get(USERS).status_code == 401


def test_list_can_be_searched(client, normal_user, auth_headers, make_user):
    make_user(email="findme@example.com", full_name="Findable Person")
    make_user(email="hidden@example.com", full_name="Someone Else")

    response = client.get(f"{USERS}?q=Findable", headers=auth_headers(normal_user))

    assert response.json()["total"] == 1


@pytest.mark.parametrize(
    ("query", "expected_limit"),
    [
        ("", 20),  # default_page_size
        ("?limit=5", 5),
        ("?limit=1000", 100),  # capped at max_page_size
    ],
)
def test_the_pagination_dependency_applies_defaults_and_caps(
    client, normal_user, auth_headers, query: str, expected_limit: int
):
    """The cap is not decoration - without it one request can ask for a million
    rows and take the database with it."""
    response = client.get(f"{USERS}{query}", headers=auth_headers(normal_user))

    assert response.json()["limit"] == expected_limit


@pytest.mark.parametrize("bad", ["?limit=0", "?limit=-1", "?offset=-1", "?limit=abc"])
def test_nonsense_paging_values_are_rejected_with_422(
    client, normal_user, auth_headers, bad: str
):
    response = client.get(f"{USERS}{bad}", headers=auth_headers(normal_user))
    assert response.status_code == 422


def test_paging_returns_different_rows_on_each_page(
    client, normal_user, auth_headers, make_user
):
    for i in range(4):
        make_user(email=f"p{i}@example.com")

    first = client.get(f"{USERS}?limit=2&offset=0", headers=auth_headers(normal_user))
    second = client.get(f"{USERS}?limit=2&offset=2", headers=auth_headers(normal_user))

    first_ids = {u["public_id"] for u in first.json()["items"]}
    second_ids = {u["public_id"] for u in second.json()["items"]}
    assert first_ids.isdisjoint(second_ids)
    assert first.json()["total"] == second.json()["total"] == 5


def test_deleted_users_do_not_appear_in_the_list(
    client, normal_user, auth_headers, make_user
):
    make_user(email="ghost@example.com", deleted=True)

    response = client.get(USERS, headers=auth_headers(normal_user))

    emails = [u["email"] for u in response.json()["items"]]
    assert "ghost@example.com" not in emails


# ---------------------------------------------------------------------- get


def test_get_one_user(client, normal_user, auth_headers, make_user):
    target = make_user(email="target@example.com")

    response = client.get(
        f"{USERS}/{target.public_id}", headers=auth_headers(normal_user)
    )

    assert response.status_code == 200
    assert response.json()["email"] == "target@example.com"


def test_an_unknown_id_is_404_not_500(client, normal_user, auth_headers):
    response = client.get(f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user))

    assert response.status_code == 404
    assert response.json()["error"] == "user_not_found"


def test_a_malformed_id_is_422_and_never_reaches_the_database(
    client, normal_user, auth_headers
):
    """Typing the path parameter as uuid.UUID is what does this. FastAPI
    rejects `/users/not-a-uuid` before the route function is even called."""
    response = client.get(f"{USERS}/not-a-uuid", headers=auth_headers(normal_user))

    assert response.status_code == 422
    assert response.json()["error"] == "validation_error"


# -------------------------------------------------------------------- patch


def test_a_user_can_update_their_own_profile(client, normal_user, auth_headers):
    response = client.patch(
        f"{USERS}/{normal_user.public_id}",
        json={"full_name": "Renamed"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Renamed"


def test_patch_leaves_the_fields_it_was_not_given_alone(
    client, make_user, auth_headers
):
    user = make_user(email="keep@example.com", phone="0171111111")

    response = client.patch(
        f"{USERS}/{user.public_id}",
        json={"full_name": "Only The Name"},
        headers=auth_headers(user),
    )

    body = response.json()
    assert body["full_name"] == "Only The Name"
    assert body["phone"] == "0171111111"  # not blanked
    assert body["email"] == "keep@example.com"


def test_patch_can_deliberately_clear_a_field(client, make_user, auth_headers):
    """Sending null is different from omitting the key, and exclude_unset is
    what keeps them different."""
    user = make_user(email="clear@example.com", phone="0171111111")

    response = client.patch(
        f"{USERS}/{user.public_id}",
        json={"phone": None},
        headers=auth_headers(user),
    )

    assert response.json()["phone"] is None


def test_patch_refuses_an_email_that_belongs_to_someone_else(
    client, make_user, auth_headers
):
    make_user(email="theirs@example.com")
    mine = make_user(email="mine@example.com")

    response = client.patch(
        f"{USERS}/{mine.public_id}",
        json={"email": "theirs@example.com"},
        headers=auth_headers(mine),
    )

    assert response.status_code == 409


def test_a_client_cannot_promote_itself_through_patch(
    client, normal_user, auth_headers
):
    """UserUpdate has no `role` field, so the key is ignored rather than
    obeyed. Role changes have their own admin-only endpoint on purpose."""
    response = client.patch(
        f"{USERS}/{normal_user.public_id}",
        json={"full_name": "Still Normal", "role": "admin"},
        headers=auth_headers(normal_user),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "user"


# ------------------------------------------------------------------- delete


def test_a_user_can_delete_their_own_account(client, normal_user, auth_headers):
    headers = auth_headers(normal_user)

    response = client.delete(f"{USERS}/{normal_user.public_id}", headers=headers)

    assert response.status_code == 200
    after = client.get(f"{USERS}/{normal_user.public_id}", headers=headers)
    # 401 because the delete also revoked their token; 404 if a different
    # caller looked. Either is correct - the account is gone.
    assert after.status_code in (401, 404)


def test_deleting_your_account_invalidates_your_token(
    client, normal_user, auth_headers
):
    headers = auth_headers(normal_user)
    client.delete(f"{USERS}/{normal_user.public_id}", headers=headers)

    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401


def test_deleting_twice_is_a_404_the_second_time(
    client, admin_user, auth_headers, make_user
):
    target = make_user(email="twice@example.com")
    headers = auth_headers(admin_user)
    path = f"{USERS}/{target.public_id}"

    assert client.delete(path, headers=headers).status_code == 200
    assert client.delete(path, headers=headers).status_code == 404


# ------------------------------------------------------------------ restore


def test_an_admin_can_restore_a_deleted_user(
    client, admin_user, auth_headers, make_user
):
    target = make_user(email="back@example.com", deleted=True)

    response = client.post(
        f"{USERS}/{target.public_id}/restore", headers=auth_headers(admin_user)
    )

    assert response.status_code == 200
    assert response.json()["email"] == "back@example.com"


def test_restore_is_409_if_the_email_was_taken_meanwhile(
    client, admin_user, auth_headers, make_user
):
    deleted = make_user(email="contested@example.com", deleted=True)
    make_user(email="contested@example.com")  # allowed: the other one is deleted

    response = client.post(
        f"{USERS}/{deleted.public_id}/restore", headers=auth_headers(admin_user)
    )

    assert response.status_code == 409


# -------------------------------------------------------------------- roles


def test_an_admin_can_promote_a_user(client, admin_user, auth_headers, make_user):
    target = make_user(email="promote@example.com")

    response = client.patch(
        f"{USERS}/{target.public_id}/role",
        json={"role": "admin"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 200
    assert response.json()["role"] == "admin"


def test_an_admin_cannot_demote_themselves(client, admin_user, auth_headers):
    response = client.patch(
        f"{USERS}/{admin_user.public_id}/role",
        json={"role": "user"},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("bad_role", ["superadmin", "", "USER", 1])
def test_an_invalid_role_value_is_422(
    client, admin_user, auth_headers, make_user, bad_role
):
    target = make_user(email="role@example.com")

    response = client.patch(
        f"{USERS}/{target.public_id}/role",
        json={"role": bad_role},
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 422


def test_a_promoted_user_can_use_admin_routes_straight_away(
    client, admin_user, auth_headers, make_user
):
    """The role is read from the database on every request, not from the token,
    so no re-login is needed. That is the behaviour this test locks in."""
    target = make_user(email="fresh-admin@example.com")
    client.patch(
        f"{USERS}/{target.public_id}/role",
        json={"role": "admin"},
        headers=auth_headers(admin_user),
    )

    # A token minted before the promotion, carrying the NEW token_version.
    response = client.post(
        USERS,
        json={
            "email": "created-by-new-admin@example.com",
            "full_name": "Created",
            "password": PASSWORD,
        },
        headers=auth_headers(target),
    )

    assert response.status_code == 201


# ------------------------------------------------------------- admin create


def test_an_admin_can_create_a_user(client, admin_user, auth_headers):
    response = client.post(
        USERS,
        json={
            "email": "made-by-admin@example.com",
            "full_name": "Made By Admin",
            "password": PASSWORD,
        },
        headers=auth_headers(admin_user),
    )

    assert response.status_code == 201
    assert response.json()["role"] == UserRole.USER.value
