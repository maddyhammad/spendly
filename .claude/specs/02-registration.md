# Spec: Step 2 — Registration

> **Status:** Implemented and covered by `tests/test_auth.py`. Hardened on 2026-10-27 per
> `.claude/plans/02-registration.md` (decisions D1–D6). Changed the same day so registration no
> longer logs the user in (see §13). This spec records the required behaviour so later steps
> (and any refactor) can be checked against it.

## 1. Overview
A visitor can create a Spendly account with a name, email and password. On success the account
is saved, but the user is **not** logged in. They are redirected to `/login`, where a one-time
success message asks them to sign in with their new account. Only `/login` starts a session,
through `start_session()`. `/logout` clears the session directly. Login and logout do not have a
spec yet.

## 2. Depends on
Step 1 — Database setup (`users` table, `get_db()`, `UNIQUE` constraint on `users.email`).

## 3. Routes

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/register` | Render `register.html`. Logged-in users are redirected to `/`. |
| `POST` | `/register` | Validate, create the user, flash the welcome message, redirect (302) to `/login`. No session is started. Logged-in users are redirected to `/` before any validation, and no user is created. |
| `GET` | `/login` | (Step 3 route.) Also renders any pending `success` flash above the login form. |

## 4. Database changes
None. Uses the existing
`users(id, name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, created_at)` table.

**Case sensitivity:** the `UNIQUE` index on `users.email` uses SQLite's default `BINARY`
collation, so it is **case-sensitive**. The database does **not** enforce case-insensitive
uniqueness. That comes entirely from the registration route lowercasing every email before
insert, so anything else that inserts users (seed commands, scripts) must apply the same
`strip().lower()`. A `COLLATE NOCASE` constraint would need a full table rebuild and was
deliberately not done (plan D4). As of 2026-10-27 every row in `spendly.db` is already normalised.

## 5. Functions (`database/db.py`)
- `create_user(name, email, password_hash)` — `INSERT` with `?` placeholders. Returns the new id,
  or `None` on **any** `sqlite3.IntegrityError`, after calling `rollback()` on the shared
  per-request connection. Validation runs first and guarantees `name`, `email` and
  `password_hash` are non-null, so in practice only the email `UNIQUE` constraint can fail. The
  constraint decides duplicates, which makes the function race-safe (no check-then-insert).
- `get_user_by_id(user_id)` — used by the `before_request` hook to load `g.user`.

## 6. Changes to `app.py`
- Constants:
  - `EMAIL_PATTERN = ^[^@\s]+@[^@\s]+\.[^@\s]+$`
  - `MIN_PASSWORD_LENGTH = 8`
  - `MAX_PASSWORD_LENGTH = 128`
- `validate_registration(name, email, password)` — returns the first error message (see §11), or `None`.
- `start_session(user_id)` — calls `session.clear()`, then sets `session["user_id"]`. Since this change
  it is used **only by `login()`**. It is the app's session-fixation defence: nothing planted in
  the session before login carries over. (Flask sessions are signed client-side cookies with no
  server-side id, so the defence is about dropping pre-login keys rather than rotating an id.)
- `@app.before_request load_logged_in_user()` — sets `g.user` to the user row, or `None`.
- `register()` route:
  - normalises the input
  - validates it
  - calls `create_user()` with `generate_password_hash(password)`
  - does **not** call `start_session()`
  - calls `flash("Welcome to Spendly! 🎉 Your account has been created successfully. Please sign in to continue.", "success")`
  - returns `redirect(url_for("login"))`

## 7. Templates
- `templates/register.html` extends `base.html`:
  - fields: `name`, `email`, `password`; POSTs to `url_for('register')`
  - shows `{{ error }}` in an `.auth-error` box with `role="alert"`
  - re-fills `name`/`email` (never the password) after an error
  - links to `url_for('login')`
- Autocomplete attributes: `name` → `autocomplete="name"`, `email` → `autocomplete="email"`,
  `password` → `autocomplete="new-password"`.
- Client-side hints **approximate** the server rules: `required`, `maxlength="100"` (name),
  `maxlength="254"` (email), `type="email"`, `minlength="8"` / `maxlength="128"` (password).
  The server is the source of truth. Known differences:
  - `type="email"` accepts `a@b`, which the server rejects
  - `required` accepts a whitespace-only name or password
  - HTML `maxlength` counts UTF-16 code units, before any stripping; Python counts code points
  - control characters in names are only caught server-side
- `templates/base.html` nav: when `g.user` is set it shows "Hi, {name}" (`.nav-user`) and Sign out.
  Otherwise it shows Sign in and Get started.
- `templates/login.html`:
  - Inside `.auth-card`, **above** the error box and the form, it loops over
    `get_flashed_messages(category_filter=["success"])`.
  - Each message is a `.auth-success` box with `role="status"`, holding a round green ✓ badge
    (`.auth-success-icon`, `aria-hidden`) and the text (`.auth-success-text`, autoescaped).
  - Styling: Spendly's green on white (`--accent` / `--accent-light`), a 4px green left border, and
    a short fade-in that is turned off under `prefers-reduced-motion`.
  - The message is removed from the session when it is rendered, so a refresh doesn't show it again.
- Flashes are rendered **only** in `login.html`, not in `base.html`. Rendering them in both would
  show each message twice on the login page, because Flask returns the same messages for every
  call within one request.

## 8. Files to change
- `app.py`, `database/db.py`, `templates/register.html`, `templates/login.html` (success flash),
  `templates/base.html` (nav)
- `static/css/style.css` (`.auth-*` including `.auth-success*`, `.form-*`, `.btn-submit`, `.nav-user`)
- `.claude/commands/seed-user.md` (email normalisation, see §4)

## 9. Files to create
None. Tests live in the existing `tests/test_auth.py` (registration section) and
`tests/test_db.py` (`create_user`). `tests/test_routes.py` also covers `GET /register`.

## 10. Dependencies
No new pip packages. Uses `werkzeug.security` (`generate_password_hash`, scrypt) and these
stdlib modules: `re`, `unicodedata`.

## 11. Validation rules

**Normalisation (before validation):**
- `name` → `strip()`
- `email` → `strip().lower()`
- `password` → **unchanged**. It is never stripped, so leading, trailing and inner spaces are
  part of the password. It is never stored, logged or echoed back.

**Rules,** applied in this order. The first failure is returned.

| # | Rule | Error message | Status |
|---|---|---|---|
| 1 | Any field empty after normalisation (whitespace-only name/email counts as empty) | All fields are required. | 400 |
| 2 | Name longer than 100 chars | Name must be 100 characters or fewer. | 400 |
| 3 | Name contains a control character (Unicode category `Cc`, e.g. NUL, `\n`, `\r`, `\t`, DEL) or a Unicode line/paragraph separator (`Zl`/`Zp`: U+2028, U+2029) | Name contains invalid characters. | 400 |
| 4 | Email longer than 254 chars or not matching `EMAIL_PATTERN` | Please enter a valid email address. | 400 |
| 5 | Password shorter than 8 chars | Password must be at least 8 characters. | 400 |
| 6 | Password longer than 128 chars | Password must be 128 characters or fewer. | 400 |
| 7 | Password is whitespace only (`str.isspace()`) | Password cannot be only spaces. | 400 |
| 8 | Email already registered (see §4 for how case-insensitivity works) | An account with that email already exists. | 409 |

Notes:
- Rules 1–7 live in `validate_registration()`. Rule 8 is detected at insert time by
  `create_user()`, *after* the password has been hashed.
- Leading or trailing characters that are also whitespace (`\n`, `\r`, `\t`, U+2028, U+2029) are
  removed by `strip()` before rule 3 runs. Rule 3 rejects the ones inside the name, and NUL anywhere.
  Format characters (`Cf`, e.g. zero-width joiners) are allowed, because some scripts need them.
- A short whitespace-only password (e.g. 3 spaces) fails rule 5 first.

## 12. Rules for implementation
- All SQL lives in `database/db.py` and uses parameterized queries only.
- Hash passwords with `generate_password_hash()`. Never store plain text.
- Validation errors re-render the form with `error=...` and a 4xx status. They never return a bare string.
- Every internal link uses `url_for()`.
- The session stores only `user_id`, plus Flask's one-time `_flashes` list until it is shown.
- These rules apply to **registration only**. `/login` does not re-validate, so existing accounts keep working.

## 13. Expected behaviour
- A valid POST creates exactly one user with an scrypt hash (`scrypt:` prefix) and returns a
  302 to `/login`. The user is **not** logged in: there is no `session["user_id"]`, and the nav
  still shows Sign in.
- The login page then shows "Welcome to Spendly! 🎉 Your account has been created successfully.
  Please sign in to continue." exactly once, above the form. A refresh doesn't show it again.
- A failed registration (400 or 409) flashes nothing.
- Signing in with the new credentials works as normal (302 to `/`, session started).
- An invalid or duplicate POST creates no user, leaves the visitor logged out and re-renders the
  form with the error.
- A POST from a logged-in user returns a 302 to `/` and creates nothing.
- Boundary values:

  | Field | Accepted | Rejected |
  |---|---|---|
  | Name | 100 chars | 101 chars |
  | Email | 254 chars | 255 chars |
  | Password | 8 and 128 chars | 7 and 129 chars |

- The password `"  pass word  "` is stored exactly. Its hash verifies the padded value, not `"pass word"`.
- `  Asha@Example.COM ` is stored as `asha@example.com`. Registering `  ASHA@Example.com ` afterwards returns 409.

## 14. Definition of done
- [x] `GET /register` renders the form; logged-in users are redirected to `/`
- [x] A POST from a logged-in user redirects to `/` and creates no user
- [x] A valid registration creates a user with an scrypt hash, does **not** log in, and redirects to `/login`
- [x] Email normalised; duplicates rejected case-insensitively with 409
- [x] Every validation rule (1–7) returns 400 with its message and creates no user
- [x] Boundaries: email 254/255, password 128/129, name 100/101
- [x] Passwords are stored exactly as entered; whitespace-only passwords are rejected
- [x] The form keeps name/email on error, never echoes the password, and the error has `role="alert"`
- [x] Nav reflects logged-in state via `g.user`
- [x] The login page shows the welcome message exactly once, above the form, after a successful registration
- [x] `pytest` (full suite) passes

## 15. Out of scope / follow-ups
- After *login*, redirect to `/profile` instead of `/` once Step 4 exists. Registration keeps redirecting to `/login`.
- Optional: pre-fill the login email after registration. This is not done today: the field starts empty.
- CSRF tokens. Required before the expense forms in Steps 7–9.
- Password confirmation field, email verification and rate limiting.
- Kept as-is on purpose (plan K1–K4):
  - the duplicate-email message reveals which emails are registered
  - `create_user()` treats any `IntegrityError` as a duplicate
  - duplicates are detected after hashing
  - emails use `.lower()`, not `casefold()`
