"""Cookie sessions and authorization for reader and administration endpoints."""

import asyncio
import hashlib
import hmac
import secrets
from datetime import timedelta
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, HTTPException, Request, Response
from psycopg.errors import UniqueViolation
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from broadwai.models import utcnow

router = APIRouter(prefix="/v1/auth", tags=["Accounts"])
SESSION_COOKIE = "kiosque_session"
PASSWORDS = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token):
    return hmac.new(token.encode(), b"kiosque-csrf-v1", hashlib.sha256).hexdigest()


def public_account(account):
    return {key: account[key] for key in ("id", "email", "name", "is_admin", "reader_profile")}


def normalize_email(value):
    try:
        return validate_email(value.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError as exc:
        raise ValueError("Indiquez une adresse e-mail valide.") from exc


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(max_length=254)
    password: SecretStr = Field(min_length=1, max_length=128)

    _email = field_validator("email")(normalize_email)


class Registration(Credentials):
    name: str = Field(min_length=1, max_length=80)
    password: SecretStr = Field(min_length=12, max_length=128)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        if not value.strip():
            raise ValueError("Indiquez votre prénom.")
        return value.strip()


class ReaderProfile(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    topics: list[str] = Field(min_length=1, max_length=30)
    languages: list[str] = Field(default_factory=lambda: ["fr"], min_length=1, max_length=5)
    notes: str = Field("", max_length=2000)
    size: int = Field(18, ge=1, le=30)

    @field_validator("name")
    @classmethod
    def valid_name(cls, value):
        return Registration.valid_name(value)

    @field_validator("topics", "languages")
    @classmethod
    def bounded_values(cls, values):
        if any(not value.strip() or len(value) > 100 for value in values):
            raise ValueError("Valeur de préférence invalide")
        return list(dict.fromkeys(values))


class ProfileUpdate(BaseModel):
    profile: ReaderProfile | None


def check_origin(request):
    origin = request.headers.get("origin")
    configured = urlsplit(request.app.state.settings.auth_public_url)
    expected = f"{configured.scheme}://{configured.netloc}"
    if origin and origin != expected:
        raise HTTPException(403, "Origine de la requête non autorisée.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(403, "Requête intersite non autorisée.")


def check_csrf(request):
    check_origin(request)
    token = request.cookies.get(SESSION_COOKIE, "")
    supplied = request.headers.get("x-kiosque-csrf", "")
    if not token or not hmac.compare_digest(csrf_token(token), supplied):
        raise HTTPException(403, "Rechargez la page avant de réessayer.")


async def account_for_request(request):
    token = request.cookies.get(SESSION_COOKIE, "")
    if not token or len(token) > 256:
        return None
    return await asyncio.to_thread(request.app.state.store.session_account, digest(token))


async def require_account(request):
    account = await account_for_request(request)
    if not account:
        raise HTTPException(401, "Connectez-vous pour retrouver votre journal.")
    request.state.account = account
    return account


async def authorize_request(request: Request):
    """Applied to all API routes; body/query IDs cannot grant access to another reader."""
    path = request.url.path
    if path in {"/", "/health", "/v1/source-directory"} or path.startswith("/v1/auth/"):
        return
    account = await require_account(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_csrf(request)
    admin_only = path.startswith(("/admin", "/v1/admin", "/v1/sources", "/v1/source-proposals"))
    admin_only = admin_only or path in {"/v1/ingest", "/v1/articles"}
    if admin_only and not account["is_admin"]:
        raise HTTPException(403, "Cet espace est réservé à l’administration.")
    if account["is_admin"]:
        return
    identities = [request.path_params.get("user_id"), *request.query_params.getlist("user_id")]
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    # Match FastAPI's JSON parsing. Binary dictation is bounded by its endpoint;
    # do not buffer the audio here merely to inspect JSON identity fields.
    json_body = not content_type or content_type == "application/json" or (
        content_type.startswith("application/") and content_type.endswith("+json")
    )
    if request.method in {"POST", "PUT", "PATCH"} and json_body:
        try:
            body = await request.json()
        except ValueError:
            body = None
        if isinstance(body, dict):
            identities.append(body.get("user_id"))
            if isinstance(body.get("profile"), dict):
                identities.append(body["profile"].get("user_id"))
    if any(identity is not None and identity != account["id"] for identity in identities):
        raise HTTPException(403, "Vous ne pouvez accéder qu’à votre propre compte.")


async def limit_attempt(request, action, email=None):
    store = request.app.state.store
    ip = request.client.host if request.client else "unknown"
    checks = [(f"{action}:ip:{ip}", 40, 900)]
    if email:
        checks.append((f"{action}:email:{email}", 10, 900))
    for key, limit, seconds in checks:
        if not await asyncio.to_thread(store.auth_attempt, digest(key), limit, seconds):
            raise HTTPException(
                429,
                "Trop de tentatives. Réessayez dans quinze minutes.",
                headers={"Retry-After": str(seconds)},
            )


async def start_session(request, response, account):
    old = request.cookies.get(SESSION_COOKIE)
    if old:
        await asyncio.to_thread(request.app.state.store.revoke_session, digest(old))
    token = secrets.token_urlsafe(48)
    settings = request.app.state.settings
    lifetime = timedelta(days=settings.auth_session_days)
    await asyncio.to_thread(
        request.app.state.store.create_session, digest(token), account["id"], utcnow() + lifetime
    )
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(lifetime.total_seconds()),
        httponly=True,
        secure=settings.auth_public_url.startswith("https:"),
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"account": public_account(account), "csrf_token": csrf_token(token)}


@router.get("/session")
async def session(request: Request, response: Response):
    account = await account_for_request(request)
    response.headers["Cache-Control"] = "no-store"
    return {
        "account": public_account(account) if account else None,
        "csrf_token": csrf_token(request.cookies[SESSION_COOKIE]) if account else None,
    }


def check_auth_submission(request):
    check_origin(request)
    # A custom header prevents cross-site HTML forms, including login CSRF.
    if request.headers.get("x-kiosque-request") != "1":
        raise HTTPException(403, "Rechargez la page avant de réessayer.")


@router.post("/register", status_code=201)
async def register(value: Registration, request: Request, response: Response):
    check_auth_submission(request)
    await limit_attempt(request, "register", value.email)
    password_hash = await asyncio.to_thread(PASSWORDS.hash, value.password.get_secret_value())
    try:
        account = await asyncio.to_thread(
            request.app.state.store.create_account, value.email, value.name, password_hash
        )
    except UniqueViolation as exc:
        raise HTTPException(409, "Cette adresse possède déjà un compte. Connectez-vous.") from exc
    return await start_session(request, response, account)


@router.post("/login")
async def login(value: Credentials, request: Request, response: Response):
    check_auth_submission(request)
    await limit_attempt(request, "login", value.email)
    account = await asyncio.to_thread(request.app.state.store.account_by_email, value.email)
    encoded = (account or {}).get("password_hash") or DUMMY_HASH
    try:
        await asyncio.to_thread(PASSWORDS.verify, encoded, value.password.get_secret_value())
    except (VerificationError, InvalidHashError) as exc:
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.") from exc
    if not account or not account["password_hash"]:
        raise HTTPException(401, "Adresse e-mail ou mot de passe incorrect.")
    return await start_session(request, response, account)


@router.post("/logout", status_code=204)
async def logout(request: Request):
    check_csrf(request)
    await asyncio.to_thread(
        request.app.state.store.revoke_session, digest(request.cookies[SESSION_COOKIE])
    )
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


@router.put("/profile")
async def update_profile(value: ProfileUpdate, request: Request, response: Response):
    account = await require_account(request)
    check_csrf(request)
    updated = await asyncio.to_thread(
        request.app.state.store.save_account_profile,
        account["id"],
        value.profile.model_dump() if value.profile else None,
    )
    response.headers["Cache-Control"] = "no-store"
    return {"account": public_account(updated)}
