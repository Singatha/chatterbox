from httpx import AsyncClient


async def test_register_returns_tokens_without_password_hash(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    response = await client.post("/auth/register", json=user_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["user"]["username"] == "alice"
    assert body["user"]["email"] == "alice@example.com"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


async def test_duplicate_registration_has_consistent_error(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    assert (await client.post("/auth/register", json=user_payload)).status_code == 201

    response = await client.post("/auth/register", json=user_payload)

    assert response.status_code == 409
    assert response.json() == {
        "error": {
            "code": "USER_ALREADY_EXISTS",
            "message": "Email or username is already registered",
        }
    }


async def test_login_with_email_or_username(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    await client.post("/auth/register", json=user_payload)

    by_email = await client.post(
        "/auth/login", json={"login": "ALICE@EXAMPLE.COM", "password": user_payload["password"]}
    )
    by_username = await client.post(
        "/auth/login", json={"login": "ALICE", "password": user_payload["password"]}
    )

    assert by_email.status_code == 200
    assert by_username.status_code == 200


async def test_login_rejects_bad_credentials(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    await client.post("/auth/register", json=user_payload)

    response = await client.post(
        "/auth/login", json={"login": "alice", "password": "not-the-right-password"}
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


async def test_protected_route_requires_valid_access_token(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    unauthenticated = await client.get("/auth/me")
    registration = await client.post("/auth/register", json=user_payload)
    token = registration.json()["access_token"]
    authenticated = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["error"]["code"] == "AUTHENTICATION_REQUIRED"
    assert authenticated.status_code == 200
    assert authenticated.json()["username"] == "alice"


async def test_refresh_rotates_token_and_rejects_reuse(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    registration = await client.post("/auth/register", json=user_payload)
    original = registration.json()["refresh_token"]

    refreshed = await client.post("/auth/refresh", json={"refresh_token": original})
    reused = await client.post("/auth/refresh", json={"refresh_token": original})

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] != original
    assert reused.status_code == 401
    assert reused.json()["error"]["code"] == "INVALID_REFRESH_TOKEN"


async def test_logout_revokes_refresh_token(
    client: AsyncClient, user_payload: dict[str, str]
) -> None:
    registration = await client.post("/auth/register", json=user_payload)
    refresh_token = registration.json()["refresh_token"]

    logout = await client.post("/auth/logout", json={"refresh_token": refresh_token})
    refresh = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert logout.status_code == 204
    assert refresh.status_code == 401


async def test_registration_validation_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/register",
        json={"username": "x!", "email": "bad-email", "password": "short"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert len(response.json()["error"]["details"]) == 3

