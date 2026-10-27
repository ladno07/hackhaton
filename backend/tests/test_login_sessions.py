from datetime import timedelta
from hashlib import sha256
import jwt
import pytest
from sqlalchemy import select
from app.config import settings
from app.models import LoginSession, now

LOGIN = {"email": "athlete@demo.example", "password": "DemoPass2026!"}


@pytest.mark.parametrize("origin", [
    "http://localhost:8080", "http://127.0.0.1:8080",
    "http://localhost:5173", "http://127.0.0.1:5173",
])
def test_local_browser_origins_support_entire_session(env, origin):
    client, _, _, _ = env
    headers = {"Origin": origin, "Sec-Fetch-Site": "same-origin"}
    assert client.post("/api/auth/login", json=LOGIN, headers=headers).status_code == 200
    assert client.post("/api/auth/refresh", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.post("/api/auth/refresh", headers=headers).status_code == 401


@pytest.mark.parametrize("origin", ["http://127.0.0.1:8081", "http://127.0.0.1.attacker.example:8080"])
def test_unconfigured_origins_still_rejected(env, origin):
    client, _, _, _ = env
    assert client.post("/api/auth/login", json=LOGIN, headers={"Origin": origin}).status_code == 403


def test_browser_session_restores_and_logout_revokes(env):
    client, factory, _, users = env
    response = client.post("/api/auth/login", json=LOGIN)
    assert response.status_code == 200
    cookie = client.cookies.get("orencode_session")
    headers = response.headers.get_list("set-cookie")
    assert any(
        "HttpOnly" in h
        and "SameSite=strict" in h
        and "Max-Age=2592000" in h
        and "Path=/api/auth" in h
        for h in headers
    )
    with factory() as db:
        stored = db.get(LoginSession, sha256(cookie.encode()).hexdigest())
        assert stored and stored.user_id == users["athlete"]["id"]
        assert cookie not in stored.token_hash
    # A browser with no access token restores it using its persistent cookie.
    restored = client.post("/api/auth/refresh")
    assert restored.status_code == 200
    access = restored.json()["access_token"]
    assert "no-store" in restored.headers["cache-control"]
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + access}
        ).status_code
        == 200
    )
    assert client.post("/api/auth/logout").status_code == 204
    assert client.post("/api/auth/refresh").status_code == 401
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + access}
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/auth/refresh", headers={"Cookie": "orencode_session=" + cookie}
        ).status_code
        == 401
    )


def test_expired_access_can_refresh_but_expired_session_cannot(env):
    client, factory, _, _ = env
    access = client.post("/api/auth/login", json=LOGIN).json()["access_token"]
    claims = jwt.decode(access, settings.jwt_secret, algorithms=["HS256"])
    claims["exp"] = now() - timedelta(seconds=1)
    expired = jwt.encode(claims, settings.jwt_secret, algorithm="HS256")
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + expired}
        ).status_code
        == 401
    )
    assert client.post("/api/auth/refresh").status_code == 200
    with factory() as db:
        session = db.get(LoginSession, claims["sid"])
        session.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.post("/api/auth/refresh").status_code == 401
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + access}
        ).status_code
        == 401
    )


@pytest.mark.parametrize("origin", ["http://localhost:8080", "http://127.0.0.1:8080", "http://localhost:5173", "http://127.0.0.1:5173"])
def test_local_origins_can_log_in(env, origin):
    client, _, _, _ = env
    response = client.post("/api/auth/login", json=LOGIN, headers={"Origin": origin})
    assert response.status_code == 200, response.text


def test_foreign_origins_and_forged_cookie_are_rejected(env):
    client, _, _, _ = env
    client.post("/api/auth/login", json=LOGIN)
    for path in ("login", "register", "refresh", "logout"):
        assert (
            client.post(
                "/api/auth/" + path,
                json=LOGIN,
                headers={"Origin": "https://attacker.example"},
            ).status_code
            == 403
        )
    assert (
        client.post(
            "/api/auth/refresh", headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.post("/api/auth/refresh").status_code == 200
    client.cookies.clear()
    assert (
        client.post(
            "/api/auth/refresh", headers={"Cookie": "orencode_session=forged"}
        ).status_code
        == 401
    )


def test_login_replaces_only_current_browser_session(env):
    client, factory, _, _ = env
    first = client.post("/api/auth/login", json=LOGIN).json()["access_token"]
    client.cookies.clear()  # a separate browser session
    second = client.post("/api/auth/login", json=LOGIN).json()["access_token"]
    client.post("/api/auth/logout")
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + second}
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/auth/me", headers={"Authorization": "Bearer " + first}
        ).status_code
        == 200
    )
