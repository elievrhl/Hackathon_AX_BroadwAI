"""Explicit, local operator administration; never exposed as a signup parameter."""

import argparse

from broadwai.auth import normalize_email
from broadwai.config import Settings
from broadwai.store import Store


def main():
    parser = argparse.ArgumentParser(description="Attribuer ou retirer le rôle administrateur")
    parser.add_argument("action", choices=["promote", "demote"])
    parser.add_argument("email")
    args = parser.parse_args()
    email = normalize_email(args.email)
    store = Store(Settings().database_url.get_secret_value())
    store.open()
    try:
        with store.pool.connection() as db:
            row = db.execute(
                "UPDATE accounts SET is_admin=%s WHERE email=%s RETURNING id",
                (args.action == "promote", email),
            ).fetchone()
        if not row:
            parser.error("Compte introuvable : créer le compte avant de modifier son rôle.")
        print("Rôle mis à jour. Les sessions existantes prennent immédiatement ce rôle en compte.")
    finally:
        store.close()


if __name__ == "__main__":
    main()
