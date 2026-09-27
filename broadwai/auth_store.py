"""PostgreSQL account, session and single-use OAuth storage."""

from datetime import timedelta
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from broadwai.models import utcnow


class AuthStore:
    def account_by_email(self, email):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute("SELECT * FROM accounts WHERE email=%s", (email,)).fetchone()

    def create_account(self, email, name, password_hash):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "INSERT INTO accounts(id,email,name,password_hash) VALUES (%s,%s,%s,%s) "
                "RETURNING *",
                (uuid4().hex, email, name, password_hash),
            ).fetchone()

    def oauth_account(self, provider, subject, email, name):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s, 20))",
                (f"{provider}:{subject}",),
            )
            # Serialize signup across providers without trusting an unverified local email.
            cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 19))", (email,))
            existing = cur.execute(
                "SELECT a.* FROM accounts a JOIN account_identities i ON i.account_id=a.id "
                "WHERE i.provider=%s AND i.subject=%s",
                (provider, subject),
            ).fetchone()
            if existing:
                return existing
            if cur.execute("SELECT id FROM accounts WHERE email=%s", (email,)).fetchone():
                raise ValueError("email_in_use")
            account = cur.execute(
                "INSERT INTO accounts(id,email,name,email_verified) VALUES (%s,%s,%s,true) "
                "RETURNING *",
                (uuid4().hex, email, name),
            ).fetchone()
            cur.execute(
                "INSERT INTO account_identities(provider,subject,account_id) VALUES (%s,%s,%s)",
                (provider, subject, account["id"]),
            )
            return account

    def save_account_profile(self, account_id, profile):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "UPDATE accounts SET reader_profile=%s, name=COALESCE(%s,name) "
                "WHERE id=%s RETURNING *",
                (
                    Jsonb(profile) if profile is not None else None,
                    profile.get("name") if profile else None,
                    account_id,
                ),
            ).fetchone()

    def create_session(self, token_hash, account_id, expires_at):
        with self.pool.connection() as db:
            db.execute("DELETE FROM account_sessions WHERE expires_at <= now()")
            db.execute(
                "INSERT INTO account_sessions(token_hash,account_id,expires_at) VALUES (%s,%s,%s)",
                (token_hash, account_id, expires_at),
            )

    def session_account(self, token_hash):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "SELECT a.* FROM account_sessions s JOIN accounts a ON a.id=s.account_id "
                "WHERE s.token_hash=%s AND s.expires_at > now()",
                (token_hash,),
            ).fetchone()

    def revoke_session(self, token_hash):
        with self.pool.connection() as db:
            db.execute("DELETE FROM account_sessions WHERE token_hash=%s", (token_hash,))

    def begin_oauth(self, state_hash, provider, browser_hash, nonce, verifier):
        with self.pool.connection() as db:
            db.execute("DELETE FROM oauth_flows WHERE expires_at <= now()")
            db.execute(
                "INSERT INTO oauth_flows VALUES (%s,%s,%s,%s,%s,%s)",
                (
                    state_hash,
                    provider,
                    browser_hash,
                    nonce,
                    verifier,
                    utcnow() + timedelta(minutes=10),
                ),
            )

    def consume_oauth(self, state_hash, provider, browser_hash):
        with self.pool.connection() as db, db.cursor(row_factory=dict_row) as cur:
            return cur.execute(
                "DELETE FROM oauth_flows WHERE state_hash=%s AND provider=%s "
                "AND browser_hash=%s AND expires_at > now() RETURNING *",
                (state_hash, provider, browser_hash),
            ).fetchone()

    def auth_attempt(self, key, limit, seconds):
        with self.pool.connection() as db:
            db.execute("DELETE FROM auth_rate_limits WHERE expires_at <= now()")
            row = db.execute(
                "INSERT INTO auth_rate_limits(key,attempts,expires_at) VALUES (%s,1,%s) "
                "ON CONFLICT(key) DO UPDATE SET attempts=auth_rate_limits.attempts+1 "
                "RETURNING attempts",
                (key, utcnow() + timedelta(seconds=seconds)),
            ).fetchone()
            return row[0] <= limit
