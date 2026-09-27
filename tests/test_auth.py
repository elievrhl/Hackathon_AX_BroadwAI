from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.auth import PASSWORDS, SESSION_COOKIE, digest
from broadwai.config import Settings
from broadwai.models import Cover, utcnow
from tests.auth_fakes import AuthMemoryStore

ORIGIN = "http://127.0.0.1:5173"
HEADERS = {"Origin": ORIGIN, "X-Kiosque-Request": "1"}
PASSWORD = "une longue phrase confidentielle"


@pytest.fixture
def auth():
    store = AuthMemoryStore()
    app = create_app(Settings(_env_file=None, openai_api_key=None), store=store)
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
        yield client, store


def register(client, email="alice@example.com"):
    response = client.post(
        "/v1/auth/register",
        json={
            "email": email,
            "name": "Alice",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 201, response.text
    client.headers["X-Kiosque-CSRF"] = response.json()["csrf_token"]
    return response.json()["account"]


def test_server_account_password_and_second_device_session(auth):
    client, store = auth
    account = register(client)
    assert account["reader_profile"] is None
    assert PASSWORDS.verify(store.accounts[account["id"]]["password_hash"], PASSWORD)
    assert "password" not in str(account)
    assert client.get("/v1/auth/session").json()["account"] == account
    profile = {
        "name": "Camille",
        "topics": ["tech"],
        "languages": ["fr"],
        "notes": "Mon projet",
        "size": 18,
    }
    assert client.put("/v1/auth/profile", json={"profile": profile}).status_code == 200
    with TestClient(client.app, base_url=ORIGIN, headers=HEADERS) as second:
        assert second.get("/v1/auth/session").json()["account"] is None
        logged = second.post(
            "/v1/auth/login", json={"email": " ALICE@EXAMPLE.COM ", "password": PASSWORD}
        )
        assert logged.status_code == 200
        assert logged.json()["account"]["id"] == account["id"]
        assert logged.json()["account"]["reader_profile"] == profile
        assert logged.json()["account"]["name"] == "Camille"


def test_bad_credentials_and_duplicate_accounts(auth):
    client, _ = auth
    register(client)
    assert (
        client.post(
            "/v1/auth/register",
            json={"email": "alice@example.com", "name": "Alice", "password": PASSWORD},
        ).status_code
        == 409
    )
    for address in ("alice@example.com", "nobody@example.com"):
        response = client.post("/v1/auth/login", json={"email": address, "password": "wrong"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Adresse e-mail ou mot de passe incorrect."
    assert (
        client.post(
            "/v1/auth/register",
            json={"email": "other@example.com", "name": "A", "password": "short"},
        ).status_code
        == 422
    )


def test_private_routes_need_a_session_and_admin_routes_need_admin(auth):
    client, _ = auth
    for path in (
        "/v1/covers",
        "/v1/archives?user_id=alice",
        "/v1/collections?user_id=alice",
        "/v1/readers/alice/preferences",
        "/admin",
        "/v1/admin/editions",
    ):
        assert client.get(path).status_code == 401, path
    register(client)
    for path in ("/admin", "/admin/covers", "/v1/admin/editions", "/v1/sources", "/v1/articles"):
        assert client.get(path).status_code == 403, path


def test_cannot_read_or_write_another_reader_even_without_user_query(auth):
    client, store = auth
    alice = register(client)
    for owner, cover_id in ((alice["id"], "mine"), ("someone-else", "theirs")):
        store.put_cover(
            Cover(
                id=cover_id,
                user_id=owner,
                title=cover_id,
                items=[],
                status="complete",
                trace=[],
                warnings=[],
                usage={},
            )
        )
    assert [row["id"] for row in client.get("/v1/covers").json()] == ["mine"]
    assert client.get("/v1/covers/mine").status_code == 200
    assert client.get("/v1/covers/theirs").status_code == 404
    for path in (
        "/v1/covers?user_id=someone-else",
        "/v1/likes?user_id=someone-else",
        "/v1/archives?user_id=someone-else",
        "/v1/readers/someone-else/preferences",
        "/v1/collections?user_id=someone-else",
        "/v1/saved-articles?user_id=someone-else",
    ):
        assert client.get(path).status_code == 403, path
    payload = {
        "profile": {"user_id": "someone-else", "interests": [{"topic": "Python"}]},
        "size": 1,
    }
    assert client.post("/v1/covers", json=payload).status_code == 403
    assert (
        client.post(
            "/v1/feedback",
            json={
                "user_id": "someone-else",
                "cover_id": "mine",
                "article_id": "a",
                "kind": "useful",
            },
        ).status_code
        == 403
    )


def test_csrf_rotation_logout_and_expiry(auth):
    client, store = auth
    account = register(client)
    original = client.cookies.get(SESSION_COOKIE)
    assert original not in store.sessions
    assert digest(original) in store.sessions
    assert (
        client.put(
            "/v1/auth/profile", json={"profile": None}, headers={"X-Kiosque-CSRF": ""}
        ).status_code
        == 403
    )
    assert (
        client.put(
            "/v1/auth/profile", json={"profile": None}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    logged = client.post("/v1/auth/login", json={"email": account["email"], "password": PASSWORD})
    assert digest(original) not in store.sessions
    assert "HttpOnly" in logged.headers["set-cookie"]
    assert "SameSite=lax" in logged.headers["set-cookie"]
    assert logged.headers["cache-control"] == "no-store"
    client.headers["X-Kiosque-CSRF"] = logged.json()["csrf_token"]
    assert client.post("/v1/auth/logout").status_code == 204
    assert client.get("/v1/auth/session").json()["account"] is None
    client.cookies.set(SESSION_COOKIE, original)
    assert client.get("/v1/covers").status_code == 401
    store.create_session(digest(original), account["id"], utcnow() - timedelta(seconds=1))
    assert client.get("/v1/covers").status_code == 401


def test_login_csrf_and_attempt_limits(auth):
    client, store = auth
    assert (
        client.post(
            "/v1/auth/login",
            json={"email": "a@example.com", "password": PASSWORD},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/v1/auth/login",
            json={"email": "a@example.com", "password": PASSWORD},
            headers={"X-Kiosque-Request": ""},
        ).status_code
        == 403
    )
    store.attempts[digest("login:email:a@example.com")] = 10
    response = client.post("/v1/auth/login", json={"email": "a@example.com", "password": PASSWORD})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "900"


def test_unconfigured_providers_do_not_offer_a_fake_login(auth):
    client, _ = auth
    assert client.get("/v1/auth/session").json()["providers"] == {"google": False, "apple": False}
    assert client.get("/v1/auth/google/start").status_code == 503
    assert client.get("/v1/auth/apple/start").status_code == 503


def test_oauth_state_is_browser_bound_single_use_and_session_is_server_owned(monkeypatch):
    settings = Settings(
        _env_file=None, google_client_id="google-client", google_client_secret="secret"
    )
    store = AuthMemoryStore()
    app = create_app(settings, store=store)
    with TestClient(app, base_url=ORIGIN, headers=HEADERS) as client:
        start = client.get("/v1/auth/google/start", follow_redirects=False)
        params = parse_qs(urlsplit(start.headers["location"]).query)
        state = params["state"][0]
        assert params["code_challenge_method"] == ["S256"]
        assert len(params["nonce"][0]) > 30
        with TestClient(app, base_url=ORIGIN) as other:
            refused = other.get(
                f"/v1/auth/google/callback?state={state}&code=fake", follow_redirects=False
            )
            assert "auth_error=oauth_failed" in refused.headers["location"]

        async def exchange(provider, code, flow):
            assert flow["nonce"] == params["nonce"][0]
            return {"email": "google@example.com", "sub": "google-123", "name": "Camille"}

        monkeypatch.setattr(app.state.oauth, "exchange", exchange)
        callback = client.get(
            f"/v1/auth/google/callback?state={state}&code=fake", follow_redirects=False
        )
        assert callback.headers["location"] == settings.auth_public_url
        assert client.get("/v1/auth/session").json()["account"]["email"] == "google@example.com"
        replay = client.get(
            f"/v1/auth/google/callback?state={state}&code=fake", follow_redirects=False
        )
        assert "auth_error=oauth_failed" in replay.headers["location"]


def test_oauth_never_links_an_unverified_password_account_by_email(auth):
    client, store = auth
    account = register(client)
    with pytest.raises(ValueError, match="email_in_use"):
        store.oauth_account("google", "other-subject", account["email"], "Not the same identity")
    assert not store.identities
