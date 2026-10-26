import os
import sqlite3

import pytest

from app import app as flask_app
from database.db import get_db, init_db

LEGACY_SCHEMA = """
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE
);
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
INSERT INTO users (name, email) VALUES ('John Doe', 'john@example.com');
INSERT INTO categories (name) VALUES ('Food'), ('Travel');
INSERT INTO expenses (user_id, category_id, amount, date, description)
VALUES (1, 1, 12.5, '2026-10-01', 'Lunch');
"""


def user_columns(db):
    return [row["name"] for row in db.execute("PRAGMA table_info(users)")]


def test_database_path_is_absolute_spendly_db_in_project():
    path = flask_app.config["DATABASE"]
    assert os.path.isabs(path)
    assert os.path.basename(path) == "spendly.db"
    assert os.path.dirname(path) == flask_app.root_path


def test_fresh_database_has_password_hash_column(app):
    with app.app_context():
        assert "password_hash" in user_columns(get_db())


def test_migration_adds_password_hash_and_preserves_data(tmp_path, monkeypatch):
    legacy_path = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_path) as con:
        con.executescript(LEGACY_SCHEMA)
    con.close()
    monkeypatch.setitem(flask_app.config, "DATABASE", str(legacy_path))

    with flask_app.app_context():
        init_db()
        init_db()  # running it twice must be a no-op
        db = get_db()

        assert user_columns(db) == ["id", "name", "email", "password_hash"]
        users = [dict(row) for row in db.execute("SELECT * FROM users")]
        assert users == [
            {"id": 1, "name": "John Doe", "email": "john@example.com", "password_hash": None}
        ]
        categories = [row["name"] for row in db.execute("SELECT name FROM categories ORDER BY id")]
        assert categories == ["Food", "Travel"]
        expense = db.execute("SELECT * FROM expenses").fetchone()
        assert (expense["user_id"], expense["amount"], expense["description"]) == (1, 12.5, "Lunch")


def test_foreign_keys_are_enforced(app):
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO expenses (user_id, category_id, amount, date) VALUES (?, ?, ?, ?)",
                (999, 999, 1.0, "2026-10-01"),
            )
