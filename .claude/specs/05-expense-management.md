# Spec: Step 5 — Expense management

> **Status:** 📝 Draft, awaiting approval. Nothing is implemented yet. Branch `feature/expense-management` (from `main` at `0e50449`).
>
> Step 5 lets a signed-in user **add, edit and delete their own expenses** and see them all on a new
> **`/expenses` page**, backed by SQLite. It starts with **CSRF tokens on every POST form**, which
> CLAUDE.md requires before any expense form is built.
>
> - `/profile` keeps its sample figures until Step 6.
> - No schema change.
>
> Decisions D1–D14 and the build order are in `.claude/plans/05-expense-management.md`.
> Roadmap: Step 6 replaces the profile's sample data with real calculations, using this step's expenses.

## 1. Overview
- **CSRF protection.**
  - Every POST form carries a hidden per-session token.
  - Every POST is rejected with **400** unless its token matches the session's.
  - The forms covered are register, login, the nav's Sign out, and the new add, edit and delete forms.
- **`/expenses`.** A signed-in user sees all their expenses, newest first: date, description, category (icon and pill) and amount.
  - A summary line shows how many expenses there are and their total.
  - Each row has **Edit** and **Delete**.
  - **Add expense** opens the form.
  - With no expenses, the page shows a friendly empty state with the same button.
- **Add and edit.** A form with these fields:
  - **amount** in ₹
  - **category**: a dropdown of the 7 fixed categories
  - **date**: defaults to today, no future dates
  - **description**: optional
  - Invalid input re-renders the form with one clear error (400) and keeps what the user typed.
  - Success redirects to `/expenses` with a one-time "Expense added." or "Expense updated." message.
- **Delete.** "Delete" opens a **confirmation page** showing the expense. Its button sends the POST, which deletes the expense and redirects to `/expenses` with "Expense deleted."
- **Ownership.** A user can only see, edit or delete their own expenses. Any other id returns **404**, so the app never reveals that it exists.
- **Navigation.** Logged-in users get an **Expenses** nav link, visible on phones too.
- **No caching.** Pages that require login send `Cache-Control: no-store`, so the Back button can't show someone's expenses after sign-out.

## 2. Depends on
- **Step 1:** the `expenses` table, the `CATEGORIES` tuple, `get_db()` with foreign keys on, and the commit/rollback pattern in `create_user()` and `seed_db()`.
- **Step 3:** the POST-only `/logout` and its invariants (spec 03 §12).
- **Step 4:**
  - `login_required`
  - the `inr` and `short_date` filters
  - the profile's expense-table styling and the `icon()` macro (both reused, §7)
  - the nav's `a.nav-profile`

