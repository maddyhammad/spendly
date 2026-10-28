# Spec: Step 4 — Profile page design

> **Status:** ✅ Implemented on `feature/profile-page` (2026-10-28). 141 tests pass (46 new in
> `tests/test_profile.py`), verified by a subagent; `pytest` leaves `spendly.db` unchanged.
> §14 awaits only your browser check.
> Step 4 is a **design step**. `/profile` becomes a real page for signed-in users.
> - The user's **name and email are real**, from `g.user`.
> - **Every financial figure is fixed sample data** from `sample_data.py`.
> - No database queries, no schema change, and no change to `database/db.py`.
> - **Signed-in users are redirected to `/profile`**: after login, and from `/login` and `/register`
>   (D3, revised 2026-10-28 at the user's request). Otherwise login, registration and logout are unchanged.
>
> Decisions D1–D14 and the build order are in `.claude/plans/04-profile-page-design.md`.
>
> **Roadmap:**
> - **Step 5:** expense management (add, edit, delete). CSRF tokens must come first.
> - **Step 6:** data integration. It replaces `sample_data.py` with real queries and designs the empty states.

## 1. Overview
A signed-in user opens `/profile`, either from the **nav link** (their initial avatar and "Hi, {name}")
or by typing the URL. The page shows:
- **Account card:** initial avatar, "Your profile", the name and the email.
- **Spending summary:**
  - the period label
  - a **"Sample data"** badge and a one-line note explaining it
  - three tiles: total spent, number of expenses, top category and its amount
- **By category:** one row per category. Name, amount and share sit on the first line, and a full-width bar underneath shows the share of the total.
- **Recent expenses:** the latest five, with date, description, category and amount.

Logged-out visitors are sent to `/login`. Signing in lands on `/profile`, and a signed-in user who
opens `/login` or `/register` is sent there too (D3).

## 2. Depends on
- Step 3: the `before_request` hook that loads `g.user`, the nav in `base.html`, and `/login`.
- Step 1: the `CATEGORIES` tuple. Every sample category must be in it. The sample figures mirror the
  demo expenses in `SAMPLE_EXPENSES`, and a test checks this.

## 3. Routes

| Method | Path | Behaviour |
|---|---|---|
| `GET` | `/profile` | **Implemented (was a stub).** Logged in: render `profile.html` (200). Logged out, including a deleted user's stale `user_id`: redirect (302) to `/login`, with no flash and the session untouched. |
| other | `/profile` | 405 Method Not Allowed (Flask default; it runs before the decorator). |

**Changed redirects** (only the target; every check and message is unchanged):

| Method | Path | Before | Now |
|---|---|---|---|
| `POST` | `/login` (success) | 302 → `/` | 302 → `/profile` |
| `GET`, `POST` | `/login` while signed in | 302 → `/` | 302 → `/profile` |
| `GET`, `POST` | `/register` while signed in | 302 → `/` | 302 → `/profile` |

**Unchanged:**
- `/logout`, and registration still redirecting to `/login` (it never logs in).
- `/` stays reachable for signed-in users.
- The `/expenses/*` stubs. Their text still says Steps 7–9 (D12).

## 4. Database changes
None: no schema change, no migration, and `database/db.py` is untouched. As a result, the page has no
"member since" line, because `get_user_by_id()` doesn't select `created_at` (D5).

## 5. Sample data (`sample_data.py`, new, repo root)
**Who uses it:**
- Only `profile()` imports this module. It touches neither Flask nor the database.
- Every call returns a **fresh** dict, so a change made by one caller can't leak into another.

**Step 6 swap:**
- Step 6 deletes the module and adds real helpers to `db.py` that return the **same keys and shapes**, then changes one line in `profile()`.
- The keys match the future `expenses` columns (`category`, `amount`, `date`, `description`), so `sqlite3.Row` objects can go straight into the template (D4).
- Avoid key names that are also dict method names (`items`, `keys`, `values`), because Jinja's dot lookup would find the method instead.

```python
def get_profile_sample():
    """Return the template context for profile.html (a new dict on every call)."""
    return {
        "period_label": "October 2026",
        "summary": {"total": 7267.00, "count": 8, "top_category": "Bills", "top_amount": 2499.00},
        # Highest amount first; share = whole-number % of summary["total"].
        "category_totals": [
            {"category": "Bills", "amount": 2499.00, "share": 34},
            {"category": "Shopping", "amount": 1899.00, "share": 26},
            {"category": "Food", "amount": 1100.00, "share": 15},
            {"category": "Health", "amount": 850.00, "share": 12},
            {"category": "Entertainment", "amount": 499.00, "share": 7},
            {"category": "Other", "amount": 300.00, "share": 4},
            {"category": "Transport", "amount": 120.00, "share": 2},
        ],
        # Newest first, at most 5. ISO date strings, like expenses.date.
        "recent_expenses": [
            {"date": "2026-10-26", "description": "Dinner with friends", "category": "Food", "amount": 650.00},
            {"date": "2026-10-22", "description": "Gift wrapping", "category": "Other", "amount": 300.00},
            {"date": "2026-10-19", "description": "New shoes", "category": "Shopping", "amount": 1899.00},
            {"date": "2026-10-15", "description": "Movie tickets", "category": "Entertainment", "amount": 499.00},
            {"date": "2026-10-12", "description": "Pharmacy", "category": "Health", "amount": 850.00},
        ],
    }
```

**Invariants** (tested):
- **Keys:** exactly `period_label`, `summary`, `category_totals` and `recent_expenses`.
- **Category totals:**
  - the amounts sum to `summary.total`
  - the rows are sorted by amount, highest first, with no repeated category
  - every category is in `CATEGORIES`
  - `top_category` and `top_amount` equal the first row
  - each share is `round(amount / total * 100)`, and the shares sum to 100
- **Recent expenses:**
  - exactly 5, and no more than `count`
  - valid ISO dates, newest first, all within `period_label`
  - every category appears in `category_totals`
- **Mirrors the seed:**
  - `total` equals the sum of the `SAMPLE_EXPENSES` amounts, and `count` equals `len(SAMPLE_EXPENSES)`
  - the per-category sums match `category_totals`
  - every recent expense is a `SAMPLE_EXPENSES` entry

## 6. `app.py`
- **Imports:**
  - stdlib group: `import functools` and `from datetime import date`
  - local group, after the `database.db` import: `from sample_data import get_profile_sample`
- **`login_required(view)`** goes in the Auth helpers section, after `start_session()`.
  - It is wrapped with `functools.wraps`, so the endpoint keeps the name `profile` for `url_for`.
  - If `g.user is None`, it returns `redirect(url_for("login"))`. Otherwise it calls the view.
  - No flash: `login.html` renders only `success` flashes.
  - No `next`, because that would change `login()`.
  - It never touches the session.
  - It redirects rather than calling `abort(401)`. Sending a visitor to sign in is a navigation, not
    an error, just as `register()` and `login()` redirect.
- **`profile()`** moves out of the Placeholder section and sits after `privacy()`. The decorator order is
  `@app.route("/profile")`, then `@login_required`. The body has one responsibility:
  `return render_template("profile.html", **get_profile_sample())`.
  - It calls `get_profile_sample` by its global name, because the tests monkeypatch `app.get_profile_sample`.
- **Template filters:** a new "Template filters" section between `validate_registration()` and the
  Routes banner. They outlive the sample data (D6).
  - **`inr(value)`:** two decimals with Indian digit grouping, built with a regex over the whole-rupee part.

    | Input | Output |
    |---|---|
    | `0` | `₹0.00` |
    | `999` | `₹999.00` |
    | `1000` | `₹1,000.00` |
    | `7267` | `₹7,267.00` |
    | `99999.99` | `₹99,999.99` |
    | `100000` | `₹1,00,000.00` |
    | `248500` | `₹2,48,500.00` |
    | `1234567.5` | `₹12,34,567.50` |
    | `10000000` | `₹1,00,00,000.00` |
    | `-1200` | `−₹1,200.00` (U+2212) |
    | `-0.001` | `₹0.00` (never `−₹0.00`) |

    `None` or text raises an error on purpose: amounts are `REAL NOT NULL`, and the template guards the one nullable case.
  - **`short_date(value)`:** `date.fromisoformat(value)`, formatted as `f"{d.day} {d:%b %Y}"`, because `%-d` fails on Windows.
    - `"2026-10-26"` → `26 Oct 2026`, `"2026-01-05"` → `5 Jan 2026`.
    - `None`, `""`, `"not-a-date"` and `"2026-02-30"` are returned unchanged.

## 7. Templates and styles

### `templates/base.html` (changed, D3)
Only the logged-in nav line changes. `<span class="nav-user">` becomes:
```html
<a href="{{ url_for('profile') }}" class="nav-profile"{% if request.endpoint == 'profile' %} aria-current="page"{% endif %}>
    <span class="nav-avatar" aria-hidden="true">{{ g.user['name'][:1]|upper }}</span>
    <span class="nav-user-text">Hi, {{ g.user['name'] }}</span>
</a>
```
- "Hi, {name}" stays as one text node, so the existing `test_auth.py` assertions still pass.
- The Sign out `<form>` and `<button>` are byte-identical.
- The `nav-user` class is retired; no test uses it.

### `templates/profile.html` (new)
- Extends `base.html`.
- `title`: `Profile — Spendly`.
- `head`: `<link>` to `url_for('static', filename='css/profile.css')`.
- **No literal ₹ sign, year, month or figure** appears in the template, and a test checks this. Even the caption's count comes from `|length`.
- **No links in the page body.** The only interactive elements are in the nav and footer.

```
div.profile-page
├── section.profile-card.account-card[aria-labelledby="profile-name"]
│   ├── span.profile-avatar[aria-hidden]  initial
│   └── div.account-details: p.profile-eyebrow "Your profile" · h1.profile-name#profile-name · p.profile-email
├── section.profile-card[aria-labelledby="summary-title"]
│   ├── div.card-header: (h2.card-title#summary-title "Spending summary" + p.card-subtitle {{ period_label }})
│   │                    · span.sample-badge "Sample data"
│   ├── p.sample-note  "All amounts on this page are examples that preview the layout. Your own spending
│   │                   will appear here in a later update."
│   └── dl.stat-grid: 3 × div.stat-tile > dt.stat-label + dd.stat-value
│       ├── Total spent   {{ summary.total|inr }}
│       ├── Expenses      {{ summary.count }}
│       └── Top category  {{ summary.top_category }} + dd.stat-note {{ summary.top_amount|inr }}
│                         (if top_category is falsy: dd.stat-value "—" and no note)
└── div.profile-columns
    ├── section.profile-card[aria-labelledby="categories-title"]  h2 "By category"
    │   ol.category-list[role="list"] > li.category-row:
    │     span.category-name · span.category-amount (|inr) · span.category-share "N%"
    │     · span.category-track[aria-hidden] > span.category-bar[style="--share: N%"]
    │   empty → p.empty-note "No spending to show yet."
    └── section.profile-card[aria-labelledby="recent-title"]  h2 "Recent expenses"
        table.expense-table
          caption.visually-hidden "Your {{ recent_expenses|length }} most recent expenses (sample data)"
          th[scope=col]: Date (.col-date) · Description · Category (.col-category) · Amount (.num)
          row: td.col-date <time datetime> |short_date
               td: span.expense-desc (description or "No description")
                   + span.expense-meta (category-pill + <time>|short_date)   ← phones only
               td.col-category span.category-pill · td.num |inr
        empty → p.empty-note "No expenses yet." (no table)
```
- The rows are an `<ol>` because they are ranked by amount.
- `role="list"` restores the list semantics Safari drops under `list-style: none`.
- A screen reader hears "Bills, ₹2,499.00, 34%"; the bar is silent.

### Visual refresh (2026-10-28, at the user's request: "a bit more attractive")
The structure above still applies. These additions sit on top of it (plan D14):
- **Hero:**
  - The account card is a deep-green banner (`--accent`), lit by two soft pale-green radial glows, with two thin decorative rings drawn with `::before` and `::after`.
  - The avatar is white with a green initial and a translucent ring.
  - The text is white, with the eyebrow at 72% opacity and the email at 82%.
- **Icons:**
  - An `icon(name)` Jinja macro, defined inside the `content` block, draws small inline-SVG line icons. Every one is `aria-hidden="true" focusable="false"`, and no icon library is used.
  - Each category has its own icon (Food, Transport, Bills, Health, Entertainment, Shopping); Other and any unknown name fall back to dots.
  - The stat tiles use wallet, list and star icons.
- **Stat tiles:**
  - Each `dt.stat-label` starts with an icon chip, `span.stat-icon`.
  - "Total spent" is the featured tile (`stat-tile--featured`): an `--accent-light` background and the value in `--accent`.
- **Extra stat lines** (`dd.stat-meta`), all computed in the template from the context:
  - "Across N categories", shown only when there are categories.
  - "Avg ₹X each", only when `count` is above 0, so there is never a division by zero.
  - "N% of total spending" for the top category.
- **Category rows:** a `span.category-icon` chip on the left spans both grid rows. The bars are 8px tall.
- **Expense rows:**
  - The Description cell is a `div.expense-item`: the icon chip, then `div.expense-text` holding the description and the phone-only meta line.
  - At ≤400px the row icon is hidden, because the pill already names the category.
- **Motion and depth:**
  - The cards have a soft resting shadow and fade up on load, staggered by 0.06s.
  - The bars grow from 0 to their share.
  - On hover-capable devices, the stat tiles lift by 2px.
  - All of this motion is off under `prefers-reduced-motion`.
- **Sample note:** it is now a quiet callout on a `--paper` background with an amber left border.
- **Phones (≤600px):** the stat tiles put the icon beside the label, to keep the tiles short.

### `static/css/profile.css` (new)
Use existing tokens only (one exception: the badge border tint), with no `!important`.
- **Layout:**
  - `.profile-page`: `max-width: var(--max-width)`, centred, padding `2.5rem 2rem 4rem`, `display: grid` with a `1.5rem` gap.
  - `.profile-columns`: `minmax(0, 2fr) minmax(0, 3fr)` with a `1.5rem` gap and `align-items: start`.
- **Cards:**
  - `.profile-card`: `--paper-card` background, `1px solid var(--border)`, `--radius-lg`, padding `1.75rem`, a `box-shadow` transition of 0.2s.
  - `.card-header`: flex and wrapping, `space-between`, `0.75rem` gap.
  - `.card-title`: display font, 1.35rem.
  - `.card-subtitle`, `.sample-note` and `.empty-note`: `--ink-muted`, 0.875rem.
- **Account card:**
  - `.account-card`: flex with the items centred and a `1.25rem` gap.
  - `.profile-avatar`: a 4.5rem circle, `--accent` background, white text (10.6:1), display font at 2rem.
  - `.account-details`: `min-width: 0`.
  - `.profile-eyebrow`: 0.75rem, 600, uppercase, letter-spaced, muted.
  - `.profile-name`: display font, `clamp(1.75rem, 3vw, 2.25rem)`, `overflow-wrap: anywhere`.
  - `.profile-email`: muted, `overflow-wrap: anywhere`.
- **Badge:** `.sample-badge` is an inline-flex pill.
  - `--accent-2-light` background, `1px solid #f0dcb8` border.
  - **`--ink-soft` text** (12.5:1). Amber text would be only 3.0:1.
  - 0.75rem, 600, uppercase, `nowrap`.
  - A `::before` `--accent-2` dot as decoration.
- **Stats:**
  - `.stat-grid`: `repeat(3, minmax(0, 1fr))` with a `1rem` gap. `dd` has no margin.
  - `.stat-tile`: `--paper` background, `1px solid var(--border-soft)`, `--radius-md`, padding `1.25rem`.
  - `.stat-label`: 0.85rem, muted.
  - `.stat-value`: **DM Sans 600** with proportional figures, at `clamp(1.5rem, 2.5vw, 1.9rem)`. Figures use the body sans and headings use the serif.
  - `.stat-note`: muted.
- **Category rows:**
  - `.category-list`: no bullets, grid, `1rem` gap.
  - `.category-row`: a grid, `minmax(0,1fr) auto auto`, with the areas `"name amount share" "bar bar bar"` and a `0.4rem` row gap.
  - The amount and share use `tabular-nums`. The share is muted, with a minimum width of `2.75rem`.
  - `.category-track`: 8px tall, `--accent-light`, radius 4px, `overflow: hidden`.
  - `.category-bar`: `width: var(--share, 0%)`, `--accent`. It is rounded only at the data end (`0 4px 4px 0`).
  - It is a single series with direct labels, so it needs no legend and no tooltip.
- **Table:**
  - `.expense-table`: full width, collapsed borders, 0.9rem.
  - `th`: 0.75rem, uppercase, muted, with a `1px var(--border)` bottom border.
  - `td`: padding `.85rem .75rem`, with a `--border-soft` bottom border. The last row has none.
  - `.num`: right-aligned, `nowrap`, `tabular-nums`, 500.
  - `.col-date`: `nowrap`, muted.
  - `.expense-desc`: 500, `overflow-wrap: anywhere`.
  - `.category-pill`: `--accent-light` background, `--accent` text (9.2:1), pill-shaped, 0.75rem, 600.
  - `.expense-meta`: `display: none` by default.
- **Hover:** only inside `@media (hover: hover)`, so taps don't leave a hover state stuck on touch screens. Nothing lifts, because nothing on the page is clickable.
  - `.profile-card:hover`: shadow `0 8px 30px rgba(0,0,0,.06)`.
  - `.stat-tile:hover`: the border changes to `--border`.
  - `.category-row:hover` and `tbody tr:hover`: `--paper` background.
- **≤900px:** `.profile-columns` collapses to one column.
- **≤600px:**
  - `.profile-page`: padding `1.5rem 1rem 3rem`, `1rem` gap.
  - `.profile-card`: `1.25rem` padding, `--radius-md`.
  - `.profile-avatar`: 3.5rem.
  - `.stat-grid`: one column.
  - `.col-date` and `.col-category` are hidden, and `.expense-meta` is `flex` (wrap, small, muted).
  - So each fact appears once at every width.
- **Motion:** `prefers-reduced-motion: reduce` turns off the transitions.

### `static/css/style.css` (changed)
- **Nav:**
  - Delete `.nav-user { … }` (line 105).
  - Add after `button.nav-cta`:
    - `.nav-profile`: inline-flex, items centred, `0.5rem` gap.
    - `.nav-avatar`: a 2rem circle, `--accent` background, `--paper-card` text, 0.85rem, 600.
    - `.nav-user-text`: `max-width: 14rem` with an ellipsis.
    - Hover, and `[aria-current="page"]`: a ring around the avatar (`0 0 0 2px var(--paper), 0 0 0 4px var(--accent)`).
    - `.nav-profile[aria-current="page"]`: `color: var(--ink)`.
- **Utilities** (a new section before Responsive), D10:
  - `.visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }`
- **The ≤600px block:**
  - `.nav-links a:not(.nav-cta), .nav-user { display: none; }` becomes `.nav-links a:not(.nav-cta, .nav-profile) { display: none; }`.
  - Add `.nav-user-text { /* the .visually-hidden declarations */ }`.
  - Phones then show only the avatar.
  - The name is **visually hidden, never `display: none`**, because it is the link's only accessible name (the avatar is `aria-hidden`).

### `static/css/landing.css` (changed)
At line 528, change `.nav-links a:not(.nav-cta)` to `.nav-links a:not(.nav-cta, .nav-profile)`. Nothing else changes:
`.nav-user-text` comes from `style.css`, which applies on `/` as well.

## 8. Files to change
- `app.py`: imports, `login_required`, `profile()`, the 2 filters, and the 3 signed-in redirect
  targets in `register()` / `login()` (`url_for("landing")` → `url_for("profile")`).
- `templates/base.html`: the nav link.
- `tests/test_auth.py`: the 5 redirect assertions now expect `/profile`.
- `static/css/style.css`: the nav profile link and avatar, the `.visually-hidden` utility, the ≤600px block.
- `static/css/landing.css`: one selector.
- `tests/test_routes.py`: remove `("/profile", "Step 4")` from `test_stub_routes_unchanged`.
- `CLAUDE.md` (D13):
  - architecture tree
  - "Where things belong" (`sample_data.py`)
  - code style (`|inr`, `|short_date`, the `--share` style-attribute exception)
  - Authentication section: `login_required`, the nav link, signed-in users go to `/profile`, CSRF before Step 5
  - route table
  - roadmap

## 9. Files to create
- `sample_data.py`
- `templates/profile.html`
- `static/css/profile.css`
- `tests/test_profile.py`

## 10. Dependencies
No new pip packages and no JavaScript. Stdlib only: `functools`, `datetime`.

## 11. Outcomes

| # | Situation | Result | Status |
|---|---|---|---|
| 1 | `GET /profile`, logged out | Redirect to `/login`; no flash; no `Set-Cookie` | 302 |
| 2 | `GET /profile` with a deleted user's stale `user_id` | Redirect to `/login`; the stale id stays in the session | 302 |
| 3 | `GET /profile`, logged in | Real name and email, plus sample figures with the badge and note | 200 |
| 4 | `POST /profile` (logged in or out) | Method Not Allowed | 405 |
| 5 | Any page, logged in | The nav shows the avatar and "Hi, {name}" linking to `/profile` (avatar only at ≤600px); `aria-current="page"` on `/profile` only | — |
| 6 | Any page, logged out | No link to `/profile` | — |
| 7 | Successful login | Redirect to `/profile` | 302 |
| 8 | `GET`/`POST` `/login` or `/register` while signed in | Redirect to `/profile`; nothing is checked or created | 302 |

## 12. Rules for implementation
- In `register()` and `login()` only the redirect targets for signed-in users change. Do not touch their
  checks or messages, nor `logout()`, `start_session()`, `validate_registration()` or `database/db.py`.
- Financial figures reach the template **only** through `get_profile_sample()`, never through SQL. Only `profile()` imports `sample_data`.
- Every internal link uses `url_for()`. Nothing links to a stub route, and the page body has no links.
- Page styles go in `profile.css`, never in a `<style>` tag. The only `style` attribute is the data value `--share`.
- User data stays autoescaped. Never use `|safe`.
- The decorator order is `@app.route` first, then `@login_required`, always with `functools.wraps`.
- The session still holds only `user_id` (plus `_flashes`). `login_required` never writes to it.
- `pytest` must leave `spendly.db` byte-for-byte unchanged.

## 13. Expected behaviour
- Log in as `demo@spendly.com` / `demo123`: you land straight on `/profile`, where the nav avatar has a ring.
  Opening `/login` or `/register` again sends you back to `/profile`. The "D" avatar links there from every page.
- The account card shows "D", "Your profile", "Demo User" and `demo@spendly.com`.
- The summary shows "October 2026", the badge and note, `₹7,267.00`, `8`, and "Bills" with `₹2,499.00`.
- "By category" shows 7 rows, from Bills (34%, the longest bar at about a third of the track) down to Transport (2%).
- "Recent expenses" shows 5 rows, newest first: "26 Oct 2026 · Dinner with friends · Food · ₹650.00".
- At ≤600px:
  - the nav shows only the avatar and Sign out, on every page including `/`
  - the stat tiles stack
  - the table shows Description and Amount, with the category pill and date underneath
  - nothing scrolls sideways
- Opening `/profile` while logged out lands on `/login`, with no message.

## 14. Definition of done
Tests in `tests/test_profile.py`. The helpers come from `tests.test_auth`.

**Access**
- [x] Logged out → 302 `/login`, no `Set-Cookie`, no `user_id` — `test_profile_requires_login`
- [x] Deleted user → 302 `/login`, and the stale `user_id` is untouched — `test_profile_for_deleted_user_redirects_to_login`
- [x] `POST` → 405, logged in and logged out — `test_profile_rejects_post`
- [x] Signing in (redirects followed) ends on `/profile` with the user's name — `test_signing_in_lands_on_profile`
- [x] The seeded demo user lands on `/profile` — `test_seeded_demo_user_lands_on_profile`
- [x] Signed in, `/login` and `/register` lead to `/profile` — `test_signed_in_user_is_sent_from_auth_pages_to_profile`
- [x] The 5 redirect assertions in `test_auth.py` expect `/profile`

**Rendering**
- [x] 200, the title, the h1 name, the email, the avatar initial, and `profile.css` linked (and not linked on `/`) — `test_profile_renders_for_logged_in_user`
- [x] All three headings, the stat labels, the badge and the period — `test_profile_renders_all_sections`
- [x] Every sample figure, share, `--share` style, date and amount; 5 rows, newest first — `test_profile_shows_sample_figures`
- [x] With the monkeypatched sample, its values show and the real sample's don't — `test_profile_figures_come_from_sample_module`
- [x] The template source has no "₹", no year and no month name — `test_profile_template_has_no_hardcoded_figures`
- [x] Empty lists and a `None` top category → 200, the empty notes, no table, no literal "None" — `test_profile_renders_empty_sample`
- [x] HTML in the name or email is escaped in the h1, nav, avatar and email — `test_profile_escapes_user_data`
- [x] Caption present, 4 `scope="col"` headers, one `aria-hidden` track per category — `test_profile_table_and_bars_are_accessible`
- [x] Every `href`/`src` returns 200 (fonts excepted), no `/expenses` links, and the only form action is `/logout` — `test_profile_has_no_dead_links`

**Nav**
- [x] On `/`: the profile link, the avatar, "Hi, Asha Rao", and no `aria-current` — `test_nav_links_to_profile_when_logged_in`
- [x] On `/profile`: `aria-current="page"` exactly once — `test_nav_marks_profile_as_current_page`
- [x] Logged out, on `/`, `/login`, `/register`, `/terms` and `/privacy`: no `href="/profile"` — `test_nav_has_no_profile_link_when_logged_out`

**Sample data and filters**
- [x] The §5 invariants hold — `test_sample_data_is_consistent`
- [x] The sample matches `SAMPLE_EXPENSES` — `test_sample_data_mirrors_seed`
- [x] Each call returns a fresh copy — `test_sample_data_returns_fresh_copy`
- [x] The `inr` table in §6 — `test_inr`
- [x] `short_date` valid and bad input — `test_short_date`
- [x] Both filters are registered on `app.jinja_env` — `test_filters_are_registered`

**Suite**
- [x] The `/profile` stub case is removed and the Step 7–9 cases still pass (`test_routes.py`)
- [x] `pytest` (full suite) passes with the expected count, and `spendly.db` is unchanged. A subagent verifies both, per CLAUDE.md.
- [ ] Manual browser check (yours):
  - 1440, 1024, 900, 600, 375 and 360px
  - `/` at 360px while logged in
  - keyboard Tab order
  - hover
  - a long name and email
  - reduced motion

## 15. Known gaps (decided; not in Step 4)
1. **The financial figures are fake** and dated October 2026 until Step 6. The badge and note say so.
2. **Signed-in users land on sample figures.** Login now goes straight to `/profile`, so until Step 6
   every user sees the sample spending there; the badge and note make that clear.
3. **No `next` parameter.** Every login lands on `/profile`, wherever the user started.
4. **No "member since"**, because it would need `created_at` from `db.py` (D5).
5. **No `Cache-Control: no-store`.** After sign-out, the Back button may show a cached profile page. Add it with real data in Step 6.
6. **`inr` rounds binary floats half-to-even** (`2.675` → `₹2.67`). With real data, rounded shares may total 99 or 101.
7. **An initial taken with `[:1]`** can split an emoji or a combining character.
8. **The stub text still says Steps 7–9**, and logged-out phones still hide "Sign in". Both are existing behaviour, left alone.
9. **Light theme only.**

## 16. Out of scope
- Real queries, date filters and designed empty states (Step 6)
- Add, edit and delete expense pages and CSRF tokens (Step 5, with CSRF first)
- Editing the name, email or password; deleting the account; uploading an avatar
- Any change to registration, login or logout
