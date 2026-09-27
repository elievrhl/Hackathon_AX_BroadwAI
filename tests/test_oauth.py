import json
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from broadwai.api import create_app
from broadwai.config import Settings
from broadwai.oauth import OAuth
from tests.auth_fakes import AuthMemoryStore


@pytest.fixture
def signing_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.mark.parametrize("provider", ["google", "apple"])
async def test_oidc_validates_signature_issuer_audience_expiry_nonce_and_email(
    signing_key, provider
):
    settings = Settings(_env_file=None, google_client_id="client", apple_client_id="client")
    oauth = OAuth(settings)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(signing_key.public_key()))
    jwk["kid"] = "test-key"
    oauth.client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"keys": [jwk]}))
    )
    claims = {
        "sub": "reader-id",
        "email": "reader@example.com",
        "email_verified": True,
        "iss": "https://accounts.google.com"
        if provider == "google"
        else "https://appleid.apple.com",
        "aud": "client",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "nonce": "browser-nonce",
    }

    def encode(value, key=signing_key):
        return jwt.encode(value, key, algorithm="RS256", headers={"kid": "test-key"})

    try:
        assert (await oauth.verify_token(provider, encode(claims), "browser-nonce"))[
            "sub"
        ] == "reader-id"
        for change in (
            {"aud": "another-client"},
            {"iss": "https://attacker.example"},
            {"exp": 1},
            {"nonce": "other"},
            {"email_verified": False},
            {"azp": "other-client"},
        ):
            with pytest.raises((ValueError, jwt.PyJWTError)):
                await oauth.verify_token(provider, encode({**claims, **change}), "browser-nonce")
        with pytest.raises(jwt.InvalidSignatureError):
            await oauth.verify_token(
                provider,
                encode(claims, rsa.generate_private_key(public_exponent=65537, key_size=2048)),
                "browser-nonce",
            )
        with pytest.raises((ValueError, jwt.PyJWTError)):
            await oauth.verify_token(
                provider,
                jwt.encode(claims, "fake-secret-that-is-at-least-32-bytes-long", algorithm="HS256"),
                "browser-nonce",
            )
    finally:
        await oauth.client.aclose()


def test_apple_form_post_uses_secure_browser_binding_and_verified_token_email(monkeypatch):
    settings = Settings(
        _env_file=None,
        auth_public_url="https://kiosque.example/reader/",
        apple_client_id="service-id",
        apple_team_id="team",
        apple_key_id="key",
        apple_private_key_path="/configured/secret.p8",
    )
    store = AuthMemoryStore()
    app = create_app(settings, store=store)
    with TestClient(app, base_url="https://kiosque.example") as client:
        start = client.get("/v1/auth/apple/start", follow_redirects=False)
        params = parse_qs(urlsplit(start.headers["location"]).query)
        assert params["response_mode"] == ["form_post"]
        assert params["redirect_uri"] == ["https://kiosque.example/v1/auth/apple/callback"]
        assert "SameSite=none" in start.headers["set-cookie"]
        assert "Secure" in start.headers["set-cookie"]

        async def exchange(provider, code, flow):
            assert provider == "apple" and flow["nonce"] == params["nonce"][0]
            return {"sub": "apple-person", "email": "private@privaterelay.appleid.com"}

        monkeypatch.setattr(app.state.oauth, "exchange", exchange)
        response = client.post(
            "/v1/auth/apple/callback",
            data={
                "state": params["state"][0],
                "code": "apple-code",
                "user": json.dumps(
                    {"email": "spoofed@example.com", "name": {"firstName": "Camille"}}
                ),
            },
            headers={"Origin": "https://appleid.apple.com"},
            follow_redirects=False,
        )
        assert response.headers["location"] == settings.auth_public_url
        assert "Secure" in response.headers["set-cookie"]
        account = client.get("/v1/auth/session").json()["account"]
        assert account["email"] == "private@privaterelay.appleid.com"
        assert account["name"] == "Camille"
