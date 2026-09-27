"""Database helper module for Spendly.

This module provides a simple wrapper around SQLite using Flask's application context.
It implements:

- :func:`get_db` – opens a SQLite connection for the current request, enables
  foreign‑key enforcement and caches the connection in ``flask.g``.
- :func:`init_db` – creates the required tables if they do not yet exist.
- :func:`seed_db` – inserts basic seed data for development.

The design follows the boilerplate pattern shown in Flask's documentation:

>>> from flask import current_app, g
>>> import sqlite3

The DB path is taken from the Flask app's ``DATABASE`` config key; when the app is
configured for the tests we use an in‑memory SQLite instance.
"""

import sqlite3
from flask import g, current_app


def get_db():
    """Return a SQLite connection for the current request.

    The connection is stored in :data:`flask.g` so that subsequent calls within the
    same request reuse the same socket.  The connection's `row_factory` is set to
    :class:`sqlite3.Row` to provide dictionary‑like access.
    """
    if "db" not in g:
        db_path = current_app.config["DATABASE"]
        g.db = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES,
        )
        g.db.row_factory = sqlite3.Row
        # SQLite foreign key support must be turned on per connection
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def init_db():
    """Create the database schema.

    The function is idempotent – ``CREATE TABLE IF NOT EXISTS`` is used for each
    table.  This makes repeated calls safe during development and in tests.
    """
    db = get_db()
    # SQLite syntax for table creation; all constraints are in the same statement.
    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );

    CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        category_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        date TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
    );
    """
    db.executescript(schema_sql)
    db.commit()


def seed_db():
    """Insert sample data for development.

    The data is idempotent – duplicates are avoided using ``INSERT OR IGNORE`` when
    appropriate.  Only a minimal dataset is inserted to keep the example
    lightweight.
    """
    db = get_db()
    # Insert a sample user if not already present.
    db.execute(
        "INSERT OR IGNORE INTO users (name, email) VALUES (?, ?)",
        ("John Doe", "john@example.com"),
    )
    # Insert a couple of categories.
    db.execute(
        "INSERT OR IGNORE INTO categories (name) VALUES (?)",
        ("Food",),
    )
    db.execute(
        "INSERT OR IGNORE INTO categories (name) VALUES (?)",
        ("Travel",),
    )
    db.commit()
