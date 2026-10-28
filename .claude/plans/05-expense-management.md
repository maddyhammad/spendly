# Plan: Step 5 — Expense management

Spec: `.claude/specs/05-expense-management.md`. This file records the decisions behind it and the build order.
**Status: draft, awaiting approval. No code written.**

## User choices (2026-10-28)
- **Delete flow:** a confirmation page. Clicking Delete opens a page that asks for confirmation, and its button sends the POST.
- **Categories:** the existing fixed list of 7, offered in a dropdown and validated on the server. No database change.
- **Expense list:** not answered. The recommended option is applied: a new `/expenses` page, with the profile staying on sample data until Step 6 (D1).

## Research summary (Explore subagent, 2026-10-28)
- **The stubs:**
  - The three `/expenses/*` stubs are GET-only, anonymous, and return raw strings.
  - `test_stub_routes_unchanged` asserts "Step 7/8/9" in their output.
  - No list route exists.
- **Database:**
  - No expense helpers exist in `db.py`.
  - The schema already fits: `description` is nullable, and `category` has no CHECK constraint (plan 01 D8 says it is validated in Python).
- **POST forms:**
  - There are only 3: register, login, and the nav's Sign out.
  - The tests POST through the `register`, `login` and `logout` helpers in `test_auth.py`, plus 2 direct calls in `test_profile.py`.
- **Flask internals (checked in the installed source):**
  - `before_request` runs **before** routing errors are raised.
  - The session cookie is written only when the session changes.
- **Validation pitfalls (checked on Python 3.11.9):**
  - `float()` accepts `nan`, `inf`, `1e3` and `1_000`.
  - `date.fromisoformat` accepts `20261026`.
  - `inr()` crashes on NaN.
- **Reuse problems:**
  - The `icon()` macro is private to `profile.html`.
  - The expense table, pill and icon-chip styles live in `profile.css`.
