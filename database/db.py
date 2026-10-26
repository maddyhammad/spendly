"""Database helper module for Spendly.

This module provides a simple wrapper around SQLite using Flask's application context.
It implements:

- :func:`get_db` – opens a SQLite connection for the current request, enables
  foreign‑key enforcement and caches the connection in ``flask.g``.
- :func:`close_db` – closes that connection when the app context ends.
- :func:`init_db` – creates the required tables if they do not yet exist and
  applies pending migrations.
- :func:`migrate_db` – additive schema changes for databases created by older
  versions of the app.
- :func:`seed_db` – inserts basic seed data for development.
- User helpers – :func:`get_user_by_id`, :func:`get_user_by_email` and
  :func:`create_user`.

The design follows the boilerplate pattern shown in Flask's documentation:

>>> from flask import current_app, g
>>> import sqlite3

The DB path is taken from the Flask app's ``DATABASE`` config key; the tests
point it at a temporary file.
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


def close_db(e=None):
    """Close the connection opened by :func:`get_db`, if any.

    Registered with ``app.teardown_appcontext`` so it runs after every request
    and CLI command.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the database schema.

    The function is idempotent – ``CREATE TABLE IF NOT EXISTS`` is used for each
    table.  This makes repeated calls safe during development and in tests.
    Existing databases are brought up to date by :func:`migrate_db`.
    """
    db = get_db()
    # SQLite syntax for table creation; all constraints are in the same statement.
    schema_sql = """
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        password_hash TEXT
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
    migrate_db()


def migrate_db():
    """Apply additive schema changes to databases created by older versions.

    Only ever adds columns – existing rows are left untouched, so this is safe
    to run against a database that already holds real data.
    """
    db = get_db()
    user_columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if "password_hash" not in user_columns:
        # Nullable because rows created before auth existed have no password.
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
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


def get_user_by_id(user_id):
    """Return the user row with ``user_id``, or ``None``."""
    return get_db().execute(
        "SELECT id, name, email, password_hash FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()


def get_user_by_email(email):
    """Return the user row with ``email``, or ``None``.

    Callers are expected to pass an already normalised (lower‑cased) email.
    """
    return get_db().execute(
        "SELECT id, name, email, password_hash FROM users WHERE email = ?",
        (email,),
    ).fetchone()


def create_user(name, email, password_hash):
    """Insert a new user and return its id.

    Returns ``None`` when the email is already registered (the ``UNIQUE``
    constraint on ``users.email`` is the source of truth, so this is race‑safe).
    """
    db = get_db()
    try:
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
    except sqlite3.IntegrityError:
        db.rollback()
        return None
    db.commit()
    return cursor.lastrowid
