"""Non-destructive, local PostgreSQL catalogue snapshots for paired paid evaluations."""

import argparse
import re

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from broadwai.config import Settings
from broadwai.store import Store


def scoped_url(database_url, schema):
    if not re.fullmatch(r"audit_[a-z0-9_]{1,50}", schema):
        raise ValueError("The destination must be an isolated audit_ schema")
    return make_conninfo(database_url, options=f"-c search_path={schema}")


def clone_catalog(database_url, source, destination):
    scoped = scoped_url(database_url, destination)
    if source != "public":
        scoped_url(database_url, source)
    with psycopg.connect(database_url, connect_timeout=5) as db:
        # No IF NOT EXISTS: never overwrite or reuse an audit accidentally.
        db.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(destination)))
    store = Store(scoped)
    try:
        store.open()
        with store.pool.connection() as db:
            db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            for table in ("articles", "briefs", "sources", "source_articles", "source_proposals"):
                db.execute(
                    sql.SQL("INSERT INTO {}.{} SELECT * FROM {}.{}").format(
                        sql.Identifier(destination),
                        sql.Identifier(table),
                        sql.Identifier(source),
                        sql.Identifier(table),
                    )
                )
        print(f"SNAPSHOT {source} -> {destination}: {store.stats()}", flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--source", default="public")
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    clone_catalog(
        Settings(_env_file=args.env_file).database_url.get_secret_value(),
        args.source,
        args.destination,
    )
