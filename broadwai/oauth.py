"""OIDC authorization-code flows. Provider tokens never enter browser storage."""

import asyncio
import base64
import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse

from broadwai.auth import digest, limit_attempt, normalize_email, start_session

router = APIRouter(prefix="/v1/auth", tags=["Accounts"])
PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "jwks": "https://www.googleapis.com/oauth2/v3/certs",
        "issuer": ["https://accounts.google.com", "accounts.google.com"],
    },
    "apple": {
        "authorize": "https://appleid.apple.com/auth/authorize",
        "token": "https://appleid.apple.com/auth/token",
        "jwks": "https://appleid.apple.com/auth/keys",
        "issuer": "https://appleid.apple.com",
    },
}


class OAuth:
    def __init__(self, settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=15, follow_redirects=False)
        self.keys = {}

    def providers(self):
        s = self.settings
        host = urlsplit(s.auth_public_url).hostname
        try:
            ipaddress.ip_address(host)
            public_host = False
        except ValueError:
            public_host = host != "localhost"
        return {
            "google": bool(
                s.google_client_id
                and s.google_client_secret
                and s.google_client_secret.get_secret_value()
            ),
            "apple": bool(
                s.apple_client_id
                and s.apple_team_id
                and s.apple_key_id
                and s.apple_private_key_path
                and public_host
                and s.auth_public_url.startswith("https://")
            ),
        }

    def client_id(self, provider):
        return getattr(self.settings, provider + "_client_id")

    def callback_url(self, provider):
        url = urlsplit(self.settings.auth_public_url)
        return f"{url.scheme}://{url.netloc}/v1/auth/{provider}/callback"

    def client_secret(self, provider):
        if provider == "google":
            return self.settings.google_client_secret.get_secret_value()
        s = self.settings
        now = int(time.time())
        return jwt.encode(
            {
                "iss": s.apple_team_id,
                "iat": now,
                "exp": now + 300,
                "aud": "https://appleid.apple.com",
                "sub": s.apple_client_id,
            },
            Path(s.apple_private_key_path).read_text(),
            algorithm="ES256",
            headers={"kid": s.apple_key_id},
        )

    async def verify_token(self, provider, encoded, nonce):
        config = PROVIDERS[provider]
        header = jwt.get_unverified_header(encoded)
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise ValueError("invalid_token")
        cached = self.keys.get(provider)
        if cached is None or cached[0] < time.monotonic():
            response = await self.client.get(config["jwks"])
            response.raise_for_status()
            cached = (time.monotonic() + 300, response.json()["keys"])
            self.keys[provider] = cached
        key = next((k for k in cached[1] if k.get("kid") == header["kid"]), None)
        if key is None:
            self.keys.pop(provider, None)
            raise ValueError("unknown_signing_key")
        claims = jwt.decode(
            encoded,
            jwt.PyJWK.from_dict(key).key,
            algorithms=["RS256"],
            audience=self.client_id(provider),
            issuer=config["issuer"],
            leeway=30,
            options={"require": ["exp", "iat", "iss", "aud", "sub", "nonce"]},
        )
        if not hmac.compare_digest(claims["nonce"], nonce):
            raise ValueError("invalid_nonce")
        if claims.get("azp", self.client_id(provider)) != self.client_id(provider):
            raise ValueError("invalid_authorized_party")
        if claims.get("email_verified") not in (True, "true"):
            raise ValueError("unverified_email")
        if not isinstance(claims["sub"], str) or not claims["sub"]:
            raise ValueError("missing_subject")
        claims["email"] = normalize_email(claims.get("email", ""))
        return claims

    async def exchange(self, provider, code, flow):
        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": self.client_id(provider),
            "client_secret": self.client_secret(provider),
            "redirect_uri": self.callback_url(provider),
        }
        if provider == "google":
            payload["code_verifier"] = flow["verifier"]
        result = await self.client.post(PROVIDERS[provider]["token"], data=payload)
        result.raise_for_status()
        return await self.verify_token(provider, result.json()["id_token"], flow["nonce"])


def flow_cookie(provider):
    return f"kiosque_oauth_{provider}"


@router.get("/{provider}/start")
async def begin(provider: str, request: Request):
    oauth = request.app.state.oauth
    if not oauth.providers().get(provider):
        raise HTTPException(503, "Ce mode de connexion est momentanément indisponible.")
    await limit_attempt(request, "oauth")
    state, browser, nonce, verifier = (secrets.token_urlsafe(32) for _ in range(4))
    await asyncio.to_thread(
        request.app.state.store.begin_oauth,
        digest(state),
        provider,
        digest(browser),
        nonce,
        verifier,
    )
    params = {
        "client_id": oauth.client_id(provider),
        "redirect_uri": oauth.callback_url(provider),
        "response_type": "code",
        "state": state,
        "nonce": nonce,
    }
    if provider == "google":
        params.update(
            scope="openid email profile",
            code_challenge_method="S256",
            code_challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("="),
        )
    else:
        params.update(scope="name email", response_mode="form_post")
    response = RedirectResponse(PROVIDERS[provider]["authorize"] + "?" + urlencode(params), 303)
    response.set_cookie(
        flow_cookie(provider),
        browser,
        max_age=600,
        httponly=True,
        secure=oauth.settings.auth_public_url.startswith("https:"),
        samesite="none" if provider == "apple" else "lax",
        path="/v1/auth",
    )
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return response


@router.api_route("/{provider}/callback", methods=["GET", "POST"])
async def callback(provider: str, request: Request):
    oauth = request.app.state.oauth
    if not oauth.providers().get(provider):
        raise HTTPException(503, "Ce mode de connexion est momentanément indisponible.")
    error = "oauth_failed"
    account = None
    try:
        if provider == "apple":
            if request.method != "POST":
                raise ValueError("invalid_callback_method")
            body = await request.body()
            if len(body) > 16000:
                raise ValueError("oversized_callback")
            data = {key: values[0] for key, values in parse_qs(body.decode()).items()}
        else:
            if request.method != "GET":
                raise ValueError("invalid_callback_method")
            data = dict(request.query_params)
        state = data.get("state", "")
        browser = request.cookies.get(flow_cookie(provider), "")
        if not state or not browser:
            raise ValueError("missing_state")
        flow = await asyncio.to_thread(
            request.app.state.store.consume_oauth, digest(state), provider, digest(browser)
        )
        if flow is None:
            raise ValueError("expired_or_replayed_state")
        if data.get("error"):
            error = "oauth_cancelled"
            raise ValueError("provider_error")
        claims = await oauth.exchange(provider, data["code"], flow)
        name = claims.get("name") or claims["email"].split("@")[0]
        if provider == "apple" and data.get("user"):
            supplied = json.loads(data["user"]).get("name", {})
            name = " ".join(str(supplied.get(part, "")) for part in ("firstName", "lastName"))
        name = str(name).strip()[:80] or "Lecteur"
        try:
            account = await asyncio.to_thread(
                request.app.state.store.oauth_account,
                provider,
                claims["sub"],
                claims["email"],
                name,
            )
        except ValueError:
            error = "email_in_use"
    except (ValueError, KeyError, TypeError, OSError, jwt.PyJWTError, httpx.HTTPError):
        pass  # Never echo provider codes, tokens, credentials or remote error bodies.
    target = oauth.settings.auth_public_url
    if account is None:
        target += "?" + urlencode({"auth_error": error})
    response = RedirectResponse(target, 303)
    response.delete_cookie(flow_cookie(provider), path="/v1/auth")
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    if account is not None:
        await start_session(request, response, account)
    return response
