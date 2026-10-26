# CLAUDE.md

## Project overview

Spendly is a lightweight personal expense tracker built with Flask and SQLite.

---

## Architecture
```
expense-tracker/            # repo root — github.com/maddyhammad/spendly
├── app.py                  # All routes + auth helpers — single file, no blueprints
├── database/
│   ├── __init__.py
│   └── db.py               # SQLite helpers (see "Database" below)
├── templates/
│   ├── base.html           # Shared layout — all templates must extend this
│   ├── landing.html
│   ├── register.html
│   ├── login.html
│   ├── terms.html
│   └── privacy.html
├── static/
│   ├── css/
│   │   ├── style.css       # Global styles
│   │   └── landing.css     # Landing-page-only styles
│   └── js/
│       └── main.js         # Vanilla JS only (currently an empty placeholder)
├── tests/                  # pytest suite — every test gets its own temp DB
│   ├── conftest.py
│   ├── test_auth.py
│   ├── test_db.py          # schema, constraints, migrations
│   ├── test_routes.py
│   └── test_seed.py
├── spendly.db              # The active SQLite database (gitignored)
└── requirements.txt
```

**Where things belong:**
- New routes → `app.py` only, no blueprints
- DB logic → `database/db.py` only, never inline in routes
- New pages → new `.html` file extending `base.html`
- Page-specific styles → new `.css` file, not inline `<style>` tags
- Tests → `tests/test_*.py`, using the `app` / `client` fixtures from `conftest.py`

---

## Code style

- Python: PEP 8, snake_case for all variables and functions
- Templates: Jinja2 with `url_for()` for every internal link — never hardcode URLs
- Route functions: one responsibility only — fetch data, render template, done
- DB queries: always use parameterized queries (`?` placeholders) — never f-strings in SQL
- Error handling: use `abort()` for HTTP errors, not bare `return "error string"`.
  Form validation errors are the exception: re-render the form with `error=...`
  and a 4xx status (see `register()` / `login()`).

---

## Tech constraints

- **Flask only** — no FastAPI, no Django, no other web frameworks
- **SQLite only** — no PostgreSQL, no SQLAlchemy ORM, no external DB
- **Vanilla JS only** — no React, no jQuery, no npm packages
- **No new pip packages** — work within `requirements.txt` as-is unless explicitly told otherwise
- Python 3.10+ assumed — f-strings and `match` statements are fine (the current venv is 3.11.9)

---

## Subagent Policy
- Always use a builtin explore subagent for codebase exploration
  before implementing any new feature
- Always use a subagent to verify test results
  after any implementation
- When asked to plan, delegate codebase research
  to a subagent before presenting the plan
- always use a builtin plan subagent in plan mode

---

## Commands
```bash
# Setup — the existing venv lives one level up (..\venv), outside the repo
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Create tables and apply migrations — idempotent, never loses rows (does not seed)
flask --app app init-db

# Run dev server (port 5001) — runs init_db() + seed_db() first
python app.py

# Run all tests
pytest

# Run a specific test file
pytest tests/test_auth.py

# Run a specific test by name
pytest -k "test_name"

# Run tests with output visible
pytest -s
```

---

## Database

- **File:** `spendly.db` in the project root. `app.py` sets
  `app.config["DATABASE"] = os.path.join(app.root_path, "spendly.db")` — an absolute
  path, so the app and `flask init-db` use the same file whatever the working directory.
- **Spec / plan:** `.claude/specs/01-database-setuo.md`, `.claude/plans/01-database-setup.md`
  (the plan lists every deliberate deviation from the spec, D1–D9).
- **Schema** (`USERS_TABLE_SQL` / `EXPENSES_TABLE_SQL` in `db.py`):
  - `users(id, name, email UNIQUE, password_hash NOT NULL, created_at DEFAULT datetime('now'))`
  - `expenses(id, user_id → users ON DELETE CASCADE, amount REAL, category TEXT NOT NULL,
    date TEXT 'YYYY-MM-DD', description, created_at DEFAULT datetime('now'))`
  - There is no `categories` table. Valid categories are the `CATEGORIES` tuple:
    Food, Transport, Bills, Health, Entertainment, Shopping, Other — validate against it in Python.
- **Helpers in `database/db.py`:**
  - `get_db()` — one connection per app context, cached in `g`, `row_factory = sqlite3.Row`,
    runs `PRAGMA foreign_keys = ON`
  - `close_db()` — registered with `app.teardown_appcontext`; closes the connection
  - `init_db()` — `CREATE TABLE IF NOT EXISTS`, then `migrate_db()`. Never seeds.
  - `migrate_db()` — upgrades older databases; idempotent, detects work by inspecting columns
  - `seed_db()` — demo user + 8 sample expenses (one per category + an extra Food), dated this
    month up to today; returns early if the demo email already exists
  - `get_user_by_id(user_id)`, `get_user_by_email(email)` — return a row or `None`
  - `create_user(name, email, password_hash)` — returns the new id, or `None` if the
    email is already registered
