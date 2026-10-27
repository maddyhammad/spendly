# Implementation Plan — Step 3: Login and Logout

- **Spec:** `.claude/specs/03-login-and-logout.md`
- **Branch:** `feature/login-and-logout` (from `main` at `9719673`)
- **Inputs read:**
  - the spec, `app.py`, `templates/login.html`, `templates/base.html`, `tests/test_auth.py`
  - codebase research subagent:
    - CSS: `static/css/style.css`, `static/css/landing.css`
    - templates and tests: `templates/landing.html`, `tests/test_routes.py`, `tests/conftest.py`
    - installed Flask/Werkzeug source, timings measured in the venv
    - live `spendly.db` (read-only counts only)
- **Status:** ✅ Implemented (2026-10-28).
  - All decisions were approved as recommended: D1–D3 are implemented, and D4–D7 are not (see §3).
  - Results: `tests/test_auth.py` 66 passed; full suite 96 passed. A verification subagent confirmed them, and mutation checks showed the new tests catch regressions. The `spendly.db` sha256 is unchanged.
  - §11 lists where the implementation differs from this plan.
  - Still open: your manual browser check (§7.5).

---

## 1. Goal

Login and logout already work, and every login/logout test passes. This step does **not**
rebuild them. It:

1. corrects the spec where research showed it was wrong or imprecise (§4),
2. closes the gaps you approve in §3 (§5),
3. adds tests for the 5 behaviours the spec marks *(untested)*, plus 2 more the research found (§6),
4. verifies that nothing else broke and the real `spendly.db` was not touched (§7).

There is **no schema change and no migration.**

---

## 2. Current state vs spec

