import os
import re
import sqlite3

import pytest

from app import app as flask_app
from database.db import create_user, get_db, init_db

USERS_COLUMNS = ["id", "name", "email", "password_hash", "created_at"]
EXPENSES_COLUMNS = ["id", "user_id", "amount", "category", "date", "description", "created_at"]

_LEGACY_TABLES = """
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);
CREATE TABLE expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
);
INSERT INTO categories (name) VALUES ('Food'), ('Travel');
"""

# The original Step 1 schema: no password column at all.
SCHEMA_V0 = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
""" + _LEGACY_TABLES + """
INSERT INTO users (name, email) VALUES ('John Doe', 'john@example.com');
INSERT INTO expenses (user_id, category_id, amount, date, description)
VALUES (1, 1, 12.5, '2026-10-01', 'Lunch'), (1, 2, 80.0, '2026-10-02', 'Train');
"""

# The schema after the auth work: nullable password_hash, still categories/category_id.
# Also has a real hash to preserve and a deleted user whose id must not be reused.
SCHEMA_V1 = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT
);
""" + _LEGACY_TABLES + """
INSERT INTO users (name, email) VALUES ('John Doe', 'john@example.com');
INSERT INTO users (name, email, password_hash)
VALUES ('Asha Rao', 'asha@example.com', 'scrypt:32768:8:1$salt$hash');
INSERT INTO users (name, email, password_hash) VALUES ('Temp', 'temp@example.com', 'x');
DELETE FROM users WHERE email = 'temp@example.com';
INSERT INTO expenses (user_id, category_id, amount, date, description)
VALUES (1, 1, 12.5, '2026-10-01', 'Lunch'), (1, 2, 80.0, '2026-10-02', 'Train');
"""


def columns(db, table):
    return [row["name"] for row in db.execute("SELECT name FROM pragma_table_info(?)", (table,))]


