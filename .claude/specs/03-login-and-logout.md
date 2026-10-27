# Spec: Step 3 — Login and Logout

> **Status:** ✅ Implemented on `feature/login-and-logout`. All 96 tests pass, a subagent
> verified the work, and §14 awaits only your browser check. Login already existed on `main`
> (as of `9719673`). Step 3:
> - makes logout POST-only, with a one-time sign-out message
> - gives the login form the same accessibility and autocomplete attributes as the register form
> - adds tests for every behaviour below
>
> Decisions D1–D7 and their reasons are in `.claude/plans/03-login-and-logout.md`.

## 1. Overview
A registered user signs in with their email and password, which starts a session. Signing out
ends it, and the login page then shows a one-time "You've been signed out." message.
Registration (Step 2) never logs the user in. It redirects to `/login` with a one-time welcome
message, so `/login` is the only way to start a session.

## 2. Depends on
- Step 1: the `users` table, `get_db()`, `UNUSABLE_PASSWORD` (`"!"`), and the demo user from `seed_db()`.
- Step 2: accounts created by `/register`, its flash message, `.auth-*` styles.

## 3. Routes

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/login` | Render `login.html`, including any pending flash. Logged-in users are redirected (302) to `/`. |
| `POST` | `/login` | Check the credentials. On success, start a session and redirect (302) to `/`. On failure, re-render the form with an error (400 or 401). Logged-in users are redirected to `/` before any check. |
| `POST` | `/logout` | If the session holds a `user_id`: clear the whole session, flash "You've been signed out." and redirect (302) to `/login`. Otherwise: redirect (302) to `/login` without touching the session (no flash, no `Set-Cookie`). |
| `GET` | `/logout` | 405 Method Not Allowed (Flask's default page). The session is untouched. |

## 4. Database changes
None. Reads `users` through `get_user_by_email()` and `get_user_by_id()`. Login and logout never write to the database.

## 5. Functions (`database/db.py`)
- `get_user_by_email(email)`:
  - exact-match lookup (`WHERE email = ?`), so the caller must pass an email that is already normalised
  - returns `id, name, email, password_hash`, or `None`
- `get_user_by_id(user_id)` — used by the `before_request` hook. Returns the row, or `None` if the user no longer exists.

## 6. `app.py`
- **`start_session(user_id)`** — `session.clear()`, then `session["user_id"] = user_id`.
  - Called **only** by `login()`.
  - It is the app's session-fixation defence: no key planted before login survives. Flask
    sessions are signed client-side cookies, so this works by dropping old keys rather than by
    rotating a server-side id.
  - It also drops a pending flash. If a user logs in without the login page rendering it first,
    the message is discarded. In a browser, the redirect to `/login` always renders it first.
- **`load_logged_in_user()`** (`@app.before_request`) — sets `g.user` to the user row, or `None`.
  - If the session holds a `user_id` whose user was deleted, `g.user` is `None`, so the visitor is treated as logged out.
  - The stale id stays in the cookie until the next login or a logout POST, and it is harmless.
    The nav shows no Sign out button to a deleted user, because `g.user` is `None`.
    - AUTOINCREMENT never reuses ids, and the migration preserves `sqlite_sequence`.
    - The exception is when `spendly.db` is deleted and recreated while a fixed `SECRET_KEY` is set.
- **`login()`**:
  1. If `g.user`, redirect to `/`.
  2. `GET` → render `login.html`.
  3. Normalise the input:
     - email: `strip().lower()`, the same as `/register`
     - password: used **as typed**, never stripped
  4. Empty email or password → 400 "Email and password are required.", with the email re-filled.
  5. `get_user_by_email(email)`. Reject with 401 "Invalid email or password." (email re-filled) if any of these is true:
     - there is no such user
     - `password_hash` is NULL or empty. The explicit `not user["password_hash"]` check exists for
       NULL, because `check_password_hash(None, …)` raises. An empty string just fails the check.
       NULL can't occur after `init_db()`: the column is `NOT NULL`, and the migration maps old NULLs
       to `"!"`. The guard is cheap insurance.
     - `check_password_hash()` fails, which also covers the `"!"` marker
  6. Success: `start_session(user["id"])`, then redirect to `/`.
- **`logout()`** — `methods=["POST"]` only.
  1. If `"user_id" in session` (including a stale id for a deleted user):
     - `session.clear()`
     - then `flash("You've been signed out.", "success")`, in that order, or the clear would wipe the message
  2. Otherwise, leave the session alone. Flask sends a delete-cookie `Set-Cookie` even when
     `session.clear()` runs on an empty session. Skipping the clear is what stops another site from
     signing the user out (§12).
  3. Redirect to `/login` either way.
- **No length or format validation at login.**
  - `validate_registration()` is registration-only, so existing accounts always keep working.
  - Example: the demo password `demo123` is 7 characters, below the registration minimum of 8.

## 7. Templates
- **`templates/login.html`** extends `base.html`. Order inside `.auth-card`:
  1. **Flashes.** A `get_flashed_messages(category_filter=["success"])` loop renders each message
     as `.auth-success` with `role="status"`.
     - The call removes **every** pending flash from the session, but shows only `success` ones.
       `success` is the only category flashed today.
     - So the welcome message and the sign-out message each show once and are gone on refresh.
  2. **The `{{ error }}` box** (`.auth-error`, `role="alert"`).
  3. **The form**, which POSTs to `url_for('login')`:
     - `email` input: `type="email"`, re-filled after an error, `maxlength="254"`,
       `autocomplete="email"`, `required`, `autofocus`
     - `password` input: `autocomplete="current-password"`, `required`, never re-filled,
       **no** `maxlength` (§12)

  Below the card, outside the form, `p.auth-switch` holds the "Create one free" link to `url_for('register')`.
- **`templates/base.html` nav:**
  - logged in (`g.user`): "Hi, {name}", then Sign out:
    - a `<form method="POST" action="{{ url_for('logout') }}" class="nav-logout">`
    - containing `<button type="submit" class="nav-cta">Sign out</button>`
  - logged out: **Sign in** and **Get started** links
- **`static/css/style.css`:**
  - `.nav-logout { display: contents; }` places the button directly in the `.nav-links` flex row
  - a `button.nav-cta` reset (border, font, cursor) makes the button look like the other `.nav-cta` links

## 8. Files to change
- `app.py` (`logout()`)
- `templates/login.html`, `templates/base.html`
- `static/css/style.css` (`.nav-logout`, `button.nav-cta`)
- `CLAUDE.md` (route table, Authentication section)
- `tests/test_auth.py`

Related but unchanged: `static/css/landing.css` duplicates the nav rules and loads after
`style.css` on `/`. `database/db.py`, `landing.html` and `register.html` are also unchanged.

## 9. Files to create
None. Tests live in `tests/test_auth.py` ("Login / logout" section). `tests/test_routes.py`
covers `GET /login` rendering and the form's `action="/login"`.

## 10. Dependencies
No new pip packages. Uses `werkzeug.security.check_password_hash` and Flask's `flash()`.

## 11. Outcomes

### Login

| # | Situation | Result | Status |
|---|---|---|---|
| 1 | Already logged in (GET or POST) | Redirect to `/`; nothing is checked | 302 |
| 2 | Email or password empty after normalisation (whitespace-only email counts as empty) | "Email and password are required."; email re-filled | 400 |
| 3 | Unknown email | "Invalid email or password."; email re-filled | 401 |
| 4 | Account has the `"!"` marker, or an empty or NULL hash | "Invalid email or password."; email re-filled | 401 |
| 5 | Wrong password | "Invalid email or password."; email re-filled | 401 |
| 6 | Correct credentials (email matched case-insensitively, password exact) | Session = `{user_id}` only; redirect to `/` | 302 |

Cases 3–5 deliberately share one message, so the login form doesn't reveal which emails exist.

### Logout

| # | Situation | Result | Status |
|---|---|---|---|
| 1 | `POST` with a session holding a `user_id` (also a deleted user's) | Session cleared; "You've been signed out." flashed; redirect to `/login` | 302 |
| 2 | `POST` with no `user_id` in the session: a logged-out visitor, or another site's form (no cookie under `SameSite=Lax`) | Session untouched, no `Set-Cookie`, no flash; redirect to `/login` | 302 |
| 3 | `GET /logout` (a typed URL, an old bookmark, a link or image on another site) | Method Not Allowed; session untouched | 405 |

## 12. Rules for implementation
- All SQL lives in `database/db.py` and uses parameterized queries only.
- Verify passwords only with `check_password_hash()`. Never log or echo a password.
- Login errors re-render the form with `error=...` and a 4xx status. They never return a bare string.
- The session stores only `user_id`, plus Flask's one-time `_flashes` until it is shown. Sessions start only through `start_session()`.
- Every internal link uses `url_for()`.
- Session cookie: `HttpOnly` and `SameSite=Lax`.
- **Logout is POST-only, and does nothing without a `user_id`:**
  - A GET logout could be triggered by any link, image or redirect on another site.
  - With `SameSite=Lax`, the browser sends no session cookie with another site's POST. Logout
    therefore sees no `user_id`, and leaves the real cookie alone.
  - This replaces a CSRF token until tokens arrive (before Step 7).
- **No password length cap at login**, neither server-side nor as `maxlength` on the input:
  - scrypt's cost doesn't grow with the password's length
  - accounts created before the Step 2 cap could be locked out
  - `maxlength` would silently truncate a pasted password

## 13. Expected behaviour
- **Registered user signs in:** after `/register` → `/login` (which shows the welcome message once), the correct
  credentials return a 302 to `/`, and the nav shows "Hi, {name}" and a Sign out button.
- **Case-insensitive, padded email:** `"  Asha@Example.COM "` logs into `asha@example.com`.
- **Exact password:** an account registered with `"  pass word  "` rejects `"pass word"` and accepts `"  pass word  "`.
- **Session clearing on login:** a key planted before login is gone afterwards; only `user_id` remains.
- **Demo user:** after `seed_db()`, `demo@spendly.com` / `demo123` logs in.
- **Sign out:** the nav's Sign out button POSTs to `/logout`. The session is cleared, `/login`
  shows "You've been signed out." once (gone on refresh), and the nav shows Sign in again.
- **Opening `/logout` directly:** 405; the user stays signed in.
- **Another site POSTing to `/logout`:** the user stays signed in; the response sets no cookie.
- **Deleted account:** with a session for a deleted user, `/` shows the logged-out nav and `/login` renders (200).
- **Logged in:** `GET /login` and `GET /register` redirect to `/`; a `POST /login` with a wrong password also redirects to `/`.

## 14. Definition of done
Tests are in `tests/test_auth.py`.

- [x] `GET /login` renders the form; logged-in users are redirected to `/` — `test_logged_in_user_is_redirected_away_from_auth_pages`
- [x] Valid credentials (case-insensitive email) start a session and redirect to `/` — `test_login_with_valid_credentials`
- [x] A padded, mixed-case email logs in — `test_login_accepts_padded_mixed_case_email`
- [x] A password with leading or trailing spaces must be typed exactly — `test_login_password_must_match_exactly`
- [x] Wrong password and unknown email → 401 with the same generic message — `test_login_rejects_invalid_credentials`
- [x] Empty or whitespace-only email, or empty password → 400 — `test_login_requires_both_fields`
- [x] A failed login (400 or 401) re-fills the email and never echoes the password — `test_login_error_keeps_email_but_not_password`
- [x] Accounts with the `"!"` marker can't log in — `test_login_user_with_unusable_password_is_rejected`
- [x] The seeded demo user can log in — `test_seeded_demo_user_can_log_in`
- [x] Login drops pre-existing session keys; the session is exactly `{user_id}` — `test_login_replaces_existing_session_data`, `test_login_session_contains_only_user_id`
- [x] A logged-in `POST /login` redirects to `/` without checking the credentials — `test_login_post_when_logged_in_redirects_without_checking`
- [x] The registration welcome flash shows once on `/login` and is gone on refresh — `test_register_shows_welcome_message_on_login_page_exactly_once`
- [x] The login form has `autocomplete`, an email `maxlength`, no password `maxlength`, and `role="alert"` on errors — `test_login_form_has_autocomplete_and_error_alert`
- [x] `POST /logout` clears the session and redirects to `/login`; the nav switches back — `test_logout_clears_session`
- [x] The sign-out message shows once on `/login` and is gone on refresh — `test_logout_shows_signed_out_message_once`
- [x] `GET /logout` → 405 and the user stays signed in — `test_logout_rejects_get`
- [x] Logout without a `user_id` leaves the session alone (no flash, pending flashes kept) — `test_logout_when_logged_out_is_harmless`
- [x] Logout without a session cookie sends no `Set-Cookie` (models another site's POST) — `test_logout_without_session_cookie_sets_no_cookie`
- [x] The nav's Sign out is a POST form with a button, not a link — `test_nav_sign_out_is_a_post_form`
- [x] A session for a deleted user is treated as logged out, and logout clears its stale id — `test_session_for_deleted_user_is_treated_as_logged_out`
- [x] The session cookie is `HttpOnly` and `SameSite=Lax` — `test_session_cookie_is_httponly_and_samesite_lax`
- [ ] Manual browser check (yours): the Sign out button looks like before, on `/` and other pages, including ≤600px wide

## 15. Known gaps (decided; not implemented in Step 3)
1. **No password length cap at login (D4, deliberate; §12).** A huge password still runs scrypt
   once per attempt. The cost doesn't depend on length: the research measured 186 ms for 500 KB
   against 160–182 ms for a short one. Flask's ~500 KB in-memory form-field limit applies
   only when the request sends a `Content-Length`.
2. **Timing difference (D5, skipped).** An unknown email or a `"!"` account returns without
   running scrypt, so it responds faster than a wrong password, which hints whether an account
   exists. `/register`'s 409 already reveals the same thing (Step 2 K1). Revisit with email verification.
3. **No rate limiting or lockout (D6, deferred).** Without packages it would be an in-memory dict,
   lost on every dev-server reload. It belongs in deployment or a DB table in a later step.
4. **No `next` parameter (D7, Step 4).** After login the user always goes to `/`. Step 4 adds the
   first protected route. Accept only relative paths that start with a single `/`. Reject `//…`,
   `/\…` and absolute URLs, because Flask doesn't validate redirect targets.
5. **No "remember me".** The session cookie lasts only for the browser session. Without a
   `SECRET_KEY` environment variable, everyone is logged out on every dev-server auto-reload, not only on restarts.
6. **No CSRF tokens.** Logout's protection relies on `SameSite=Lax` (§12). The login and register
   forms have no token either. Tokens come before Step 7, and every POST helper in the tests will need one.

## 16. Out of scope
- Password reset or change, email verification, account deletion
- The profile page and the post-login redirect target (Step 4)
- CSRF tokens across the app (before Steps 7–9)
- A friendlier 405 page for `GET /logout` (no `errorhandler` exists yet)
