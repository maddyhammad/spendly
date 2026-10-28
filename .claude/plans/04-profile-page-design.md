# Plan: Step 4 — Profile page design

Spec: `.claude/specs/04-profile-page-design.md`. This file records the decisions behind the spec and the
order in which to build it. **Status: implemented 2026-10-28** (141 tests pass; subagent-verified).

## History
- The first draft was a profile page.
- The user's brief then asked for a full dashboard (sidebar, income, budgets, charts).
- When asked which spec to implement, the user chose the **profile page with sample data**.
- The user kept the database untouched. Login was first left unchanged; after implementation the
  user asked for signed-in users to be redirected to the profile page (D3, revised).
- The design rules from the brief still apply:
  - green, black and white theme
  - responsive, rounded cards, subtle hover
  - beginner-friendly
  - vanilla JS only where needed
  - sample data clearly separated
  - no links to routes that don't exist
- The project `frontend-design` skill is empty, so the design reuses the `style.css` tokens.

## Research summary (Explore subagents and a Plan subagent, 2026-10-28)
- **The stub:** `/profile` is at `app.py:163-165` and returns plain text. `test_routes.py:25` expects "Step 4" in it.
- **Auth:**
  - No `login_required` decorator exists.
  - `login()` redirects to `url_for("landing")` (`app.py:135-136`).
  - `g.user` is set in `load_logged_in_user()` and holds `id`, `name`, `email`, `password_hash` (no `created_at`).
- **`base.html`:**
  - The logged-in nav is `<span class="nav-user">Hi, …</span>`, followed by the POST Sign out form.
  - `test_nav_sign_out_is_a_post_form` asserts that form's exact markup.
  - The available blocks are `title`, `head`, `content` and `scripts`.
- **CSS:**
  - The ≤600px blocks hide `.nav-links a:not(.nav-cta)`: in `style.css:574-578`, which also hides `.nav-user`, and in `landing.css:527-530`.
  - `landing.css` loads after `style.css` on `/`.
  - No `.visually-hidden` utility exists, and `.feature-card` has no hover rule.
- **Tests:**
  - The fixtures never seed.
  - `tests/__init__.py` exists, so the `test_auth` helpers can be imported.
  - There is no HTML parser; the tests use substrings and regexes.
  - There is no pytest config file.

## Decisions

