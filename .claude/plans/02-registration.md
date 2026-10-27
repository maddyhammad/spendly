# Implementation Plan — Step 2: Registration

- **Spec:** `.claude/specs/02-registration.md`
- **Branch:** `feature/registration` (from `main` at `d70a165`)
- **Inputs read:**
  - spec, `app.py`, `database/db.py`, `templates/register.html`, `templates/base.html`, `tests/test_auth.py`
  - codebase research subagent: `tests/conftest.py`, `tests/test_routes.py`, `tests/test_db.py`,
    `static/css/style.css`, `templates/login.html`, `templates/landing.html`, `.gitignore`, live `spendly.db` (read-only)
- **Date:** 2026-10-27
- **Status:** ✅ Implemented 2026-10-27. D1–D6 were all approved, and §11 lists where the implementation
  differs from this draft. Registration was then changed (same day, at the user's request) so it no longer logs
  the user in. It now redirects to `/login` with a one-time success message (see §11). Full suite: 83 passed.
  The implementation and tests never wrote to `spendly.db`; the only new rows came from the user's own
  manual sign-ups in the browser. Nothing is committed yet.

---

## 1. Goal

Registration already works and `tests/test_auth.py` passes (30/30). This step therefore does
**not** rebuild the feature. It:

1. corrects the spec where it misdescribes the code (§4),
2. closes the behavioural gaps found during research, but only the ones you approve in §3 (§5),
3. adds tests for the behaviour the spec promises but nothing asserts yet (§6),
4. verifies that nothing else broke and the real `spendly.db` was not touched (§7).

Nothing in this step changes the database schema, so there is **no migration** and no `spendly.db` backup is required.

---

## 2. Current state vs spec

| Area | Spec says | Code today | Gap |
|---|---|---|---|
| `GET /register` | Form; logged-in users go to `/` | ✅ `app.py:70-75` | none |
| `POST /register` logged in | Redirect to `/` | ✅ `app.py:72` runs before the method check | **Untested.** The test at `test_auth.py:218-223` only covers GET |
| Field normalisation | Name stripped; email `strip().lower()` | ✅ `app.py:77-79`. The email is stripped too, but the spec only mentions the name | Spec wording |
| Empty-field check | Whitespace-only counts as empty | ✅ for name and email. The **password is not stripped**, so 8 spaces pass | **Gap → D1** |
| Password length | ≥ 8 | ✅ `app.py:56`. No upper bound (Flask's form-size cap is about 500 KB) | **Gap → D2** |
| Name content | 1–100 chars | ✅ length only. Control characters (NUL, etc.) are accepted | **Gap → D3** |
| Duplicate email | 409, case-insensitive | ✅ but only via `.lower()` in the route. DB `UNIQUE` is case-sensitive (`db.py:59`) | **Gap → D4.** All live rows are lowercase today |
| `create_user()` → `None` | "email already registered" | Returns `None` on **any** `IntegrityError` (`db.py:306-308`) | Spec wording (validation makes other errors unreachable) |
| Hashing | scrypt | ✅ Werkzeug 3.1.6 default | **Untested** for registration. Only the seed asserts `scrypt:` |
| Session start | `start_session()` clears first | ✅ `app.py:42-45`, used by register and login (logout calls `session.clear()` directly) | Clearing on register is **untested**. "Session fixation" is imprecise for client-side cookie sessions |
| Form hints | "Mirror" server rules | Approximate: `type="email"` accepts `a@b`; `required` accepts whitespace | Spec wording. **Accessibility gaps → D5** |
| Nav | `g.user` switches links | ✅ `base.html:21-27`; `.nav-user` in `style.css:105` | Spec omits `style.css` from files |
| Email boundary | ≤ 254 | ✅ `app.py:54` | **Untested** at exactly 254 / 255 (the existing test uses 257) |
| Files to create | `tests/test_auth.py` | Already exists; `tests/test_routes.py` also covers `/register` | Spec wording |
| Spec/plan tracking | n/a | `.gitignore:33` (`.claude/*`) ignores `.claude/specs/` and `.claude/plans/` | **Housekeeping → D6** |

---

## 3. Decisions

### Need your call

| # | Decision | Recommendation | Alternative |
|---|---|---|---|
| **D1** | Whitespace-only passwords (for example 8 spaces) | **Reject** with "Password cannot be only spaces." (400). Spaces *inside* a password stay allowed, and the password is still **never stripped** | Leave as is |
| **D2** | Maximum password length | **Add a 128-character cap** with "Password must be 128 characters or fewer." (400), plus `maxlength="128"` on the input. Cheap, and stops 500 KB bodies being hashed | No cap (scrypt cost barely grows with length; Flask's 500 KB form limit still applies) |
| **D3** | Control characters in names | **Reject** ASCII/Unicode control characters (category `Cc`, which includes NUL and newlines) with "Name contains invalid characters." (400). Leave format characters (`Cf`) alone because some scripts need zero-width joiners | Leave as is (autoescaping already prevents XSS) |
| **D4** | Enforce case-insensitive email at the DB level | **No schema change.** Changing `UNIQUE` to `COLLATE NOCASE` is a constraint change and needs a full table rebuild. Instead, keep normalising in the route, add a test, and make `/seed-user` lowercase its email argument | Rebuild `users` with `COLLATE NOCASE` in `migrate_db()` (heavy, and needs the full rebuild procedure from CLAUDE.md) |
| **D5** | Form accessibility | **Yes, template-only:** `autocomplete` attributes (`name`, `email`, `new-password`) and `role="alert"` on the error box | Leave as is |
| **D6** | Track `.claude/specs/` and `.claude/plans/` in git | **Yes:** add `!.claude/specs/` and `!.claude/plans/` to `.gitignore`, matching how `commands/` is handled, so the spec and plan can ship on this branch | Keep them local-only |

### Kept as-is (deliberate; noted so nobody "fixes" them by accident)

| # | Topic | Why we keep it |
|---|---|---|
| K1 | "An account with that email already exists." reveals which emails are registered | Standard for small apps. A real fix needs email verification, which is out of scope |
| K2 | `create_user()` returns `None` on any `IntegrityError` | Validation guarantees name, email and hash are non-null, so only the email `UNIQUE` can fire. Only the spec wording changes |
| K3 | Duplicates are detected at insert time, *after* hashing | Race-safe (no check-then-insert). Costs one scrypt per duplicate attempt, which is acceptable without rate limiting |
| K4 | Email normalised with `.lower()`, not `casefold()` | Equivalent for ASCII emails. Changing it could orphan existing accounts |

---

## 4. Phase 1 — Correct the spec (`.claude/specs/02-registration.md`)

Documentation only. Do this first so the remaining phases are checked against an accurate spec.

1. **§1 Overview:** say that only *login* reuses `start_session()`, while logout calls `session.clear()`
   directly. Drop "specced in Step 3", because no Step 3 spec exists yet.
2. **§4 Database:** list `name` and `email` as `NOT NULL`.
3. **§5 Functions:** `create_user()` returns `None` on any `IntegrityError`. In practice that is
   only the email `UNIQUE`, because validation runs first. Note that its rollback is on the shared
   per-request connection.
4. **§6 `start_session()`:** reword "prevents session fixation" to "drops any keys set before
   login/registration". Sessions are signed client-side cookies with no server-side id.
5. **§7 Templates:** "mirror" → "approximate". List the known differences: `a@b`, whitespace-only
   name, `maxlength` counts UTF-16 units before `strip()`.
6. **§8 Files to change:** add `static/css/style.css` (`.nav-user`). Add any files changed by approved decisions.
7. **§9 Files to create:** "None — `tests/test_auth.py` already exists." Mention `tests/test_routes.py`.
8. **§11 Validation rules:**
   - the email is stripped as well as the name; the password is never stripped
   - case-insensitivity comes from route-level lowercasing, not the DB
   - the duplicate check happens at insert time, after hashing
   - add rows for each approved D1/D2/D3 rule, in their evaluation order (see §5.1)
9. **§13/§14:** add the new boundary and behaviour lines from §6. Leave the new items unticked until Phase 4 passes.
10. **§15 Out of scope:** add K1–K4.

---

## 5. Phase 2 — Code changes (only for approved decisions)

### 5.1 `app.py` — `validate_registration()`

Keep the "first failure wins" structure. The approved checks go in this **evaluation order**
(new ones marked ★):

1. any field empty → "All fields are required." (unchanged)
2. name > 100 chars (unchanged)
3. ★ **D3** name contains a control character → "Name contains invalid characters."
4. email > 254 chars or fails `EMAIL_PATTERN` (unchanged)
5. password < `MIN_PASSWORD_LENGTH` (unchanged)
6. ★ **D2** password > new `MAX_PASSWORD_LENGTH` constant (128) → "Password must be 128 characters or fewer."
7. ★ **D1** password is only whitespace → "Password cannot be only spaces."

Notes:
- D2 adds a module-level constant next to `MIN_PASSWORD_LENGTH`. Its message is built from the
  constant in the same way the min-length message is.
- D3 uses the standard library (`unicodedata`) only, with no new packages. The check runs on the stripped name.
- D1 is placed *after* the length checks, so 3 spaces still produce the "at least 8" message, and
  is a separate check from "All fields are required" so the message is accurate.
- The `register()` route itself does not change. It already re-renders with `error`, `name` and `email` and a 400.
- `login()` is **not** touched. Its checks belong to Step 3, and existing accounts must keep working.

### 5.2 `templates/register.html`

- **D2:** add `maxlength="128"` to the password input. Update the placeholder only if it still reads correctly.
- **D5:** `autocomplete="name"`, `autocomplete="email"`, `autocomplete="new-password"`; `role="alert"` on the `.auth-error` div.
- No CSS changes. All classes exist in `style.css`.

### 5.3 `database/db.py`

- No changes. (D4 recommends no schema change, and K2 keeps `create_user()` as is.)

### 5.4 `.claude/commands/seed-user.md` (D4)

- Add one instruction: normalise the email argument with `strip().lower()` before looking it up or inserting it.

### 5.5 `.gitignore` (D6)

- Re-include `.claude/specs/` and `.claude/plans/` alongside the existing `!.claude/commands/` line.
- Check with `git check-ignore` that `.claude/settings.local.json` and other local `.claude/` files stay ignored.

### 5.6 `CLAUDE.md`

- Authentication section: extend the validation rule list with the approved D1–D3 rules and `MAX_PASSWORD_LENGTH`.
- If D6 is approved, note that specs and plans are tracked.

---

## 6. Phase 3 — Tests

All new tests use the existing `app`/`client` fixtures and the `register()` / `session_user_id()` /
`fetch_users()` helpers in `tests/test_auth.py`. The `app` fixture never seeds, so the `users` table starts empty.

### 6.1 Always add (cover behaviour the spec already promises)

| Test | Asserts |
|---|---|
| `test_register_post_when_logged_in_redirects_without_creating_user` | register, then POST a second registration in the same session → 302 to `/`, still 1 user, session unchanged |
| `test_register_clears_existing_session_data` | plant a stray key in the session, register → only `user_id` remains (mirrors the login test at `test_auth.py:175`) |
| `test_register_hash_uses_scrypt` | the stored `password_hash` starts with `scrypt:` |
| `test_register_email_length_boundary` | parametrised: a 254-char valid email → 302; a 255-char one → 400 "valid email" |
| `test_register_duplicate_with_padding_and_case` | register `asha@example.com`, log out, register `  ASHA@Example.com ` → 409, 1 user |
| `test_create_user_returns_none_for_duplicate` (in `tests/test_db.py`) | the second `create_user()` with the same email returns `None` and the row count is unchanged |

### 6.2 Add per approved decision

| Decision | Change |
|---|---|
| D1 | Add cases to `test_register_validation`: `" " * 8` and a mixed tab/space password → 400 "only spaces". Plus a positive test that `"pass word"` (an inner space) is accepted |
| D2 | Add a 129-char password → 400 "128 characters" to `test_register_validation`. Extend `test_register_accepts_boundary_values` with a 128-char password |
| D3 | Add names `"Asha\x00Rao"` and `"Asha\nRao"` → 400 "invalid characters". Plus a positive test with an accented name (`"José Ñúñez"`) |
| D5 | One test that the register page contains `autocomplete="new-password"` and `role="alert"` when an error is shown |

### 6.3 Must keep passing unchanged

- All 30 tests in `tests/test_auth.py`, plus `tests/test_routes.py`, `tests/test_db.py` and `tests/test_seed.py`.
- In particular `test_register_error_keeps_name_and_email_but_not_password` and
  `test_auth_forms_post_to_their_own_routes`. The template edits must not change `action` or the `value` echo.

---

## 7. Phase 4 — Verification

1. Record the sha256 of `spendly.db` before running anything.
2. Run the **full** suite (`pytest`), not just `test_auth.py`.
3. Hand result verification to a subagent (CLAUDE.md policy). It re-runs `pytest` and reports pass/fail counts.
4. Confirm the `spendly.db` hash is unchanged. Tests must only ever use temp DBs.
5. Manual smoke test with `python app.py` on port 5001 (needs your OK, because it writes to the real DB through `seed_db()` and any accounts registered):
   - register a new account → redirected to Sign in with the green welcome message; nav still shows Sign in
     (superseded the original "nav shows Hi, <name>" step, see §11)
   - try each new rule in the browser (a whitespace password; a 129-char password if the browser's `maxlength` is bypassed)
   - duplicate email → error banner, name and email kept, password cleared
   - sign out → nav switches back
   - *Use a throwaway email such as `smoke+reg@example.com`. Test accounts stay in `spendly.db`
     unless you ask for them to be removed, because CLAUDE.md forbids resetting the DB.*
6. Update the spec's §14 checkboxes and set this plan's status to ✅ Implemented.

---

## 8. Files touched (if everything is approved)

| File | Phase | Change |
|---|---|---|
| `.claude/specs/02-registration.md` | 1 | Corrections + new rules |
| `app.py` | 2 | `MAX_PASSWORD_LENGTH`; 3 new checks in `validate_registration()` |
| `templates/register.html` | 2 | `maxlength`, `autocomplete`, `role="alert"` |
| `.claude/commands/seed-user.md` | 2 | Lowercase the email |
| `.gitignore` | 2 | Track specs and plans |
| `CLAUDE.md` | 2 | Validation rules; tracked specs/plans |
| `tests/test_auth.py` | 3 | ~5 new tests + new parametrised cases |
| `tests/test_db.py` | 3 | 1 new test |
| `database/db.py`, `static/css/*`, `base.html`, `login.html` | — | **No change** |

No new pip packages. No schema change or migration.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| A new rule locks out existing users | Rules apply only at **registration**. `login()` is untouched, so existing accounts with whitespace passwords etc. still sign in |
| The new password cap rejects a password manager's long generated password | 128 is above common generator defaults (16–64). The client-side `maxlength` matches, so users see the limit before submitting |
| The control-character check rejects legitimate names | Only `Cc` is rejected (control codes); `Cf` joiners and all letters/marks are allowed; covered by a positive accented-name test |
| Template edits break existing tests that string-match the HTML | §6.3 tests run in Phase 4; edits avoid `action` and `value` |
| Smoke test pollutes `spendly.db` | Throwaway email; only with your OK; the hash check in §7.4 covers the automated part |
| Un-ignoring `.claude/` subfolders commits local settings | Re-include only `specs/` and `plans/`, then verify with `git check-ignore` |

---

## 10. Out of scope (noticed, not touched)

- **CSRF tokens.** Needed before the Step 7–9 expense forms (CLAUDE.md). `SameSite=Lax` is the only defence today.
- **Redirect after *login* → `/profile`.** Belongs to Step 4. Registration now always redirects to `/login` (see §11).
- **Login form parity** (`maxlength` on email, `autocomplete="current-password"`). Belongs to Step 3; no spec exists yet.
- Rate limiting, email verification, account-enumeration hardening (K1).
- A custom 405 page (Werkzeug's default is shown for e.g. `PUT /register`).
- Landing-page "Start tracking free" CTAs still show to logged-in users. They just bounce to `/`.
- `SESSION_COOKIE_SECURE` and a required `SECRET_KEY` for production.
- `.claude/commands/create-specs.md` is still empty on `main`.

---

## 11. As implemented (2026-10-27): differences from the draft above

- **D3 widened:** names also reject the Unicode line and paragraph separators (`Zl`/`Zp`: U+2028, U+2029),
  as well as `Cc`. The user asked for newlines to be rejected, and these are newlines too. An independent review flagged the gap.
- **D4 data check:** a read-only check of `spendly.db` found 3 users, 0 emails that aren't normalised, 0
  case-insensitive duplicates, and a `BINARY` collation on the `email` index. No records were modified.
- **D6 extras:** `.gitignore` also ignores:
  - `*.db`, `*.sqlite`, `*.sqlite3`, `*.backup`, `*.orig` (stray DB copies or backups could contain user data)
  - `CLAUDE.local.md`, `.env.*` (with `!.env.example` re-included)
  - `*.tmp`, `*.swp`, `*~`

  The old standalone `.claude/plans/` ignore line was removed.
- **Spec §6 wording:** `start_session()` is still described as the session-fixation defence. The spec
  explains that with client-side cookies this works by dropping pre-login keys, which keeps
  `CLAUDE.md` and the `app.py` comment accurate unchanged.
- **Test names differ from §6.1:**

  | Draft name | Actual |
  |---|---|
  | `test_register_clears_existing_session_data` | `test_register_replaces_existing_session_data`, later **removed** when registration stopped logging in (see below) |
  | `test_register_hash_uses_scrypt` | `test_register_hashes_password_with_scrypt` |
  | `test_register_duplicate_with_padding_and_case` | `test_register_rejects_padded_mixed_case_duplicate` |
  | `test_register_email_length_boundary` | Split: 255 → a `test_register_validation` case; 254 → `test_register_accepts_max_lengths` (with password 128) |
  | `test_create_user_returns_none_for_duplicate` | `test_create_user_returns_none_for_duplicate_email` |

  New tests not in the draft:
  - `test_email_unique_is_case_sensitive_at_db_level` documents D4 and fails if the schema changes
  - `test_register_stores_password_exactly_as_entered`
  - `test_register_accepts_non_ascii_name`
- **Changed after implementation, at the user's request: registration no longer logs the user in.**
  This replaces a short-lived welcome banner on `/`.
  - `register()` no longer calls `start_session()`. It flashes "Welcome to Spendly! 🎉 Your account has
    been created successfully. Please sign in to continue." (category `success`) and redirects to `/login`.
  - `login.html` renders success flashes above the form as an `.auth-success` box (`style.css`).
    Its look: a green ✓ badge, a green left border, and a short fade-in that respects reduced motion.
  - The global flash block in `base.html` and the `.flash-*` styles from the banner were removed, so
    `base.html` matches `main` again.
  - Tests:
    - updated: the registration tests now expect `/login` and no session
    - tests that need a logged-in user (logout, deleted user, logged-in redirects, cookie flags,
      logged-in POST) use a new `sign_up_and_log_in()` helper
    - removed: 5 now-pointless `client.get("/logout")` calls
    - removed: `test_register_replaces_existing_session_data`, because registration no longer touches the
      session. Login's equivalent test covers session clearing.
    - the cookie-flags test now asserts that the login succeeded before checking the cookie
    - added: the message appears exactly once, above the form, and is gone on refresh
    - added: no message after a 400 or 409 failure
- **Manual browser smoke test (§7.5) not run.** It would write test accounts into the real `spendly.db`,
  which the user asked to keep unchanged. The automated tests cover the same flows against temp DBs.
