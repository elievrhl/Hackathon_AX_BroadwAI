from datetime import timedelta
from uuid import uuid4

from psycopg.errors import UniqueViolation

from broadwai.models import utcnow
from tests.fakes import MemoryStore


class AuthMemoryStore(MemoryStore):
    def __init__(self, articles=()):
        super().__init__(articles)
        self.accounts = {}
        self.sessions = {}
        self.identities = {}
        self.flows = {}
        self.attempts = {}

    def account_by_email(self, email):
        return next((a for a in self.accounts.values() if a["email"] == email), None)

    def create_account(self, email, name, password_hash):
        if self.account_by_email(email):
            raise UniqueViolation()
        account = dict(
            id=uuid4().hex,
            email=email,
            name=name,
            password_hash=password_hash,
            is_admin=False,
            reader_profile=None,
            email_verified=False,
        )
        self.accounts[account["id"]] = account
        return account

    def oauth_account(self, provider, subject, email, name):
        existing = self.identities.get((provider, subject))
        if existing:
            return self.accounts[existing]
        if self.account_by_email(email):
            raise ValueError("email_in_use")
        account = self.create_account(email, name, None)
        account["email_verified"] = True
        self.identities[provider, subject] = account["id"]
        return account

    def save_account_profile(self, account_id, profile):
        self.accounts[account_id]["reader_profile"] = profile
        if profile:
            self.accounts[account_id]["name"] = profile["name"]
        return self.accounts[account_id]

    def create_session(self, token_hash, account_id, expires_at):
        self.sessions[token_hash] = account_id, expires_at

    def session_account(self, token_hash):
        value = self.sessions.get(token_hash)
        return self.accounts[value[0]] if value and value[1] > utcnow() else None

    def revoke_session(self, token_hash):
        self.sessions.pop(token_hash, None)

    def begin_oauth(self, state_hash, provider, browser_hash, nonce, verifier):
        self.flows[state_hash] = dict(
            provider=provider,
            browser_hash=browser_hash,
            nonce=nonce,
            verifier=verifier,
            expires_at=utcnow() + timedelta(minutes=10),
        )

    def consume_oauth(self, state_hash, provider, browser_hash):
        value = self.flows.get(state_hash)
        if (
            value
            and value["provider"] == provider
            and value["browser_hash"] == browser_hash
            and value["expires_at"] > utcnow()
        ):
            return self.flows.pop(state_hash)

    def auth_attempt(self, key, limit, seconds):
        self.attempts[key] = self.attempts.get(key, 0) + 1
        return self.attempts[key] <= limit