## 3. Routes

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/expenses` | **New.** Login required. Lists the user's expenses (§7.2). |
| `GET` | `/expenses/add` | **Was a stub.** Login required. Empty form, with the date defaulting to today. |
| `POST` | `/expenses/add` | Validate (§5). Invalid → 400 and the form re-rendered. Valid → insert, flash "Expense added.", 302 to `/expenses`. |
| `GET` | `/expenses/<int:expense_id>/edit` | **Was a stub.** Login required. Form pre-filled from the user's own expense; any other id → 404. |
| `POST` | `/expenses/<int:expense_id>/edit` | Ownership check first (404). Invalid → 400 and re-render. Valid → update, flash "Expense updated.", 302 to `/expenses`. |
| `GET` | `/expenses/<int:expense_id>/delete` | **Was a stub.** Login required. Confirmation page for the user's own expense; any other id → 404. A GET **never** deletes. |
| `POST` | `/expenses/<int:expense_id>/delete` | Ownership check (404). Delete, flash "Expense deleted.", 302 to `/expenses`. |
| any POST | (every endpoint) | Missing or wrong CSRF token → **400** with "This form has expired…" (§6.1). The session is untouched. |

- **Logged out:** every route above redirects to `/login` through `login_required`, with no flash and no `next`.
- **Route variable:** it is renamed from `id` to `expense_id`, which stops it shadowing a Python builtin. The endpoint names (`add_expense`, `edit_expense`, `delete_expense`) stay the same.
- **Unchanged:** `/`, `/terms`, `/privacy` and `/profile`. `/profile` still shows sample figures. It only gains the `Cache-Control` header (§6.3).

## 4. Database
**No schema change.** The `expenses` table already has every column needed:
`id, user_id → users ON DELETE CASCADE, amount REAL NOT NULL, category TEXT NOT NULL, date TEXT NOT NULL ('YYYY-MM-DD'), description TEXT NULL, created_at`.

New helpers in `database/db.py`:
- Every query is parameterized and **scoped by `user_id`**.
- Writes follow the `seed_db()` pattern: `try` → `commit`, and `except` → `rollback` and re-raise.
- The names avoid clashing with the route functions in `app.py`.

| Helper | SQL (shape) | Returns |
|---|---|---|
| `list_expenses(user_id)` | `SELECT id, amount, category, date, description FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC` | list of rows (empty list if none) |
| `get_expense(expense_id, user_id)` | `… WHERE id = ? AND user_id = ?` | row or `None` |
| `create_expense(user_id, amount, category, date, description)` | `INSERT …` | new id |
| `update_expense(expense_id, user_id, amount, category, date, description)` | `UPDATE … WHERE id = ? AND user_id = ?` | `True` if a row changed |
| `remove_expense(expense_id, user_id)` | `DELETE … WHERE id = ? AND user_id = ?` | `True` if a row was deleted |

## 5. Validation — `validate_expense(form)` in `app.py`
It returns `(values, error)`:
- `values` always holds the **re-fill** strings (`amount`, `category`, `date`, `description`, as typed after normalisation).
- On success it also holds the parsed `amount_value` (a float rounded to 2 places), `date_value` and `description_value` (`None` when empty).
- `error` is the first failing message, or `None`.

**Normalisation:**
- **amount:** `strip()`, then commas are removed, so `"1,250.50"` becomes `"1250.50"`.
- **category:** `strip()`.
- **date:** `strip()`.
- **description:** `strip()`; an empty description is stored as `NULL`.

**Rules,** applied in this order; the first failure wins. Every failure returns 400.

| # | Rule | Message |
|---|---|---|
| 1 | Amount empty | Please enter an amount. |
| 2 | Amount not matching `^\d{1,10}(\.\d{1,2})?$` (rejects `nan`, `inf`, `1e3`, `1_000`, `-5`, `12.345`, `₹100`) | Enter the amount as a number, like 250 or 99.50. |
| 3 | Amount ≤ 0 | Amount must be more than zero. |
| 4 | Amount > `MAX_EXPENSE_AMOUNT` (1,00,00,000) | Amount must be ₹1,00,00,000 or less. |
| 5 | Category not exactly one of `CATEGORIES` (including empty) | Please choose a category from the list. |
| 6 | Date empty | Please choose a date. |
| 7 | Date not matching `^\d{4}-\d{2}-\d{2}$`, or not a real date. The format check comes first, because `date.fromisoformat` alone accepts `20261026` and `2026-W43-1`. | Enter a real date (YYYY-MM-DD). |
| 8 | Date after `date.today()` | Date can't be in the future. |
| 9 | Date before 2000-01-01 | Date must be in 2000 or later. |
| 10 | Description longer than 200 characters | Description must be 200 characters or fewer. |
| 11 | Description contains a control character (`Cc`) or a line or paragraph separator (`Zl`, `Zp`), the same rule as for names | Description contains invalid characters. |

**Boundaries:**

| Field | Accepted | Rejected |
|---|---|---|
| Amount | `0.01`, `1`, `99.5`, `1,250.50`, `10000000` | `0`, `0.00`, `10000000.01`, `12.345` |
| Date | today, `2000-01-01` | tomorrow, `1999-12-31` |
| Description | 200 characters | 201 characters |

## 6. `app.py`

### 6.1 CSRF (Auth helpers section)
- **`csrf_token()`** is registered as a Jinja global.
  - It returns `session["csrf_token"]`, creating it with `secrets.token_hex(32)` on first use.
  - It is **lazy**: only a page that renders a form writes the session. Redirects and form-less pages for logged-out visitors still send no `Set-Cookie`.
  - The token is hex, so it can never contain text like "None" (a Step 4 test checks the profile page for that string).
- **`@app.before_request check_csrf()`** is registered after `load_logged_in_user`.
  - It applies to `POST`, `PUT`, `PATCH` and `DELETE`.
  - It skips requests Flask couldn't route (`request.routing_exception` set, or `request.endpoint is None`). That keeps `POST /profile` at **405** and unknown URLs at **404**, because Flask runs `before_request` hooks before routing errors.
  - It compares `request.form.get("csrf_token", "")` with `session.get("csrf_token", "")` using `secrets.compare_digest`. A missing value on either side fails.
  - On failure: `abort(400, description="This form has expired. Go back, refresh the page and try again.")`. It never touches the session.
- **Rotation:** `start_session()` already clears the session at login, and `logout()` clears it too. Both drop the token, and the next form render creates a fresh one.
- **Template change:** every POST form gets `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` on its own line, so the existing markup tests still match. That covers `login.html`, `register.html`, the nav Sign out form in `base.html`, and the three new forms.

### 6.2 Routes (replace the Placeholder section; after `profile()`)
- Add `abort` to the `flask` import.
- Add `MAX_EXPENSE_AMOUNT = 10_000_000` with the other constants, and `validate_expense()` next to `validate_registration()`.
- `CATEGORIES` and the five helpers are imported from `database.db`.
- **`expenses()`:**
  - `@app.route("/expenses")`, then `@login_required`.
  - Renders `expenses.html` with `expenses=list_expenses(g.user["id"])`.
- **`add_expense()`:**
  - `methods=["GET", "POST"]`.
  - **GET:** renders `expense_form.html` with `mode="add"`, `values={"date": today}` and `categories=CATEGORIES`.
  - **POST:** runs `validate_expense`.
    - Invalid → re-render with `error` and `values`, status 400.
    - Valid → `create_expense`, then `flash("Expense added.", "success")`, then redirect to `expenses`.
- **`edit_expense(expense_id)`:**
  - Loads the expense with `get_expense(expense_id, g.user["id"])`, or `abort(404)`.
  - **GET:** pre-fills the form.
    - The amount is shown as `f"{amount:.2f}"`, with no grouping, so it validates again unchanged.
    - The description is shown as `''` when it is NULL.
  - **POST:** validate, then `update_expense`, flash and redirect. An invalid POST returns 400.
- **`delete_expense(expense_id)`:**
  - Loads the expense, or `abort(404)`.
  - **GET:** renders `expense_delete.html`.
  - **POST:** `remove_expense`, then flash and redirect.

### 6.3 `login_required` adds `Cache-Control: no-store`
- The wrapper turns the view's return value into a response (`make_response`) and sets `Cache-Control: no-store` on it.
- That covers `/profile` and every `/expenses` page, closing the gap spec 04 §15.5 left open.
- The redirect for logged-out visitors stays exactly as it is.

## 7. Templates and styles

### 7.1 Shared pieces (moved, not changed)
- **Icons:** the `icon(name)` macro moves from `profile.html` to **`templates/partials/icons.html`**, unchanged.
  - Both `profile.html` and the expense pages use `{% from "partials/icons.html" import icon %}`.
  - The profile's rendered HTML stays byte-for-byte the same (D8).
- **Styles:** the expense-display rules move from `profile.css` to a new **"Shared: expense lists"** section in `style.css`, without changes:
  - `.expense-table` and its `th`/`td`/`.num`/`.col-*` rules
  - `.expense-item`, `.expense-text`, `.expense-desc`, `.expense-meta`
  - `.category-pill`, `.category-icon`
  - the related ≤600px and ≤400px rules, and the `(hover: hover)` row tint
- **Form controls:** `style.css` gains rules for `select.form-input` (pointer cursor) and `input[type="date"].form-input` (inherits the font).

### 7.2 `templates/expenses.html` (new, extends `base.html`, `title` "Expenses — Spendly", `head` → `css/expenses.css`)
```
div.expenses-page
├── div.page-header: h1.page-title "Your expenses" · p.page-subtitle "{n} expense(s) · {total|inr} total" (omitted when empty)
│                    · a.btn-primary "+ Add expense" → url_for('add_expense')
├── flashes: get_flashed_messages(category_filter=["success"]) → div.auth-success[role=status] (same markup as login.html)
├── section.expenses-card (when there are expenses)
│   └── table.expense-table (caption.visually-hidden "All your expenses, newest first")
│       th[scope=col]: Date (.col-date) · Description · Category (.col-category) · Amount (.num) · Actions (.col-actions, visually-hidden label)
│       row: <time>|short_date · icon chip + desc ("No description") + meta line · pill · amount|inr
│            · a.row-action "Edit" → edit_expense · a.row-action.row-action--danger "Delete" → delete_expense
│            (each action link has a visually-hidden suffix naming the expense, e.g. "Edit <span class=visually-hidden>Groceries, 26 Oct 2026</span>")
└── div.empty-state (when there are none): icon, h2 "No expenses yet", p "Add your first expense to start tracking.",
                                             a.btn-primary "Add your first expense"