def table_names(db):
    return {row["name"] for row in db.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def snapshot(path):
    """Full SQL dump (schema + every row), read through a separate connection."""
    con = sqlite3.connect(path)
    dump = list(con.iterdump())
    con.close()
    return dump


@pytest.fixture
def legacy_db(tmp_path, monkeypatch):
    """Point the app at a database built from a legacy schema script."""
    def make(script):
        path = tmp_path / "legacy.db"
        con = sqlite3.connect(path)
        con.executescript(script)
        con.close()
        monkeypatch.setitem(flask_app.config, "DATABASE", str(path))
        return path
    return make


# ------------------------------------------------------------------ #
# Configuration and fresh schema                                      #
# ------------------------------------------------------------------ #

def test_database_path_is_absolute_spendly_db_in_project():
    path = flask_app.config["DATABASE"]
    assert os.path.isabs(path)
    assert os.path.basename(path) == "spendly.db"
    assert os.path.dirname(path) == flask_app.root_path


def test_fresh_schema_matches_spec(app):
    with app.app_context():
        db = get_db()
        assert columns(db, "users") == USERS_COLUMNS
        assert columns(db, "expenses") == EXPENSES_COLUMNS
        assert table_names(db) == {"users", "expenses", "sqlite_sequence"}

        user_info = {r["name"]: r for r in db.execute("SELECT * FROM pragma_table_info('users')")}
        assert user_info["password_hash"]["notnull"] == 1
        assert user_info["created_at"]["dflt_value"] == "datetime('now')"
        expense_info = {r["name"]: r for r in db.execute("SELECT * FROM pragma_table_info('expenses')")}
        assert expense_info["category"]["notnull"] == 1
        assert expense_info["amount"]["type"] == "REAL"
        assert expense_info["created_at"]["dflt_value"] == "datetime('now')"


def test_init_db_is_idempotent_and_never_seeds(app):
    with app.app_context():
        init_db()
        init_db()
        db = get_db()
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


# ------------------------------------------------------------------ #
# Constraints                                                         #
# ------------------------------------------------------------------ #

def test_created_at_defaults_to_now(app):
    with app.app_context():
        create_user("Asha Rao", "asha@example.com", "hash")
        created_at = get_db().execute("SELECT created_at FROM users").fetchone()[0]
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", created_at)


def test_password_hash_is_required(app):
    with app.app_context():
        with pytest.raises(sqlite3.IntegrityError):
            get_db().execute(
                "INSERT INTO users (name, email) VALUES (?, ?)", ("No Hash", "nohash@example.com")
            )


def test_duplicate_email_violates_unique(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("A", "same@example.com", "hash"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("B", "same@example.com", "hash"),
            )


def test_create_user_returns_none_for_duplicate_email(app):
    with app.app_context():
        first = create_user("A", "same@example.com", "hash")
        second = create_user("B", "same@example.com", "hash")
        count = get_db().execute("SELECT COUNT(*) FROM users").fetchone()[0]
    assert first is not None
    assert second is None
    assert count == 1


def test_email_unique_is_case_sensitive_at_db_level(app):
    # Case-insensitive uniqueness comes from /register lowercasing emails, not from
    # the schema. If this starts failing, update CLAUDE.md and the Step 2 spec.
    with app.app_context():
        assert create_user("A", "same@example.com", "hash") is not None
        assert create_user("B", "SAME@example.com", "hash") is not None


def test_foreign_keys_are_enforced(app):
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO expenses (user_id, amount, category, date) VALUES (?, ?, ?, ?)",
                (999, 1.0, "Food", "2026-10-01"),
            )


# ------------------------------------------------------------------ #
# Migration from older schemas                                        #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize("script", [SCHEMA_V0, SCHEMA_V1], ids=["v0-no-password", "v1-categories"])
def test_migration_brings_legacy_schema_to_spec(legacy_db, script):
    legacy_db(script)

    with flask_app.app_context():
        init_db()
        init_db()  # running it twice must be a no-op
        db = get_db()

        assert columns(db, "users") == USERS_COLUMNS
        assert columns(db, "expenses") == EXPENSES_COLUMNS
        assert table_names(db) == {"users", "expenses", "sqlite_sequence"}

        john = db.execute("SELECT * FROM users WHERE email = 'john@example.com'").fetchone()
        assert (john["id"], john["name"], john["password_hash"]) == (1, "John Doe", "!")
        assert john["created_at"]

        expenses = [
            (r["id"], r["user_id"], r["amount"], r["category"], r["date"], r["description"])
            for r in db.execute("SELECT * FROM expenses ORDER BY id")
        ]
        assert expenses == [
            (1, 1, 12.5, "Food", "2026-10-01", "Lunch"),
            (2, 1, 80.0, "Other", "2026-10-02", "Train"),  # "Travel" isn't a valid category
        ]
        assert all(r["created_at"] for r in db.execute("SELECT created_at FROM expenses"))

        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migration_keeps_password_hashes_and_never_reuses_ids(legacy_db):
    legacy_db(SCHEMA_V1)

    with flask_app.app_context():
        init_db()
        db = get_db()
        asha = db.execute("SELECT * FROM users WHERE email = 'asha@example.com'").fetchone()
        assert (asha["id"], asha["password_hash"]) == (2, "scrypt:32768:8:1$salt$hash")

        # id 3 belonged to a deleted user; AUTOINCREMENT must continue from it.
        assert create_user("New", "new@example.com", "hash") == 4


def test_migration_cascade_still_works(legacy_db):
    legacy_db(SCHEMA_V1)

    with flask_app.app_context():
        init_db()
        db = get_db()
        db.execute("DELETE FROM users WHERE id = 1")
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_migration_failure_rolls_back_completely(legacy_db):
    # An orphaned expense (user 99 doesn't exist) makes the post-rebuild FK check fail.
    path = legacy_db(
        SCHEMA_V1
        + "INSERT INTO expenses (user_id, category_id, amount, date) VALUES (99, 1, 1.0, '2026-10-03');"
    )
    before = snapshot(path)

    with flask_app.app_context():
        with pytest.raises(sqlite3.IntegrityError, match="foreign key violations"):
            init_db()
        assert get_db().execute("PRAGMA foreign_keys").fetchone()[0] == 1

    assert snapshot(path) == before
