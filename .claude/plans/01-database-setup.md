# Implementation Plan — Step 1: Database Setup

- **Spec:** `.claude/specs/01-database-setuo.md`
- **Inputs read:** spec, `database/db.py`, `app.py` (as of commit `0e46f25`), live `spendly.db` (read-only)
- **Date:** 2026-10-26
- **Status:** ✅ Implemented 2026-10-26 — all recommendations in §3 approved; real `spendly.db`
  migrated and seeded (backup: `..\backups\spendly.db.pre-step1-20261026.bak`)

---

## 1. Goal

Bring the data layer in line with the spec — schema, `seed_db()` behaviour and startup
initialisation — **without losing anything in the existing `spendly.db`** and without breaking
the auth work (register / login / logout) that is already built on top of it.

---

## 2. Current state vs spec

| Area | Spec | Current code / DB | Gap |
|---|---|---|---|
| `users.password_hash` | `TEXT NOT NULL` | `TEXT` (nullable) — added by `ALTER` | Needs table rebuild (SQLite has no `ALTER COLUMN`) |
| `users.created_at` | `TEXT DEFAULT datetime('now')` | missing | Can't `ADD COLUMN` with that default on a non-empty table → rebuild |
| `expenses.category` | `TEXT NOT NULL`, fixed list | `category_id INTEGER` → `categories(id)` | Needs table rebuild (FK blocks `DROP COLUMN`) |
| `expenses.created_at` | `TEXT DEFAULT datetime('now')` | missing | Part of the same rebuild |
| `categories` table | not in spec | exists: `Food`, `Travel` | Becomes unused — drop (D2) |
| `get_db()` | `spendly.db`, `Row`, FK on | ✅ already (absolute path via `app.config["DATABASE"]`) | none |
| `init_db()` | `CREATE TABLE IF NOT EXISTS`, idempotent | ✅ + calls `migrate_db()` | schema text only |
| `seed_db()` | demo user + 8 expenses, once | John Doe + 2 categories, no expenses | Rewrite |
| Startup | `init_db()` + `seed_db()` in app context | none — only `flask --app app init-db` | Add (see D5 for *where*) |
| Fixed categories | Food, Transport, Bills, Health, Entertainment, Shopping, Other | Food, Travel | Add `CATEGORIES` constant |

**Live `spendly.db` today:** `users` 1 row (`1, John Doe, john@example.com, password_hash NULL`),
`categories` 2 rows (Food, Travel), `expenses` 0 rows, `user_version` 0, FK check clean.

---

## 3. Decisions

