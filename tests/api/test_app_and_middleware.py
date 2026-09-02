"""The bits of the app that are not endpoints: probes, middleware, startup.

Easy to skip, and then easy to break - nothing here has a user-visible name,
so nobody notices until a deploy goes sideways or a browser starts refusing
requests.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app

pytestmark = pytest.mark.api


# ------------------------------------------------------------------- probes


def test_health_does_not_touch_the_database(client, query_counter):
    """Liveness answers "is this process alive?". If it queried the database, a
    database outage would make the orchestrator kill and restart perfectly
    healthy containers - turning a slow database into an outage."""
    with query_counter:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert query_counter.count == 0


def test_ready_does_touch_the_database(client, query_counter):
    """Readiness answers "can I serve traffic?", and the honest answer depends
    on the database. This is the opposite promise to the test above, which is
    why both are worth writing down."""
    with query_counter:
        response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert query_counter.count >= 1


def test_the_probes_sit_outside_the_version_prefix(client):
    """Your load balancer should not have to care what version your API is on.
    /api/v1/health must NOT exist."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/health").status_code == 404


# --------------------------------------------------------------- middleware


@pytest.mark.parametrize(
    ("header", "value"),
    [
        ("x-content-type-options", "nosniff"),
        ("x-frame-options", "DENY"),
        ("referrer-policy", "no-referrer"),
    ],
)
def test_the_security_headers_are_on_every_response(client, header: str, value: str):
    response = client.get("/health")
    assert response.headers[header] == value


def test_hsts_is_absent_outside_production(client):
    """Strict-Transport-Security tells a browser "never speak plain HTTP to
    this host again" - and it caches that. Sending it from localhost can lock
    a developer out of their own machine."""
    response = client.get("/health")
    assert "strict-transport-security" not in response.headers


def test_hsts_is_present_in_production():
    """Built with production settings, without setting the environment variable
    for the whole suite. The factory taking a Settings argument is what makes
    this a three-line test."""
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret="a" * 40,
        environment="production",
    )
    prod_app = create_app(settings)

    with TestClient(prod_app) as prod_client:
        response = prod_client.get("/health")

    assert "strict-transport-security" in response.headers


def test_the_interactive_docs_are_hidden_in_production():
    """/docs advertises every endpoint and every schema to anyone who finds the
    URL. Fine locally, not fine in public."""
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret="a" * 40,
        environment="production",
    )
    prod_app = create_app(settings)

    assert prod_app.docs_url is None
    assert prod_app.redoc_url is None


def test_the_docs_are_available_locally(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_every_response_reports_how_long_it_took(client):
    response = client.get("/health")
    assert float(response.headers["x-process-time-ms"]) >= 0


def test_a_request_id_is_generated_when_the_client_does_not_send_one(client):
    first = client.get("/health").headers["x-request-id"]
    second = client.get("/health").headers["x-request-id"]

    assert first and second
    assert first != second  # a new one per request


# --------------------------------------------------------------------- CORS


def test_an_allowed_origin_gets_the_cors_header(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_an_unknown_origin_gets_no_cors_header(client):
    """The browser is what enforces this, but the server is what decides it.
    A missing header means the browser refuses to hand the response to the
    page - which is the entire point."""
    response = client.get("/health", headers={"Origin": "http://evil.example.com"})

    assert "access-control-allow-origin" not in response.headers


def test_the_preflight_allows_the_methods_the_api_actually_uses(client):
    response = client.options(
        "/api/v1/users",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "PATCH",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_the_wildcard_origin_is_never_used(client):
    """With allow_credentials=True a browser rejects "*" anyway, and without
    it, "*" lets any site call your API from a victim's browser."""
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.headers["access-control-allow-origin"] != "*"


# ------------------------------------------------------- factory + lifespan


def test_create_app_returns_a_new_app_every_time():
    """A factory rather than a module-level global is what lets a test build an
    app with different settings - see the production tests above - without
    poisoning every other test in the process."""
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused", jwt_secret="a" * 40
    )

    assert create_app(settings) is not create_app(settings)


@pytest.mark.db
def test_the_lifespan_runs_on_startup_and_shutdown(app):
    """`with TestClient(...)` is what triggers lifespan; a plain TestClient(app)
    never runs it, which is why most of this suite skips it. Here we want it:
    the startup check is the difference between "the app refused to start,
    here's why" and "every request 500s and nobody knows why".
    """
    with TestClient(app) as started:
        assert started.get("/health").status_code == 200
    # exiting the block runs the shutdown half, disposing the engine


def test_the_v1_prefix_is_configurable_not_hardcoded():
    """Every route sits under settings.api_v1_prefix. Adding /api/v2 later
    means a sibling router package, not editing twenty decorators."""
    settings = Settings(
        database_url="postgresql+psycopg://unused/unused",
        jwt_secret="a" * 40,
        api_v1_prefix="/api/v9",
    )
    other = create_app(settings)

    # Read the paths off the OpenAPI schema rather than app.routes: recent
    # FastAPI versions put wrapper objects in .routes that have no .path, so
    # the schema is both simpler and less likely to break on an upgrade.
    paths = set(other.openapi()["paths"])
    assert "/api/v9/auth/login" in paths
    assert "/api/v1/auth/login" not in paths


def test_an_unknown_path_is_a_plain_404(client):
    response = client.get("/api/v1/nope")

    assert response.status_code == 404