| # | Decision | Why |
|---|---|---|
| D1 | `/profile` replaces the stub, and there is no `/dashboard`. | The user's choice. The route already exists and CLAUDE.md marks it as Step 4. |
| D2 | `login_required` redirects to `/login`: no flash, no `next`, no session change, and no `abort(401)`. | `login.html` shows only `success` flashes. `next` would change `login()`. Sending someone to sign in is a navigation, not an error (`register()` and `login()` redirect too). |
| D3 | **Revised 2026-10-28:** signed-in users are redirected to `/profile`: after a successful login, and when they open `/login` or `/register`. `/` stays reachable. The nav's "Hi, {name}" is also the profile link (`a.nav-profile`) with an initial avatar; phones show only the avatar, with the name visually hidden. | The user asked for signed-in users to land on the profile automatically (this was first deferred to Step 6, when login was to stay unchanged). Only the three redirect targets change; every check and message stays the same. The name is the link's only accessible name (the avatar is `aria-hidden`), so it must never be `display: none`. |
| D4 | Sample data lives in its own `sample_data.py` → `get_profile_sample()`, which returns a fresh dict whose keys match future DB rows (`category`, `amount`, `date`, `description`). | It is clearly separate from app logic, as the brief asks. Step 6 deletes one file, changes one line, and can pass `sqlite3.Row` objects to the unchanged template. |
| D5 | Only the name and email are real. There is no "member since". | It would need `created_at`, which means changing `db.py`, and the brief says the database stays unchanged. |
| D6 | The `inr` filter (Indian grouping, `₹2,48,500.00`, never `−₹0.00`) and the `short_date` filter (`26 Oct 2026`, no `%-d`) live in `app.py`. | Spendly is rupee-first. They are presentation helpers, so they outlive the sample data. `%-d` crashes on Windows. |
| D7 | Category bars use a single accent colour and show the share of the total. Each row is stacked: name, amount and % on one line, then a full-width bar. Bars are `aria-hidden` and sized by `--share`. | One series needs no colour coding; the text labels carry the values. A four-column row would leave about 60px for the bar between 901 and 1100px. A `style` attribute carrying only data is the least-bad way to pass a width (CLAUDE.md gets an explicit exception). |
| D8 | On phones the table uses a meta line: the Date and Category columns are hidden, and the pill and date appear under the description. | It avoids sideways scrolling, and each fact appears once at every width. |
| D9 | The empty-data **guards** come now (empty lists, `None` top category, missing description). The **designed** empty states come in Step 6. | `None|inr` would cause a 500. The guards cost about four lines and let Step 6 change only the data layer. The designed empty state needs Step 5's add-expense call to action. |
| D10 | A global `.visually-hidden` utility goes in `style.css`. | None exists yet. The table caption needs it, and later pages will too. The nav rule repeats its declarations, because a media query can't apply a class. |
| D11 | Hover means shadow or tint only, inside `@media (hover: hover)`, and is off under reduced motion. Nothing lifts. | Nothing on the page is clickable, and touch screens would otherwise keep a hover state stuck after a tap. |
| D12 | The roadmap renumbering is a docs change only. The stub strings ("Step 7/8/9") stay. CSRF tokens move to "before Step 5". | CLAUDE.md forbids touching stubs this step doesn't target, and `test_stub_routes_unchanged` asserts those strings. |
| D13 | The sample mirrors the seeded demo expenses, and a test enforces it. | The numbers stay realistic and consistent (the landing mock's ₹11,550 vs ₹12,450 mismatch can't happen here). Step 6 can then check its real queries against the same totals for the demo user. |
| D14 | **Visual refresh (added after implementation):** a deep-green hero, inline-SVG icons from a Jinja macro, a featured "Total spent" tile, derived stat lines (categories count, average, top share), entrance and bar-grow animation. Spec §7 has the details. | The user asked for a more attractive page. It stays on brand (existing tokens; the only new colours are translucent whites and greens), needs no library and no JS, and keeps the markup the tests rely on. The icons are decorative (`aria-hidden`), the text carries the meaning, and all motion respects reduced-motion settings. The derived lines are guarded, so empty data can't divide by zero or print "None". |

## Build order
Run `pytest` at every checkpoint, and keep it green before moving on.

0. **Docs.** Write this plan and the spec. The dashboard drafts were renamed and then overwritten.
1. **Baseline.** Record the `pytest` count (Step 3 recorded 96) and the sha256 of `spendly.db`.
2. **`sample_data.py`**, with `test_sample_data_is_consistent`, `…_mirrors_seed` and `…_returns_fresh_copy`.
3. **Filters** in `app.py`, with `test_inr`, `test_short_date` and `test_filters_are_registered`.
4. **Auth and route.**
   - Add `login_required` and `profile()` with a minimal `profile.html`.
   - Remove the `/profile` row from `test_routes.py`.
   - Add the access tests.
5. **Nav.**
   - Change `base.html`, the `style.css` nav rules plus the utility, and the `landing.css` selector.
   - Add the nav tests.
   - The whole `test_auth.py` suite must stay green.
6. **Full `profile.html`**, with the rendering tests.
7. **`profile.css`**, then a first look in the browser.
8. **`CLAUDE.md`** updates (spec §8).
9. **Verification subagent:**
   - run the full suite and check the count
   - confirm `spendly.db`'s sha256 is unchanged
   - confirm the diff doesn't touch `register()`, `login()`, `logout()`, `start_session()`, `validate_registration()` or `db.py`

   Then the user's manual browser check (spec §14).

## Risks

| Risk | Guard |
|---|---|
| Decorators in the wrong order make the page public | `test_profile_requires_login` |
| A missing `functools.wraps` breaks `url_for('profile')` | the rendering and nav tests |
| `landing.css` hides the profile link on `/` | the selector change; manual check at 360px on `/` |
| The nav name gets `display: none`, leaving the link without an accessible name | visually hidden instead; manual screen-reader check |
| Switching to `import sample_data` silently defeats the monkeypatch | `test_profile_figures_come_from_sample_module` fails |
| The `base.html` change breaks other pages | the full `test_auth.py` and `test_routes.py` suites; the Sign out markup stays byte-identical |