- **Nav on phones:** at ≤600px, every non-CTA nav link is hidden, in both `style.css` and `landing.css`.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | A new **`/expenses`** page lists the user's real expenses. `/profile` keeps its sample data. | It's the recommended default for the unanswered question, and it matches the roadmap (Step 6 integrates the profile). Mixing real and sample figures on one page would confuse users. |
| D2 | **Delete uses a confirmation page.** GET shows the expense, POST deletes, and GET never changes data. | The user's choice. It needs no JS, reuses the stub URL, and a link on another site can't delete anything. |
| D3 | The **7 fixed categories** go in a `<select>`, and the server accepts only exact `CATEGORIES` values. | The user's choice. CLAUDE.md says there's no categories table and categories are validated in Python. |
| D4 | **Hand-rolled CSRF:** one `secrets.token_hex(32)` token per session, created lazily by a `csrf_token()` Jinja global. A `before_request` hook checks every POST/PUT/PATCH/DELETE, skips requests that couldn't be routed, compares with `secrets.compare_digest`, and on failure calls `abort(400, …)` without touching the session. | Flask-WTF isn't installed and can't be added. Lazy creation keeps logged-out redirects cookie-free (Step 4 tests). Skipping routing errors keeps 405 and 404 correct. Hex tokens can't contain the text "None", which a Step 4 test searches the page for. |
| D5 | **Logout is CSRF-checked too.** A cross-site, cookie-less POST to `/logout` now gets **400** instead of 302, and still no `Set-Cookie`. | One rule for every POST. The security property from spec 03 §12 (another site can't sign the user out, and no cookie is touched) still holds; only the status code changes. The test is updated. |
| D6 | **Token rotation** comes for free: `start_session()` and `logout()` already clear the session. The session rule becomes `user_id` + `csrf_token` + `_flashes`. | Login gets a fresh token. The existing "session is exactly `{user_id}` right after login" tests stay true, because the token appears only when a form next renders. |
| D7 | **Ownership:** every helper filters by `user_id`. A foreign or missing id gives **404**, not 403, for GET and POST alike. | A 403 would confirm that the id exists. Filtering by `user_id` in SQL means a route can't forget the check. |
| D8 | **Reuse without duplication:** move `icon()` to `templates/partials/icons.html`, and move the expense-table, pill and icon-chip CSS from `profile.css` to a shared section of `style.css`. The profile's rendered HTML must stay identical. | Both pages show the same expense rows. Copying about 80 lines of CSS and a macro would drift over time. The move is checked with a before/after HTML diff and screenshots. |
| D9 | **Explicit validation:** regexes for amount and date; a text input with `inputmode="decimal"` (not `type="number"`); commas allowed; a ₹1 crore cap; dates from 2000-01-01 to today; an optional description of up to 200 characters with no control characters. The first error wins, with 400 and a re-fill. | It closes the `nan`/`inf`/`1e3`/`20261026` loopholes and keeps `inr()` safe. It matches the seed commands (positive amounts, valid dates, nothing in the future), and it follows the register/login pattern. |
| D10 | **DB helper names** are `list_expenses`, `get_expense`, `create_expense`, `update_expense` and `remove_expense`. Writes use try/commit and except/rollback/raise. | `delete_expense` etc. are the route endpoints in `app.py`, so importing a helper with that name would clash. The write pattern copies `seed_db`. |
| D11 | **Success flashes render on `expenses.html`** with the same `.auth-success` markup. Never in `base.html`. | Adds, edits and deletes all redirect there. The CLAUDE.md rule about double rendering still holds. |
| D12 | **`login_required` adds `Cache-Control: no-store`.** | Expense pages now show real data, and spec 04 §15.5 planned this "with real data". It's one place, and it covers `/profile` too. |
| D13 | **The nav Expenses link** stays visible on phones. At ≤600px the nav padding and gap shrink in both CSS files. | Without it, phones would have no way to reach the list. It gets checked at 360px. |
| D14 | **The route variable becomes `expense_id`**, while the endpoint names stay. `test_stub_routes_unchanged` is deleted, and CLAUDE.md drops its "stub text still says Step 7–9" notes. | `id` shadows a builtin. No stubs remain, so the test has nothing left to check. |

## Build order
Run `pytest` at every checkpoint and keep it green before moving on.

0. **Docs:** this plan and the spec. No code.
1. **Baseline:** record the test count (141) and the sha256 of `spendly.db`.
2. **CSRF:**
   - Add `csrf_token()` and `check_csrf`, and put the hidden inputs in login, register and the nav Sign out.
   - The test helpers send the token. Update the logout no-cookie test (D5) and the two direct POSTs in `test_profile.py`.
   - Add `tests/test_csrf.py`.
   - Run the **full suite**.
3. **DB helpers** and their scoping tests.
4. **`validate_expense()`** and its rule and boundary tests, before any route uses it.
5. **Shared refactor (D8):**
   - Capture the profile's rendered HTML, move the macro and the CSS, then diff the HTML (it must be identical).
   - Take profile screenshots.
6. **Routes and templates:**
   - Add the list, add, edit and delete routes, with their templates and `abort`.
   - Delete the stub test.
   - Add `tests/test_expenses.py`.
7. **Nav link and phone CSS (D13)** in `style.css` and `landing.css`.
8. **`expenses.css` polish**, then screenshots at 1280, 900, 375 and 360px. Include the nav on `/` at 360px.
9. **`Cache-Control` in `login_required` (D12)**, plus its test.
10. **`CLAUDE.md`:** route table, architecture, session/CSRF/flash rules, DB helpers, roadmap.
11. **Verification subagent:** full suite, `spendly.db` hash, rules check. Then your browser check.

## Risks

| Risk | Guard |
|---|---|
| CSRF breaks routing errors (405/404) | The check skips unrouted requests; `test_routing_errors_bypass_csrf` |
| Token creation sets cookies on redirects | Lazy Jinja global; `test_token_created_only_when_a_form_renders`, plus the existing Step 4 no-cookie test |
| Test helpers can't fetch a token while signed in (GET `/login` redirects) | The helpers read or plant the token through `client.session_transaction()`; `test_rendered_token_is_accepted` covers the real form path |
| The shared refactor changes the profile | A before/after rendered-HTML diff must be identical; the existing profile tests (SVG count, markup) and screenshots |
| A user edits or deletes someone else's expense | SQL filtered by `user_id`; 404 tests for every route/method |
| Bad input reaches `inr()` (NaN or inf → 500) | Regex validation before `float()`; boundary tests |
| The nav overflows at 360px | Phone padding and gap changes; screenshot check on `/` and `/expenses` |
| `pytest` touches `spendly.db` | Hash before and after, checked by the verification subagent |
