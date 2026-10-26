"""Database helper module for Spendly.

This module provides a simple wrapper around SQLite using Flask's application context.
It implements:

- :func:`get_db` – opens a SQLite connection for the current request, enables
  foreign‑key enforcement and caches the connection in ``flask.g``.
- :func:`close_db` – closes that connection when the app context ends.
- :func:`init_db` – creates the required tables if they do not yet exist and
  applies pending migrations.
- :func:`migrate_db` – brings databases created by older versions of the app up
  to the current schema without losing rows.
- :func:`seed_db` – inserts the demo user and sample expenses for development.
- User helpers – :func:`get_user_by_id`, :func:`get_user_by_email` and
  :func:`create_user`.

The design follows the boilerplate pattern shown in Flask's documentation:

>>> from flask import current_app, g
>>> import sqlite3

The DB path is taken from the Flask app's ``DATABASE`` config key; the tests
point it at a temporary file.
"""

import sqlite3
from datetime import date

from flask import g, current_app
from werkzeug.security import generate_password_hash

# The only valid values for ``expenses.category``.
CATEGORIES = ("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")

# Stored in ``users.password_hash`` for accounts that must not be able to log in.
# It never matches ``check_password_hash()``.
UNUSABLE_PASSWORD = "!"

DEMO_NAME = "Demo User"
DEMO_EMAIL = "demo@spendly.com"
DEMO_PASSWORD = "demo123"

# (category, amount, description) – one per category, plus a second Food entry.
SAMPLE_EXPENSES = (
    ("Food", 450.00, "Groceries"),
    ("Transport", 120.00, "Metro card top-up"),
    ("Bills", 2499.00, "Electricity bill"),
    ("Health", 850.00, "Pharmacy"),
    ("Entertainment", 499.00, "Movie tickets"),
    ("Shopping", 1899.00, "New shoes"),
    ("Other", 300.00, "Gift wrapping"),
    ("Food", 650.00, "Dinner with friends"),
)

USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
)
"""

EXPENSES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    date TEXT NOT NULL,
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
)
"""


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
    Existing databases are brought up to date by :func:`migrate_db`.  It never
    seeds data; call :func:`seed_db` for that.
    """
    db = get_db()
    db.execute(USERS_TABLE_SQL)
    db.execute(EXPENSES_TABLE_SQL)
    db.commit()
    migrate_db()


def _columns(db, table):
    return {
        row["name"]
        for row in db.execute("SELECT name FROM pragma_table_info(?)", (table,))
    }


def migrate_db():
    """Bring a database created by an older version of the app up to date.

    Each stage checks the current columns first, so this is idempotent and a
    no-op on a database created by :func:`init_db`.  Existing rows are always
    preserved.
    """
    db = get_db()
    # Stage A: the original schema had no password column.
    if "password_hash" not in _columns(db, "users"):
        db.execute("ALTER TABLE users ADD COLUMN password_hash TEXT")
        db.commit()
    # Stage B: category_id/categories → category TEXT, created_at, NOT NULL password_hash.
    if "category_id" in _columns(db, "expenses") or "created_at" not in _columns(db, "users"):
        _rebuild_to_current_schema(db)


def _rebuild_to_current_schema(db):
    """Rebuild ``users`` and ``expenses`` with the current schema, copying all rows.

    SQLite cannot change constraints or drop a column used by a foreign key, so
    the old tables are renamed aside, recreated from ``USERS_TABLE_SQL`` /
    ``EXPENSES_TABLE_SQL``, filled from the old ones and the old ones dropped –
    all in one transaction that is rolled back on any error.  Both tables are
    rebuilt together, so no other table is left referencing a renamed one.
    Foreign keys are switched off meanwhile so dropping the old tables does not
    cascade-delete rows.
    """
    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")  # no-op inside a transaction
    try:
        db.execute("BEGIN")
        old_seq = {
            row["name"]: row["seq"]
            for row in db.execute(
                "SELECT name, seq FROM sqlite_sequence WHERE name IN ('users', 'expenses')"
            )
        }
        db.execute("ALTER TABLE expenses RENAME TO expenses_old")
        db.execute("ALTER TABLE users RENAME TO users_old")

        db.execute(USERS_TABLE_SQL)
        db.execute(
            "INSERT INTO users (id, name, email, password_hash, created_at) "
            "SELECT id, name, email, COALESCE(password_hash, ?), datetime('now') "
            "FROM users_old",
            (UNUSABLE_PASSWORD,),
        )

        db.execute(EXPENSES_TABLE_SQL)
        old_expenses = db.execute(
            "SELECT e.id, e.user_id, e.amount, c.name AS category, e.date, e.description "
            "FROM expenses_old e LEFT JOIN categories c ON c.id = e.category_id"
        ).fetchall()
        db.executemany(
            "INSERT INTO expenses "
            "(id, user_id, amount, category, date, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, datetime('now'))",
            [
                (
                    row["id"],
                    row["user_id"],
                    row["amount"],
                    # Categories outside the fixed list (e.g. "Travel") become "Other".
                    row["category"] if row["category"] in CATEGORIES else "Other",
                    row["date"],
                    row["description"],
                )
                for row in old_expenses
            ],
        )

        db.execute("DROP TABLE expenses_old")
        db.execute("DROP TABLE users_old")
        db.execute("DROP TABLE IF EXISTS categories")

        # Keep AUTOINCREMENT counters so ids of deleted rows are never reused.
        for table, seq in old_seq.items():
            current = db.execute(
                "SELECT seq FROM sqlite_sequence WHERE name = ?", (table,)
            ).fetchone()
            if current is None:
                db.execute(
                    "INSERT INTO sqlite_sequence (name, seq) VALUES (?, ?)", (table, seq)
                )
            elif current["seq"] < seq:
                db.execute(
                    "UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (seq, table)
                )

        violations = db.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise sqlite3.IntegrityError(
                "foreign key violations after rebuild: "
                + repr([tuple(row) for row in violations])
            )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def seed_db():
    """Insert the demo user and sample expenses for development.

    Idempotent – returns early if the demo user already exists, so repeated
    calls (e.g. every app start) never duplicate data.  Expense dates are spread
    across the current month up to today, formatted ``YYYY-MM-DD``.
    """
    db = get_db()
    if db.execute("SELECT 1 FROM users WHERE email = ?", (DEMO_EMAIL,)).fetchone():
        return

    today = date.today()
    last = len(SAMPLE_EXPENSES) - 1
    try:
        cursor = db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (DEMO_NAME, DEMO_EMAIL, generate_password_hash(DEMO_PASSWORD)),
        )
        user_id = cursor.lastrowid
        rows = [
            (
                user_id,
                amount,
                category,
                today.replace(day=1 + (today.day - 1) * i // last).isoformat(),
                description,
            )
            for i, (category, amount, description) in enumerate(SAMPLE_EXPENSES)
        ]
        db.executemany(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise


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