```
- **Totals:** the count and total come from the list itself (`expenses|length`, `expenses|sum(attribute="amount")`), so there is no extra query.
- **No pagination** (§15).

### 7.3 `templates/expense_form.html` (new, add and edit share it)
- **Layout:** the existing auth layout: `section.auth-section > div.auth-container > div.auth-header + div.auth-card`.
- **Title:** "Add an expense" or "Edit expense". The subtitle is "Amounts are in rupees (₹)."
- **Error:** `{% if error %}<div class="auth-error" role="alert">`.
- **Form:** `method="POST"`, with `action` set to `url_for('add_expense')` or `url_for('edit_expense', expense_id=…)`. It starts with the hidden CSRF input.
- **Fields:**

  | Field | Type | Attributes and behaviour |
  |---|---|---|
  | `amount` | `input type="text"` | `inputmode="decimal"`, `autocomplete="off"`, `maxlength="16"`, `required`, `autofocus`. Re-filled after an error. |
  | `category` | `select` | First option is `"" disabled` "Choose a category", then the 7 `CATEGORIES`. The re-filled choice is `selected`. `required`. |
  | `date` | `input type="date"` | `max="{{ today }}"`, `min="2000-01-01"`, `required`. Re-filled after an error. |
  | `description` | `input type="text"` | `maxlength="200"`, `autocomplete="off"`. The label says "(optional)". |

  `type="number"` is avoided for the amount because browsers let it accept `e`, change it on scroll, and handle commas differently by locale.
- **Buttons:** `button.btn-submit` "Add expense" or "Save changes". Below the card, `p.auth-switch` holds "Cancel" → `url_for('expenses')`.

### 7.4 `templates/expense_delete.html` (new)
- **Layout:** the auth layout, titled "Delete this expense?"
- **Summary card:** `dl.delete-summary` with Date, Description, Category and Amount.
- **Warning:** p.delete-warning, "This can't be undone."
- **Form:** `method="POST"` to `url_for('delete_expense', expense_id=…)`, holding the CSRF input and `button.btn-danger` "Delete expense".
- **Cancel** link back to `/expenses`.

### 7.5 `static/css/expenses.css` (new)
Existing tokens only, no `!important`.
- **Header:** `.expenses-page` uses the same container sizes as `.profile-page`. `.page-header` is flex, wraps, and has the title in the display font.
- **Card:** `.expenses-card` uses the profile-card look: white, border, `--radius-lg`, soft shadow.
- **Row actions:** small text buttons.
  - `--accent` for Edit, `--danger` for Delete.
  - An underline on hover.
  - A visible focus ring.
- **Empty state:** centred, with an icon chip, a muted line and the button.
- **Delete page:**
  - `.btn-danger`: full width, `--danger` background, white text, a darker shade on hover.
  - `.delete-summary` uses a two-column grid.
  - `.delete-warning` uses `--danger` text.
- **≤600px:** Date and Category hide, as on the profile, and the actions stack under the amount.

### 7.6 Nav (`base.html`, `style.css`, `landing.css`)
- **Logged-in nav:** `<a href="{{ url_for('expenses') }}" class="nav-expenses"…>Expenses</a>` comes first, then the profile avatar link, then Sign out. It gets `aria-current="page"` when `request.endpoint == 'expenses'`.
- **Phones (≤600px):**
  - The hiding selector becomes `a:not(.nav-cta, .nav-profile, .nav-expenses)` in **both** `style.css` and `landing.css`.
  - `.navbar` padding drops to `0 1rem` and `.nav-links` gap to `1rem`, so the brand, Expenses, avatar and Sign out fit at 360px.
  - This is checked in the browser.
- **Sign out form:** it gains only the hidden CSRF input, on its own line.

## 8. Files to change
- `app.py`: CSRF, validation, the 4 routes, `abort`/`make_response` imports, `login_required` headers.
- `database/db.py`: 5 helpers.
- `templates/base.html`: nav Expenses link, logout CSRF input.
- `templates/login.html`, `templates/register.html`: CSRF input.
- `templates/profile.html`: replace the macro definition with the import line (rendered output unchanged).
- `static/css/style.css`: shared expense-list rules (moved), form controls, nav at ≤600px.
- `static/css/profile.css`: the moved rules removed.
- `static/css/landing.css`: nav selector, ≤600px padding and gap.
- `tests/test_auth.py`:
  - the POST helpers send the CSRF token
  - `test_logout_without_session_cookie_sets_no_cookie` now expects **400** and still no `Set-Cookie`
- `tests/test_profile.py`:
  - the two direct `/login` POSTs send the token
  - `test_profile_has_no_dead_links` drops its "no `/expenses` links" rule, since `/expenses` is now real, and still GETs every link
- `tests/test_routes.py`: delete `test_stub_routes_unchanged`, because no stubs are left.
- `CLAUDE.md`:
  - route table and roadmap
  - architecture tree
  - the session rule (it now holds `user_id`, `csrf_token` and `_flashes`)
  - the CSRF section
  - the flash rule (rendered in `login.html` and `expenses.html`, never in `base.html`)
  - DB helpers
  - `login_required` (`no-store`)

## 9. Files to create
- `templates/expenses.html`, `templates/expense_form.html`, `templates/expense_delete.html`
- `templates/partials/icons.html`
- `static/css/expenses.css`
- `tests/test_csrf.py`, `tests/test_expenses.py`

## 10. Dependencies
- No new packages. Flask-WTF is not installed, and none may be added.
- Stdlib only: `secrets` (already imported), `datetime`, `re` and `unicodedata`.
- No JavaScript.

## 11. Outcomes

| # | Situation | Result | Status |
|---|---|---|---|
| 1 | Any `/expenses…` route, logged out | Redirect to `/login` | 302 |
| 2 | `GET /expenses` | Own expenses, newest first, with count and total; empty state if none | 200 |
| 3 | `POST /expenses/add`, valid | Inserted; flash; redirect to `/expenses` | 302 |
| 4 | Add or edit with invalid input | Form re-rendered with one error and the typed values | 400 |
| 5 | Edit or delete (GET or POST) another user's id, or an id that doesn't exist | Not found; nothing changes | 404 |
| 6 | `GET …/delete` | Confirmation page; nothing deleted | 200 |
| 7 | `POST …/delete` | Deleted; flash; redirect | 302 |
| 8 | Any POST with a missing or wrong CSRF token | "This form has expired…"; session untouched; nothing changes | 400 |
| 9 | `POST /profile` or a POST to an unknown URL | Unchanged (CSRF skipped) | 405 / 404 |
| 10 | Another site's form POSTs to `/logout` (no cookie, no token) | Rejected; no `Set-Cookie`; user stays signed in | 400 |
| 11 | Login-required page | Response has `Cache-Control: no-store` | — |

## 12. Rules for implementation
- All SQL lives in `db.py`, parameterized and filtered by `user_id`. Routes never trust an id they haven't looked up with `user_id`.
- No GET request ever changes data. Delete is POST-only, behind a confirmation page.
- Every POST form includes the CSRF input. The check runs before every view, and a failure never modifies the session.
- Errors use `abort(404)` and `abort(400)`. Form errors re-render with `error=` and a 400, just like register and login.
- Money is shown with `|inr` and dates with `|short_date`. The amount field is re-filled as plain `1250.50`.
- `sample_data.py`, `get_profile_sample()`, the `profile()` body and the profile's sample badge are untouched (Step 6).
- Flashes render in `login.html` and `expenses.html` only, never in `base.html`.
- `pytest` leaves `spendly.db` byte-for-byte unchanged.

## 13. Expected behaviour
- **Demo user** (`demo@spendly.com` / `demo123`):
  - Lands on `/profile`.
  - Opens **Expenses** in the nav and sees the 8 seeded expenses, newest first, with "8 expenses · ₹7,267.00 total".
  - **Add expense:** enters ₹1,250.50, Food, today and "Lunch". They're back on `/expenses` with "Expense added." The new row is at the top, and the total is ₹8,517.50.
  - **Edit** that row to ₹1,300. "Expense updated." appears, and the row shows ₹1,300.00.
  - **Delete:** the confirmation page shows the expense. Confirming leads to "Expense deleted." and the row is gone.
- **Invalid input:** `abc`, `0`, a future date or no category re-render the form with the matching message and keep what was typed.
- **Other users' data:** opening `/expenses/1/edit` while signed in as someone who doesn't own expense 1 gives 404.
- **New user:** sees the empty state with "Add your first expense".
- **Stale form:** if a form was opened before the dev server restarted without a fixed `SECRET_KEY`, submitting it gives the 400 "This form has expired…" page. Refreshing fixes it.

## 14. Definition of done
Test names are proposals.

**CSRF** (`tests/test_csrf.py`)
- [ ] Every POST form includes the hidden token: login, register, the nav Sign out, add, edit and delete — `test_every_post_form_has_csrf_field`
- [ ] Each POST endpoint returns 400 without a token and with a wrong one, and nothing changes — `test_post_without_valid_token_is_rejected` (parametrized)
- [ ] The token scraped from the rendered form is accepted — `test_rendered_token_is_accepted`
- [ ] A CSRF failure doesn't touch the session (no `Set-Cookie`) — `test_csrf_failure_leaves_session_alone`
- [ ] The token is created lazily: a logged-out `GET /` and `GET /profile` still send no `Set-Cookie` — `test_token_created_only_when_a_form_renders`
- [ ] Login rotates the token; it isn't carried across — `test_login_rotates_csrf_token`
- [ ] `POST /profile` is still 405, and a POST to an unknown URL is 404 — `test_routing_errors_bypass_csrf`
- [ ] The token is 64 hex characters — `test_csrf_token_is_hex`

**Expenses** (`tests/test_expenses.py`)
- [ ] All 7 route/method pairs redirect a logged-out visitor to `/login` — `test_expense_routes_require_login`
- [ ] The list shows only the user's own expenses, newest first (date, then id), with count and total; the demo user sees 8 and ₹7,267.00 — `test_list_shows_own_expenses_newest_first`, `test_demo_user_sees_seeded_expenses`
- [ ] Empty state with the add link — `test_list_empty_state`
- [ ] A valid add inserts exactly one row with the parsed values, redirects, and the flash shows once — `test_add_expense_success`
- [ ] Every validation rule (1–11) gives 400 with its message and no row, and the typed values come back — `test_add_expense_validation` (parametrized)
- [ ] Boundaries from §5; commas are accepted; an empty description is stored as NULL — `test_add_expense_boundaries`
- [ ] Edit: GET is pre-filled; a valid POST updates the row and flashes; an invalid POST gives 400 and no change — `test_edit_expense_*`
- [ ] Edit, delete and their POSTs on another user's or a missing id give 404 and change nothing — `test_cannot_touch_other_users_expenses`
- [ ] A delete GET shows the confirmation and doesn't delete; a POST deletes and flashes — `test_delete_expense_*`
- [ ] Descriptions are HTML-escaped — `test_expense_description_is_escaped`
- [ ] `Cache-Control: no-store` on `/profile` and the expense pages — `test_login_required_pages_are_not_cached`
- [ ] The nav Expenses link shows only when logged in, with `aria-current` on `/expenses` — `test_nav_expenses_link`
- [ ] No dead links on `/expenses` and the form pages — `test_expense_pages_have_no_dead_links`
- [ ] DB helpers are scoped by `user_id` — `test_db_helpers_are_scoped_to_user`

**Suite**
- [ ] The updated `test_auth.py`, `test_profile.py` and `test_routes.py` pass. The full `pytest` passes, `spendly.db` is unchanged, and a subagent verifies it.
- [ ] Screenshots at 1280, 900, 375 and 360px of the list, form, delete page and empty state, plus the nav at 360px on `/`.
- [ ] Manual browser check (yours).

## 15. Known gaps (decided; not in Step 5)
1. **`/profile` still shows sample figures.** Real calculations and the designed profile empty state come in Step 6.
2. **No pagination, search or filters** on `/expenses`. That's fine for personal-scale lists; revisit in Step 6.
3. **"Today"** for the future-date check uses the server's local date, not the user's time zone.
4. **No index on `expenses(user_id, date)`.** It isn't needed at this scale. If one is added, it goes through `migrate_db()`.
5. **The CSRF 400 page is Werkzeug's default page**, though it shows our message. There is no custom error template yet.
6. **No undo after delete.** The confirmation page is the safeguard.
7. **No `next` parameter.** Login always lands on `/profile`.
8. **No `updated_at` column.** Edits don't record when they happened.

## 16. Out of scope
- Real profile figures, charts, date-range filters and monthly summaries (Step 6)
- Income records, budgets and custom categories (the user chose the fixed list)
- Bulk delete, CSV import/export, attachments and receipts
- Changes to registration and login beyond adding the CSRF field
