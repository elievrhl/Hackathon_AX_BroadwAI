import os
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from broadwai.store import Store


@pytest.fixture
def pg_store():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL requis pour les tests PostgreSQL réels")
    schema = "test_" + uuid4().hex
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as db:
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = Store(make_conninfo(url, options=f"-c search_path={schema}"))
    try:
        store.open()
        yield store
    finally:
        store.close()
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as db:
            db.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
