from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import UniqueViolation

from broadwai.api import create_app
from broadwai.auth import PASSWORDS, digest
from broadwai.config import Settings
from broadwai.models import utcnow
from tests.test_auth import HEADERS, ORIGIN, PASSWORD, register


def test_accounts_sessions_and_profiles_persist_in_postgres(pg_store):
    settings = Settings(_env_file=None, openai_api_key=None)
    with TestClient(
        create_app(settings, store=pg_store), base_url=ORIGIN, headers=HEADERS
    ) as first:
        account = register(first)
        profile = {
            "name": "Camille",
            "topics": ["tech"],
            "languages": ["fr"],
            "notes": "",
            "size": 18,
        }
        assert first.put("/v1/auth/profile", json={"profile": profile}).status_code == 200
        token = first.cookies.get("kiosque_session")
    # A new application instance and browser recover the same account and profile.
    with TestClient(
        create_app(settings, store=pg_store), base_url=ORIGIN, headers=HEADERS
    ) as second:
        logged = second.post(
            "/v1/auth/login", json={"email": account["email"], "password": PASSWORD}
        )
        assert logged.status_code == 200
        assert logged.json()["account"]["id"] == account["id"]
        assert logged.json()["account"]["reader_profile"] == profile
    assert pg_store.session_account(digest(token))["id"] == account["id"]
    pg_store.revoke_session(digest(token))
    assert pg_store.session_account(digest(token)) is None
    pg_store.create_session("expired", account["id"], utcnow() - timedelta(seconds=1))
    assert pg_store.session_account("expired") is None
    with pytest.raises(UniqueViolation):
        pg_store.create_account(account["email"], "Other", PASSWORDS.hash(PASSWORD))


def test_login_attempt_limits_persist_in_postgres(pg_store):
    assert pg_store.auth_attempt("limit", 2, 900)
    assert pg_store.auth_attempt("limit", 2, 900)
    assert not pg_store.auth_attempt("limit", 2, 900)