- **Startup:** `python app.py` runs `init_db()` + `seed_db()` inside the `__main__` block only.
  Never move them to module level — tests import `app` before pointing `DATABASE` at a temp
  file, so module-level calls would migrate/seed the real `spendly.db` on every `pytest` run.
- **Migrations:** every schema change goes through `migrate_db()` and must preserve rows.
  Prefer `ALTER TABLE ... ADD COLUMN`. When SQLite can't do it in place (constraint changes,
  dropping an FK column, non-constant defaults on non-empty tables), a table rebuild is allowed
  **only** inside `migrate_db()` and must: run in one transaction with `PRAGMA foreign_keys = OFF`
  set before `BEGIN`, rebuild every table that references the rebuilt one, preserve
  `sqlite_sequence`, pass `PRAGMA foreign_key_check` before `COMMIT`, roll back on any error,
  and have a test that it rolls back. Back up `spendly.db` (outside the repo) before running
  a new rebuild against it.

---

## Authentication

- Passwords are hashed with Werkzeug `generate_password_hash()` (scrypt) and checked with
  `check_password_hash()`. Never store or log plain-text passwords.
- Emails are normalised (`strip().lower()`) on both register and login.
- Validation (server-side, `validate_registration()` in `app.py`): name 1–100 chars,
  email matches `EMAIL_PATTERN` and ≤ 254 chars, password ≥ `MIN_PASSWORD_LENGTH` (8).
- The session stores only `user_id`. `start_session()` clears the session before setting
  it (prevents session fixation). A `before_request` hook loads `g.user` (or `None`);
  templates check `g.user` — `base.html` uses it to switch the nav.
- Logged-in users hitting `/login` or `/register` are redirected to `/`. After register or
  login the user is sent to `/` — change this to the profile page once Step 4 exists.
- Accounts that must not log in store the marker `"!"` (`UNUSABLE_PASSWORD` in `db.py`) in
  `password_hash` — it never matches a password. John Doe (id 1, from the old seed) has it.
- **Demo login:** `demo@spendly.com` / `demo123` (created by `seed_db()`). It is shorter than
  the 8-char registration minimum on purpose — the spec fixes it and login doesn't check length.
- `SECRET_KEY` comes from the `SECRET_KEY` environment variable. Without it a random key is
  generated per process, so everyone is logged out whenever the dev server restarts or reloads.
- Session cookie: `HttpOnly` (Flask default) and `SameSite=Lax`. There are no CSRF tokens
  yet — add them before building the expense forms (Steps 7–9).

---

## Implemented vs stub routes

| Route | Status |
|---|---|
| `GET /` | Implemented — renders `landing.html` |
| `GET, POST /register` | Implemented — validates, creates user, logs in, redirects to `/` |
| `GET, POST /login` | Implemented — checks password hash, redirects to `/` |
| `GET /logout` | Implemented (Step 3) — clears the session, redirects to `/` |
| `GET /terms` | Implemented — renders `terms.html` |
| `GET /privacy` | Implemented — renders `privacy.html` |
| `GET /profile` | Stub — Step 4 |
| `GET /expenses/add` | Stub — Step 7 |
| `GET /expenses/<int:id>/edit` | Stub — Step 8 |
| `GET /expenses/<int:id>/delete` | Stub — Step 9 |
| `flask --app app init-db` | CLI — creates tables and applies migrations (no seeding) |

**Do not implement a stub route unless the active task explicitly targets that step.**

---

## Warnings and things to avoid

- **Never use raw string returns for stub routes** once a step is implemented — always render a template
- **Never hardcode URLs** in templates — always use `url_for()`
- **Never put DB logic in route functions** — it belongs in `database/db.py`
- **Never install new packages** mid-feature without flagging it — keep `requirements.txt` in sync
- **Never use JS frameworks** — the frontend is intentionally vanilla
- **Never delete or reset `spendly.db`** — schema changes go through `migrate_db()` (see Database)
- **FK enforcement is manual** — SQLite foreign keys are off by default; `get_db()` runs
  `PRAGMA foreign_keys = ON` on every connection, so always go through `get_db()`
- **Never commit a venv or nested project copies** — a `Downloads/` duplicate (plus a venv)
  was once pulled in from a stray Git repo in the home folder and had to be removed
- The app runs on **port 5001**, not the Flask default 5000 — don't change this
