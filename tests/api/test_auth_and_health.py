from __future__ import annotations

from tests.conftest import login, register_and_login


async def test_health_endpoints(client):
    assert (await client.get("/health/live")).json() == {"status": "ok"}
    ready = await client.get("/health/ready")
    assert ready.status_code == 200
    assert ready.json()["checks"]["database"] == "ok"


async def test_register_login_and_duplicate(client):
    r = await client.post(
        "/api/auth/register", json={"email": "Alice@Example.com", "password": "long-password-1"}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["data"]["email"] == "alice@example.com"
    assert body["data"]["role"] == "recruiter"
    assert "passwordHash" not in body["data"]

    dup = await client.post(
        "/api/auth/register", json={"email": "alice@example.com", "password": "long-password-1"}
    )
    assert dup.status_code == 409
    assert dup.json()["success"] is False
    assert dup.json()["traceId"]

    token = await client.post(
        "/api/auth/token", json={"email": "alice@example.com", "password": "long-password-1"}
    )
    assert token.status_code == 200
    assert token.json()["data"]["tokenType"] == "bearer"


async def test_wrong_password_is_401(client):
    await register_and_login(client, "bob@example.com", "bob-password-1")
    r = await client.post(
        "/api/auth/token", json={"email": "bob@example.com", "password": "wrong-password"}
    )
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"
    unknown = await client.post(
        "/api/auth/token", json={"email": "nobody@example.com", "password": "whatever-123"}
    )
    assert unknown.status_code == 401


async def test_register_validation_is_422_with_field_errors(client):
    r = await client.post("/api/auth/register", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422
    fields = {e["field"] for e in r.json()["errors"]}
    assert {"email", "password"} <= fields


async def test_only_admin_can_create_admin(client, auth, admin_auth):
    body = {"email": "boss@example.com", "password": "boss-password-1", "role": "admin"}
    assert (await client.post("/api/auth/register", json=body)).status_code == 403
    assert (await client.post("/api/auth/register", json=body, headers=auth)).status_code == 403
    created = await client.post("/api/auth/register", json=body, headers=admin_auth)
    assert created.status_code == 201
    assert created.json()["data"]["role"] == "admin"


async def test_protected_endpoints_require_valid_token(client):
    assert (await client.get("/api/resumes")).status_code == 401
    bad = await client.get("/api/resumes", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401
    assert bad.json()["message"] == "Invalid token"


async def test_login_rate_limit_returns_429(app_factory):
    async with app_factory(login_rate_limit_burst=2, login_rate_limit_per_minute=1) as client:
        await client.post(
            "/api/auth/register", json={"email": "c@example.com", "password": "c-password-12"}
        )
        for _ in range(2):
            await client.post(
                "/api/auth/token", json={"email": "c@example.com", "password": "bad-password"}
            )
        r = await client.post(
            "/api/auth/token", json={"email": "c@example.com", "password": "c-password-12"}
        )
        assert r.status_code == 429
        assert int(r.headers["retry-after"]) >= 1


async def test_request_id_is_propagated(client):
    r = await client.get("/health/live", headers={"X-Request-ID": "abc12345-req"})
    assert r.headers["x-request-id"] == "abc12345-req"
    r = await client.get("/api/jobs/missing", headers={"X-Request-ID": "trace-0001"})
    assert r.json()["traceId"] == "trace-0001"


async def test_admin_login(client):
    from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

    headers = await login(client, ADMIN_EMAIL, ADMIN_PASSWORD)
    assert headers["Authorization"].startswith("Bearer ")