### Need your call

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| **D1** | What happens to John Doe (no password) when `password_hash` becomes `NOT NULL`? | **Keep him**, store the unusable-password marker `"!"`. Werkzeug's `check_password_hash("!", …)` returns `False` (verified), so he still can't log in, and the row is preserved. | Delete him (he's leftover seed data, not a real account). |
| **D2** | Drop the `categories` table? | **Drop it** inside the rebuild transaction, *after* `expenses` no longer references it (with FKs off, so nothing cascades). It only holds the two old seed rows. | Keep it as an unused table. |
| **D3** | Demo password: spec says `demo123` (7 chars) but registration requires ≥ 8. | **Keep `demo123`** as the spec says — login doesn't apply the length rule, so it works, and later course steps likely quote it. *(Earlier I suggested `demo1234`; on reflection, matching the spec causes less friction.)* | Use `demo1234` and update the spec. |

### Technical — required for correctness, deviate from spec wording

| # | Decision | Why |
|---|---|---|
| **D4** | `seed_db()` returns early if **the demo email** exists, not if `users` has *any* rows. | With John Doe in the DB, the spec's check would never seed anything. Still idempotent. |
| **D5** | Startup `init_db()` + `seed_db()` go in the `if __name__ == "__main__":` block, not at module level. | `tests/conftest.py` imports `app` *before* it points `DATABASE` at a temp file, so module-level calls would run the migration and seed against the real `spendly.db` on every `pytest` run. `python app.py` (the documented way to run) still initialises on startup. `flask run` won't — use `flask --app app init-db` there. |
| **D6** | `migrate_db()` may rebuild tables (SQLite's documented copy → drop → rename procedure) in one transaction. | Only way to reach the spec schema. Requires rewording the CLAUDE.md rule "never drop, rename or recreate tables". |
| **D7** | Legacy expense categories not on the fixed list (e.g. `Travel`) map to `Other` during migration. | Keeps `category` within the fixed list. No effect today — there are 0 expenses. |
| **D8** | No DB `CHECK` constraint on `category`; enforce the list in Python via `CATEGORIES` (Step 7 form validation). | Spec only requires UNIQUE + FK at DB level; a `CHECK` would force another rebuild to change the list. |
| **D9** | `app.py` imports `init_db, seed_db` but **not** `get_db`. | Spec lists `get_db`, but `app.py` doesn't use it — an unused import. |

---

## 4. Target schema

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expenses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount REAL NOT NULL,
    category TEXT NOT NULL,
    date TEXT NOT NULL,              -- YYYY-MM-DD
    description TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

`ON DELETE CASCADE` is kept from the current schema (the spec doesn't say either way): deleting a
user removes their expenses.

---

## 5. Implementation steps

### 5.1 `database/db.py`

1. **Constants**
   ```python
   CATEGORIES = ("Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other")
   UNUSABLE_PASSWORD = "!"          # D1 — never matches check_password_hash
   DEMO_NAME = "Demo User"
   DEMO_EMAIL = "demo@spendly.com"
   DEMO_PASSWORD = "demo123"        # D3
   ```
2. **`init_db()`** — replace the schema script with §4 (drop the `categories` CREATE). Still calls
   `migrate_db()` afterwards. Must **not** call `seed_db()` (tests rely on an empty `users` table).
3. **`migrate_db()`** — two stages, each detected by inspecting columns (`PRAGMA table_info`), so it
   is idempotent and a no-op on fresh databases:
   - **Stage A (existing):** if `users` lacks `password_hash`, `ALTER TABLE users ADD COLUMN password_hash TEXT`.
     Brings the oldest schema up to the current shape so Stage B has one input shape.
   - **Stage B (new):** if `expenses` has `category_id` **or** `users` lacks `created_at`, call
     `_rebuild_to_current_schema(db)`.
   - Update the docstring — it is no longer "additive only".
4. **`_rebuild_to_current_schema(db)`** (new, private) — *as implemented*:
   1. `db.commit()` to close any implicit transaction; `PRAGMA foreign_keys = OFF`
      (only takes effect outside a transaction — prevents the cascade that `DROP TABLE` would trigger).
   2. `BEGIN`; read the old `sqlite_sequence` values for `users` / `expenses`.
   3. Rename the old tables aside: `expenses` → `expenses_old`, `users` → `users_old`.
      *(Changed from "create `*_new` then rename" so each table is created from the single
      `USERS_TABLE_SQL` / `EXPENSES_TABLE_SQL` constant without string-formatting table names into
      SQL. Safe because both tables that reference each other are rebuilt together; SQLite 3.45
      renames the UNIQUE autoindex with the table.)*
   4. `CREATE` `users` from `USERS_TABLE_SQL`; copy rows with
      `COALESCE(password_hash, ?)` → `UNUSABLE_PASSWORD` (D1) and `created_at = datetime('now')`.
   5. `CREATE` `expenses` from `EXPENSES_TABLE_SQL`; read old rows with `LEFT JOIN categories`, map
      names outside `CATEGORIES` (and NULLs) to `Other` **in Python** (D7), insert with `executemany`.
   6. `DROP TABLE expenses_old`, `DROP TABLE users_old`, `DROP TABLE IF EXISTS categories` (D2).
   7. Restore `sqlite_sequence` so AUTOINCREMENT ids are never reused (only raised, never lowered).
   8. `PRAGMA foreign_key_check` — if it returns any row, raise `IntegrityError`.
   9. `COMMIT`; on **any** exception `ROLLBACK` and re-raise (Stage B leaves the DB exactly as before;
      Stage A's additive `ADD COLUMN`, if it ran, is committed separately and stays).
   10. `finally: PRAGMA foreign_keys = ON`.
   - All values go through `?` placeholders; no f-strings / `.format` in SQL. Column lookups use
     `SELECT name FROM pragma_table_info(?)`.
   - ⚠ Future tables that reference `users` or `expenses` must be rebuilt in this same function,
     or the rename would leave their FK pointing at a dropped `*_old` table.
5. **`seed_db()`** — rewrite:
   - Return early if `SELECT 1 FROM users WHERE email = ?` (DEMO_EMAIL) finds a row (D4).
   - Insert the demo user with `generate_password_hash(DEMO_PASSWORD)` (`werkzeug.security`).
   - Insert 8 expenses for that user with `executemany`, **one transaction**, single `commit()`:

     | # | Category | Amount (₹) | Description |
     |---|---|---|---|
     | 1 | Food | 450.00 | Groceries |
     | 2 | Transport | 120.00 | Metro card top-up |
     | 3 | Bills | 2499.00 | Electricity bill |
     | 4 | Health | 850.00 | Pharmacy |
     | 5 | Entertainment | 499.00 | Movie tickets |
     | 6 | Shopping | 1899.00 | New shoes |
     | 7 | Other | 300.00 | Gift wrapping |
     | 8 | Food | 650.00 | Dinner with friends |

   - Dates: spread across the current month **up to today** (never in the future):
     `day = 1 + (today.day - 1) * i // 7` for `i = 0..7`, formatted with `date.isoformat()` → `YYYY-MM-DD`.
6. **User helpers** (`get_user_by_id`, `get_user_by_email`, `create_user`) — no change needed.
7. Update the module docstring (constants, seed contents, rebuild migration).

### 5.2 `app.py`

1. Import `seed_db` alongside `init_db` (D9: not `get_db`).
2. Startup (D5):
   ```python
   if __name__ == "__main__":
       with app.app_context():
           init_db()
           seed_db()
       app.run(debug=True, port=5001)
   ```
   Under the debug reloader this runs twice (parent + child) — harmless, both calls are idempotent.
3. Login guard comment (`app.py:107`) → mention the `"!"` marker as well as legacy `NULL`s.
   Keep the `not user["password_hash"]` check — `check_password_hash(None, …)` raises.
4. `init-db` CLI command — unchanged.

### 5.3 Tests

**`tests/test_db.py`**
- Replace `LEGACY_SCHEMA` with two fixtures-as-SQL: **V0** (original, no `password_hash`) and
  **V1** (today's live shape: nullable `password_hash`, `categories`, `category_id`), each seeded with
  John Doe, Food/Travel and two expenses (one Food, one Travel).
- `test_migration_from_v0_and_v1` (parametrised): after `init_db()` twice →
  exact spec column lists for `users` and `expenses`; no `categories` table; John Doe kept with
  `password_hash == "!"` and non-null `created_at`; expenses kept with `category` Food / Other;
  `foreign_key_check` empty; `integrity_check` ok; FK enforcement still on.
- `test_migration_failure_rolls_back` — force an error mid-rebuild (e.g. monkeypatch to raise
  before `COMMIT`) and assert the DB is byte-for-byte / row-for-row unchanged.
- `test_fresh_schema_matches_spec` — exact columns, `NOT NULL` on `password_hash`, defaults present.
- `test_foreign_keys_are_enforced` — switch the insert from `category_id` to `category`.
- New: `test_duplicate_email_violates_unique`, `test_password_hash_is_required`
  (insert without it → `IntegrityError`), `test_created_at_defaults`.

**New `tests/test_seed.py`**
- Demo user created with a scrypt hash that verifies `demo123`.
- Exactly 8 expenses, all linked to the demo user, all 7 categories present, amounts are `float`,
  dates match `YYYY-MM-DD`, lie in the current month and are ≤ today.
- Idempotent: `seed_db()` twice → still 1 demo user, 8 expenses.
- Seeds even when another user (John Doe) already exists (D4).

**`tests/test_auth.py`**
- `test_login_user_without_password_hash_is_rejected` → insert with `"!"` (NULL is no longer
  allowed) and rename to `..._with_unusable_password_...`.
- New: after `seed_db()`, `demo@spendly.com` / `demo123` logs in (302 + session).
- Existing tests that assume an empty `users` table stay valid because `init_db()` never seeds.

### 5.4 `CLAUDE.md`

- Database section: new schema, `CATEGORIES`, seed contents + demo credentials, startup behaviour
  (D5), `"!"` marker (D1), `categories` table removed.
- Migration rule (D6): replace "never drop, rename or recreate tables" with: schema changes go through
  `migrate_db()`; table rebuilds are allowed only there, inside one transaction with FKs off,
  `foreign_key_check` before commit, rollback on error, and a manual backup of `spendly.db` first.
- Authentication section: replace the "NULL password_hash" note with the `"!"` marker.

---

## 6. Runbook — migrating the real `spendly.db`

1. **Backup first**, outside the repo so `git add .` can never pick it up:
   `C:\Users\user\Downloads\expense-tracker\backups\spendly.db.pre-step1-20261026.bak` — record its sha256.
2. Run the full test suite — every test uses a temp DB; confirm `spendly.db`'s hash is unchanged afterwards.
3. Start the app once: `python app.py` → migration + seed run.
4. Verify read-only:
   - schema matches §4; `categories` gone; `integrity_check` = ok; `foreign_key_check` empty
   - user 1 = John Doe, unchanged except `password_hash = "!"` and new `created_at`
   - user 2 = Demo User with a scrypt hash; 8 expenses across all 7 categories, dates this month
5. HTTP smoke test on port 5001: demo login → 302; John Doe login → 401; register/logout still work.
   (Write tests against a scratch copy of the DB so no test users land in `spendly.db`.)
6. Restart the app → still 2 users, 8 expenses (no duplicate seed).
7. Hand test verification to a subagent (CLAUDE.md policy).

**Rollback:** stop the server, copy the `.bak` file back over `spendly.db`.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Rebuild fails half-way and corrupts data | Single transaction + rollback; FK check before commit; manual backup (§6.1); failure-path test |
| `DROP TABLE` cascades and deletes expenses | `PRAGMA foreign_keys = OFF` set *before* `BEGIN`; tables dropped only after rows are copied |
| Tests touch the real DB | Startup calls only under `__main__` (D5); runbook step 2 checks the hash |
| Migrated rows get `created_at` = migration time, not true creation time | Unavoidable — the data never existed. Documented. |
| Spec/code drift again | Plan lists every deviation (D1–D9); update the spec afterwards if you want them reflected there |

---

## 8. Out of scope (noticed, not touched)

- Spec formatting: §4 tables are flattened one cell per line; §11 "Hash passwords using:" has lost its
  code line; filename typo `setuo`.
- `templates/landing.html` mock card: bars sum to ₹11,550 but the total shows ₹12,450.
- Expense routes (Steps 7–9) — this plan only prepares the schema and `CATEGORIES` for them.
