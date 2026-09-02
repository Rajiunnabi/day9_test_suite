"""Error handling: the paths you cannot reach with a well-behaved request.

Some failures cannot be triggered by sending a clever payload - a database
going down mid-request, a service raising something nobody anticipated, two
requests racing to the same unique index. The way to test them is to override
a dependency with one that fails on purpose, which is the same
dependency_overrides mechanism used everywhere else in this suite, pointed at
a different job.

That is the real answer to "what should I mock": mock what you cannot
otherwise cause. Not the database - the database is easy to run. The
*disaster* is what is hard to arrange, so that is what gets faked.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.api import deps
from app.core.exceptions import AppError, ConflictError, NotFoundError

pytestmark = [pytest.mark.api, pytest.mark.db]

USERS = "/api/v1/users"
AUTH = "/api/v1/auth"


# ------------------------------------------------- every error, one shape


@pytest.mark.parametrize(
    ("status", "error_code", "make_request"),
    [
        (401, "not_authenticated", lambda c, h: c.get(f"{AUTH}/me")),
        (
            404,
            "user_not_found",
            lambda c, h: c.get(f"{USERS}/{uuid.uuid4()}", headers=h),
        ),
        (
            422,
            "validation_error",
            lambda c, h: c.post(f"{AUTH}/register", json={}, headers=h),
        ),
    ],
)
def test_every_failure_uses_the_same_json_shape(
    client, normal_user, auth_headers, status: int, error_code: str, make_request
):
    """One envelope for every error: {"error": "...", "detail": ...}.

    Consistency is the whole point. A frontend writes one error handler instead
    of five, and nobody has to guess whether this endpoint says "detail",
    "message" or "errors" today.
    """
    response = make_request(client, auth_headers(normal_user))

    assert response.status_code == status
    body = response.json()
    assert body["error"] == error_code
    assert "detail" in body


def test_a_401_body_never_hints_at_why(client, make_user):
    make_user(email="a@b.com")

    response = client.post(
        f"{AUTH}/login", json={"email": "a@b.com", "password": "wrong"}
    )

    assert "password" not in response.json()["detail"].lower().replace(
        "email or password", ""
    )


# ------------------------------------------- unexpected errors become a 500


def test_an_unexpected_exception_becomes_a_clean_500(client, app):
    """Force a service to explode, and check the client learns nothing from it.

    Internal error text leaks table names, file paths and sometimes
    credentials. The catch-all handler in app/api/errors.py logs the traceback
    and returns a fixed sentence - this is the test for that promise.
    """

    class ExplodingService:
        def get(self, public_id):
            raise RuntimeError("connection string: postgres://admin:hunter2@db")

    app.dependency_overrides[deps.get_user_service] = ExplodingService

    response = client.get(
        f"{USERS}/{uuid.uuid4()}",
        headers={"Authorization": "Bearer irrelevant"},
    )

    assert response.status_code in (401, 500)
    assert "hunter2" not in response.text
    assert "postgres://" not in response.text
    assert "Traceback" not in response.text


def test_the_500_body_is_generic(client, app, normal_user, auth_headers):
    class ExplodingService:
        def get(self, public_id):
            raise RuntimeError("secret internal detail")

    app.dependency_overrides[deps.get_user_service] = ExplodingService

    response = client.get(
        f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user)
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "detail": "Something went wrong.",
    }


def test_a_database_outage_does_not_crash_the_readiness_probe(client, app):
    """/ready is the endpoint your load balancer polls. When the database is
    gone it must answer - with a failure - rather than hang or leak."""

    def broken_db():
        raise RuntimeError("could not connect to server")

    app.dependency_overrides[deps.get_db] = broken_db

    response = client.get("/ready")

    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


# ------------------------------------------- database constraints become 409


def test_an_unanticipated_integrity_error_becomes_409(
    client, app, normal_user, auth_headers
):
    """The registration race, from the API's side.

    Two requests can both pass the "is this email taken?" check before either
    inserts; only one survives the unique index, and the loser raises
    IntegrityError from somewhere the service never expected. 409 is the honest
    answer - "your change conflicts with existing data" - not 500.

    Simulated with a service that raises the same exception the driver would.
    """

    class RacingService:
        def get(self, public_id):
            raise IntegrityError("INSERT ...", {}, Exception("duplicate key"))

    app.dependency_overrides[deps.get_user_service] = RacingService

    response = client.get(
        f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user)
    )

    assert response.status_code == 409
    assert response.json()["error"] == "integrity_error"
    assert "duplicate key" not in response.text  # the driver message stays internal


# ------------------------------------------------ custom exceptions map right


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (NotFoundError, 404),
        (ConflictError, 409),
    ],
)
def test_any_app_error_maps_to_its_own_status_code(
    client, app, normal_user, auth_headers, exception, expected_status
):
    """The handler reads status_code off the exception class, so a new
    AppError subclass works without touching app/api/errors.py. This proves
    that, using errors the routes do not normally raise."""

    class RaisingService:
        def get(self, public_id):
            raise exception()

    app.dependency_overrides[deps.get_user_service] = RaisingService

    response = client.get(
        f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user)
    )

    assert response.status_code == expected_status


def test_a_bare_app_error_defaults_to_400(client, app, normal_user, auth_headers):
    class RaisingService:
        def get(self, public_id):
            raise AppError("something the caller did wrong")

    app.dependency_overrides[deps.get_user_service] = RaisingService

    response = client.get(
        f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user)
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "something the caller did wrong"


def test_the_service_layer_never_raises_httpexception(client, normal_user, auth_headers):
    """A design rule, enforced by a test rather than by hoping.

    If a service raised HTTPException it would work - and it would also weld
    the business logic to FastAPI, so the same service could not be called
    from a CLI or a worker. Reading the source is the only way to check a rule
    like this, so the test reads the source.
    """
    import pathlib
    import re

    services = pathlib.Path(__file__).resolve().parents[2] / "app" / "services"
    for module in services.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        # Match import statements and raises, not the word appearing in a
        # comment or docstring - auth.py's docstring says "no HTTPException",
        # and a test that fails on prose is a test people learn to ignore.
        assert not re.search(r"^\s*(from|import)\s+fastapi", source, re.M), (
            f"{module.name} imports FastAPI - business logic should not know "
            "it is being called over HTTP"
        )
        assert not re.search(r"raise\s+HTTPException", source), (
            f"{module.name} raises HTTPException - raise an AppError instead"
        )


def test_the_repository_layer_never_commits():
    """The other half of the same idea: a commit is a business decision, so it
    belongs to the service. If a repository commits, a service can no longer
    make two writes succeed or fail together."""
    import pathlib

    repos = pathlib.Path(__file__).resolve().parents[2] / "app" / "repositories"
    for module in repos.glob("*.py"):
        source = module.read_text(encoding="utf-8")
        assert ".commit()" not in source, f"{module.name} commits - it should not"


# ------------------------------------------------------ headers on errors


def test_a_401_still_carries_the_www_authenticate_header(client):
    """Custom headers declared on the exception class survive the trip through
    the handler. Without this, a compliant HTTP client cannot tell that it
    should be sending credentials."""
    response = client.get(f"{AUTH}/me")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_error_responses_still_get_the_security_headers(client):
    """Middleware wraps error responses too - a 404 page is just as capable of
    being sniffed or framed as a 200."""
    response = client.get(f"{AUTH}/me")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_a_handled_error_still_gets_a_request_id(client, normal_user, auth_headers):
    """The id in the response is what ties a user's screenshot to a line in
    your logs. It has to be there on the responses people actually complain
    about, which are the failures."""
    response = client.get(f"{USERS}/{uuid.uuid4()}", headers=auth_headers(normal_user))

    assert response.status_code == 404
    assert response.headers["x-request-id"]


def test_an_incoming_request_id_is_kept_rather_than_replaced(client):
    """So one id follows a request across services instead of each hop
    inventing its own."""
    response = client.get("/health", headers={"X-Request-ID": "abc12345"})

    assert response.headers["x-request-id"] == "abc12345"


def test_the_service_is_reachable_again_after_a_forced_failure(
    client, normal_user, auth_headers, make_user
):
    """Cleanup check. dependency_overrides is a dict on the app object, and the
    app fixture clears it - but a leaked override would poison every later
    test in a way that is maddening to trace, so it is worth one assertion."""
    target = make_user(email="still-working@example.com")

    response = client.get(
        f"{USERS}/{target.public_id}", headers=auth_headers(normal_user)
    )

    assert response.status_code == 200