| Area | Today | Gap |
|---|---|---|
| Login outcomes (spec §11) | ✅ `app.py:111-136`. All 6 outcomes behave as specced | The 5 behaviours in spec §14 are untested. Also untested: a whitespace-only email → 400, the email kept after a 401, and "session holds **only** `user_id`" |
| Logout method | `GET /logout` (`app.py:139-142`). The nav "Sign out" is an `<a class="nav-cta">` (`base.html:23`) | **Cross-site logout is possible → D1** |
| Logout without a cookie | `session.clear()` marks even an empty session as modified, so Flask still sends a "delete cookie" header | Turning logout into a POST **alone** doesn't stop cross-site logout. Logout must do nothing when the request has no logged-in session (D1) |
| Logout feedback | Redirects to `/` silently. `/` renders no flashes, and the landing hero's `::before` circle covers the space above it | **No confirmation → D2** |
| Login form | No `role="alert"`, no `autocomplete`, no `maxlength` on the email (`login.html:23-39`) | **Parity with register → D3** |
| Password cap at login | None. A 500 KB password costs about the same as a short one (186 ms vs 160–182 ms), because scrypt pre-hashes the input | **D4** (recommend no cap) |
| Response timing | Unknown email, `"!"` account or empty hash: instant. Real account: about 170 ms of scrypt | **D5** (recommend skip: `/register`'s 409 already reveals which emails exist, Step 2 K1) |
| Rate limiting | None. There's no shared in-memory state. The dev server reloads and is threaded, and the tests share one `app` object | **D6** (recommend defer) |
| `next` after login | No protected routes yet. The stubs are anonymous, and `test_stub_routes_unchanged` expects that | **D7** (recommend defer to Step 4) |
| CSRF tokens | None. No library is installed, and none may be added (CLAUDE.md) | Out of scope: before Step 7 (§10) |

---

## 3. Decisions

### Need your call

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| **D1** | Stop other sites from signing users out | **Make `/logout` POST-only, and only clear the session when it holds a `user_id`.** The nav's "Sign out" becomes a small form with a button styled exactly like today's link. With `SameSite=Lax`, the browser doesn't send the session cookie on another site's POST. Logout then sees no `user_id`, does nothing, and sends no "delete cookie" header. A `GET /logout` (an old bookmark, say) gets Flask's default **405** page | Keep GET logout and accept the risk until CSRF tokens arrive (Step 7) |
| **D2** | Show a "signed out" confirmation | **Redirect logout to `/login` with a one-time "You've been signed out." message.** It reuses the existing `.auth-success` box on the login page, so `landing.html` and `landing.css` need no changes. The message is flashed only when a session was actually ended | (a) Keep redirecting to `/` and add a message slot above the landing hero. That needs a `z-index` workaround for the hero's decorative circle. (b) No message |
| **D3** | Login form parity with register | **Yes, template-only:** `role="alert"` on the error box, `autocomplete="email"` / `autocomplete="current-password"` (matching register's `"email"`), and `maxlength="254"` on the email. **No** `maxlength` on the password (see D4) | Leave as is |
| **D4** | Cap the password length at login | **No cap.** It saves no real work (the cost doesn't grow with length). Accounts 3–7 were created before the Step 2 cap, so their password lengths can't be checked, and a cap could lock one out. A `maxlength` on the input would silently truncate pasted passwords | A 128-character server-side cap with the generic 401 |
| **D5** | Equalise login timing (run scrypt against a dummy hash for unknown/unusable accounts) | **Skip for now.** `/register` already tells anyone whether an email exists (Step 2 K1). Equalising adds about 170 ms to every import or test run, and an extra hash per failed login, without closing that leak. Revisit together with email verification | Implement it with a dummy hash computed once on first use |
| **D6** | Rate-limit or lock out failed logins | **Defer.** Without packages it would be an in-memory dict, which loses its state on every dev-server reload. It would also need a lock across threads and a reset between tests. Real limits belong in deployment (a reverse proxy) or a DB table in a later step | A simple in-memory per-email limit (e.g. 5 failures in 15 min) |
| **D7** | `next` parameter (return to the page that needed login) | **Defer to Step 4.** That's when the first protected route (`/profile`) and a login-required decorator arrive. Note for then: accept only relative paths that start with a single `/`, and reject `//…`, `/\…` and absolute URLs (Flask doesn't validate redirect targets) | Build it now with nothing to protect yet |

### Kept as-is (deliberate; noted so nobody "fixes" them by accident)

| # | Topic | Why we keep it |
|---|---|---|
| K1 | Login never re-validates format or length | Existing accounts must keep working. The demo password `demo123` is 7 characters |
| K2 | The `not user["password_hash"]` guard | `check_password_hash(None, …)` raises. NULL can't occur after `init_db()`, but the guard is cheap insurance |
| K3 | One generic message for unknown email, wrong password and `"!"` accounts | The form itself shouldn't reveal which emails exist |
| K4 | `login.html` renders only `success` flashes but pops all categories | Only `success` is ever flashed. Revisit when another category is introduced |
| K5 | No "remember me"; a random `SECRET_KEY` without the env var | The dev server reloads log users out. The fix is to set `SECRET_KEY` in the environment (already in CLAUDE.md) |

---

## 4. Phase 1 — Correct the spec (`.claude/specs/03-login-and-logout.md`)

Documentation only. Do this first so later phases are checked against an accurate spec.

1. **§7:** the "Create one free" link is in `p.auth-switch` **outside** the card and form.
   Flash rendering pops **all** categories and shows only `success` (K4).
2. **§6 / §11 row 4:** an empty hash returns `False` without raising. The guard only matters for
   NULL, and NULL can't exist after `init_db()` (NOT NULL column, and the rebuild maps it to `"!"`).
3. **§6 stale ids:** add "…unless `spendly.db` is deleted and recreated while a fixed `SECRET_KEY` is set".
4. **§8:** add `static/css/landing.css`. It duplicates the nav rules and loads after `style.css` on `/`.
5. **§15:** sharpen each gap with the research facts:
   - 15.1: a POST alone doesn't stop cross-site logout, because `clear()` emits a "delete cookie" header even without an incoming cookie
   - 15.4: the cost doesn't depend on length, and the 500 KB limit only applies with a Content-Length
   - 15.5: `"!"` accounts are as fast as unknown emails
   - 15.8: sessions are lost on every auto-reload, not just restarts
6. Once §3 is answered, rewrite §3, §6, §7, §11, §13 and §14 for the approved decisions. Add the new tests to §14, unticked until Phase 4 passes. Move rejected or deferred gaps to §16.

---

## 5. Phase 2 — Code changes (only for approved decisions)

### 5.1 `app.py`
- **D1:** `logout()` accepts **POST only**.
  - It clears the session only when it contains a `user_id`. That includes a stale id for a deleted user, so the cookie still gets cleaned up.
  - Otherwise it redirects without touching the session, so no `Set-Cookie` is sent.
- **D2:** after clearing (never before, or the clear would wipe it), flash "You've been signed out."
  with category `success`, then redirect to `url_for("login")`. With no session to end: no flash, and the redirect target stays the same.
- `login()`: **no change** (D4/D5 rejected, K1–K3).

### 5.2 `templates/base.html` (D1)
- Replace the "Sign out" `<a>` with a `<form method="post">` pointing at `url_for('logout')`.
  It contains a `<button type="submit" class="nav-cta">Sign out</button>`. The visible text stays
  "Sign out", so existing text assertions keep passing.
- The logged-out branch (Sign in / Get started) doesn't change.

### 5.3 `static/css/style.css` (D1)
- **The form** gets a class (e.g. `.nav-logout`) with `display: contents`. The button then sits
  directly in the `.nav-links` flex row, and the nav height doesn't change.
- **A button reset for `button.nav-cta`:** `border: 0`, `font: inherit`, `cursor: pointer`.
  `.nav-cta` already provides the background, colour, padding, radius and hover.
- **No change to `landing.css`.**
  - Its duplicated `.nav-cta` rule overrides only the same properties.
  - The ≤600px rule hides only `a:not(.nav-cta)`.
  - `style.css` loads on every page, so the reset applies on `/` too.

### 5.4 `templates/login.html` (D3)
- `role="alert"` on `.auth-error`.
- Email input: `autocomplete="email"`, `maxlength="254"`.
- Password input: `autocomplete="current-password"` (no `maxlength`, D4).
- Keep the flash loop, the form `action` and the `value` echo unchanged
  (`test_routes.py:19` and the new tests depend on them).

### 5.5 `CLAUDE.md`
- **Route table:** `POST /logout`, with "clears the session only when logged in; redirects to `/login` with a sign-out message".
- **Authentication section:**
  - logout is POST-only
  - why (the `SameSite=Lax` reasoning)
  - the sign-out flash is rendered on `/login`
  - `start_session()` is still login-only
- **Note for Step 7 (CSRF):** a per-session token will change the "session stores only `user_id` + `_flashes`" rule. Every POST helper in `tests/test_auth.py` will also need a token.

---

## 6. Phase 3 — Tests (`tests/test_auth.py`)

They use the existing `register()`, `login()`, `sign_up_and_log_in()`, `session_user_id()` and
`fetch_users()` helpers. A small `logout(client)` helper (POST) would replace raw `client.get("/logout")` calls.

### 6.1 Always add (spec §14 *untested* items + research extras)

| Test | Asserts |
|---|---|
| `test_login_error_keeps_email_but_not_password` | Parametrised over a 401 (wrong password) and a 400 (empty password): the email is re-filled; the typed password never appears in the HTML |
| `test_login_accepts_padded_mixed_case_email` | `"  Asha@Example.COM "` → 302, session started |
| `test_login_password_must_match_exactly` | Register `"  pass word  "`. Logging in with `"pass word"` → 401; with `"  pass word  "` → 302 |
| `test_login_rejects_whitespace_only_email` | `"   "` → 400 "Email and password are required." |
| `test_login_post_when_logged_in_redirects_without_checking` | Logged in, POST with a **wrong** password → 302 to `/`, same `user_id`, no 401 |
| `test_login_session_contains_only_user_id` | After a successful login, the session is exactly `{"user_id": <id>}`. The pending welcome flash is dropped by `start_session()` |
| `test_logout_when_logged_out_is_harmless` | Without a session → a redirect, no error |

### 6.2 Add or update per approved decision

| Decision | Change |
|---|---|
| D1 | **Update** `test_logout_clears_session` to POST. **Add:** `test_logout_rejects_get` (GET → 405, still logged in). **Add:** `test_logout_without_session_sets_no_cookie` (a fresh client POSTs → redirect, no `Set-Cookie` header; models a cross-site POST under `SameSite=Lax`). **Add:** `test_nav_sign_out_is_a_post_form` (a logged-in page has `method="post"` and `action="/logout"` and a "Sign out" button) |
| D2 | **Add:** `test_logout_shows_signed_out_message_once` (redirect to `/login`, the message appears exactly once, gone on refresh, nav shows "Sign in"). **Add:** no message when logging out without a session. **Update** `test_logout_clears_session`: its empty-session check becomes "no `user_id`, planted key gone", because `_flashes` sits there until shown |
| D3 | **Add:** `test_login_form_has_autocomplete_and_error_alert` (`autocomplete="email"`, `"current-password"`, `maxlength="254"`; `role="alert"` on a 401 page) |

### 6.3 Must keep passing unchanged
- Every other test in `tests/test_auth.py`, plus `tests/test_routes.py` (form `action`, stub routes), `tests/test_db.py` and `tests/test_seed.py`.
- The "Sign out" / "Sign in" text assertions (`test_auth.py:190, 231, 313`) rely on the button text staying "Sign out".

---

## 7. Phase 4 — Verification

1. Record the sha256 of `spendly.db` before starting.
2. Run `pytest tests/test_auth.py`, then the full `pytest`.
3. A subagent independently re-runs both and reviews the diff against the approved decisions (CLAUDE.md policy).
4. Confirm the `spendly.db` hash is unchanged. Tests only use temp DBs.
5. Manual check in your browser (your dev server reloads automatically):
   - sign in → "Hi, {name}" and a **Sign out** button that looks identical to today's
   - sign out → the login page shows "You've been signed out." once
   - refresh → the message is gone
   - opening `/logout` directly in the address bar → 405 page; you stay signed in
   - check the nav on `/` and on narrow (≤600px) screens
6. Update the spec's §14 checkboxes, and set this plan's status to ✅ Implemented.

Nothing is committed or pushed by Claude. You commit and push yourself.

---

## 8. Files touched (if D1–D3 are approved and D4–D7 aren't)

| File | Phase | Change |
|---|---|---|
| `.claude/specs/03-login-and-logout.md` | 1 | Corrections + approved behaviour |
| `app.py` | 2 | `logout()`: POST-only, clear only with a `user_id`, flash after the clear, redirect to `/login` |
| `templates/base.html` | 2 | "Sign out" link → POST form + button |
| `static/css/style.css` | 2 | `.nav-logout` (`display: contents`) and the button reset |
| `templates/login.html` | 2 | `role="alert"`, `autocomplete`, email `maxlength` |
| `CLAUDE.md` | 2 | Route table, Authentication section, Step 7 CSRF note |
| `tests/test_auth.py` | 3 | `logout()` helper; 7 new tests + 6 for D1–D3; 1 updated |
| `database/db.py`, `landing.html`, `landing.css`, `register.html` | — | **No change** |

No new pip packages. No schema change or migration.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| An old bookmark or link to `/logout` shows a plain 405 page | Only the nav links there, and it becomes a form. A friendlier GET page can be added later if wanted |
| The logout protection depends on browsers honouring `SameSite=Lax` | All current browsers do. Full CSRF tokens are planned before Step 7 |
| The button doesn't look exactly like the old link (font, border, height) | Button reset + `display: contents`; the manual check on `/` and ≤600px in §7.5 |
| The sign-out flash lingers if logout ever redirects somewhere other than `/login` | It's only flashed when the redirect target is `/login`; covered by a test |
| Changing `test_logout_clears_session` weakens it | It keeps asserting the planted key and `user_id` are gone, and a new test asserts the message is consumed |
| Tests share one `app` object, so state could leak | No module-level state is introduced (D5/D6 skipped) |

---

## 10. Out of scope (noticed, not touched)

- **CSRF tokens across all forms.** Before Step 7 (CLAUDE.md). Needs a session token and updated test helpers (§5.5 note).
- **Rate limiting (D6), the `next` redirect (D7), timing equalisation (D5).** Deferred with their reasons in §3.
- **Post-login redirect to `/profile`.** Step 4.
- **Password reset or change, email verification, account deletion, "remember me".**
- **A friendlier 405 page.** No `errorhandler` exists anywhere yet.
- **`.claude/commands/create-specs.md` is still empty.**

---

## 11. Implementation notes (differences from §5–§6)

- **Nav form markup:** it uses `method="POST"`, uppercase like the login and register forms, with
  `class="nav-logout"`: `<form method="POST" action="{{ url_for('logout') }}" class="nav-logout">`.
- **Whitespace-only email:** added as a `("   ", PASSWORD)` case of `test_login_requires_both_fields`, not as a separate test.
- **Renamed test:** `test_logout_without_session_sets_no_cookie` became `test_logout_without_session_cookie_sets_no_cookie`.
- **D2's "no message without a session" check:** it lives in `test_logout_when_logged_out_is_harmless`.
  - That test registers first, so a welcome flash is pending.
  - It asserts that logout leaves the flash intact and shows no sign-out message.
- **`test_logout_clears_session`:** it now asserts the session is exactly `["_flashes"]` after logout.
- **`test_session_for_deleted_user_is_treated_as_logged_out`:** it now also checks that logout clears a stale id.
- **`test_login_error_keeps_email_but_not_password`:** it checks the password `<input>` alone for
  `value=`, not the whole page, so a hidden CSRF input (Step 7) won't break it.
- **Totals:** 11 new test functions plus 1 new parametrised case, which is 13 new test items. 2 tests were updated.
- **Verification notes (unconfirmed browser quirks, for the manual check):**
  - Older Firefox versions can widen the button via `::-moz-focus-inner`. The fix is `button.nav-cta::-moz-focus-inner { border: 0; padding: 0; }`.
  - Older iOS Safari can keep native button styling. The fix is `appearance: none`.
  - Add either fix only if you see the problem.
