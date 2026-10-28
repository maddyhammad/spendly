import calendar
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

import app as app_module
from app import inr, short_date
from database.db import (
    CATEGORIES,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    SAMPLE_EXPENSES,
    get_db,
    seed_db,
)
from sample_data import get_profile_sample
from tests.test_auth import login, register, session_user_id, sign_up_and_log_in


def profile_page(client):
    sign_up_and_log_in(client)
    return client.get("/profile").get_data(as_text=True)


def use_sample(monkeypatch, sample):
    # profile() looks get_profile_sample up by its global name, so patch it on the app module.
    monkeypatch.setattr(app_module, "get_profile_sample", lambda: sample)


# ------------------------------------------------------------------ #
# Access                                                              #
# ------------------------------------------------------------------ #

def test_profile_requires_login(client):
    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert "Set-Cookie" not in response.headers
    assert session_user_id(client) is None


def test_profile_for_deleted_user_redirects_to_login(app, client):
    sign_up_and_log_in(client)
    stale_id = session_user_id(client)
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM users")
        db.commit()

    response = client.get("/profile")

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    assert session_user_id(client) == stale_id  # login_required never touches the session


@pytest.mark.parametrize("logged_in", [False, True])
def test_profile_rejects_post(client, logged_in):
    if logged_in:
        sign_up_and_log_in(client)

    assert client.post("/profile").status_code == 405


def test_signing_in_lands_on_profile(client):
    register(client)

    response = client.post(
        "/login",
        data={"email": "asha@example.com", "password": "correct-horse"},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert response.request.path == "/profile"
    assert '<h1 class="profile-name" id="profile-name">Asha Rao</h1>' in response.get_data(as_text=True)


def test_seeded_demo_user_lands_on_profile(app, client):
    with app.app_context():
        seed_db()

    response = client.post(
        "/login", data={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}, follow_redirects=True
    )

    assert response.request.path == "/profile"
    assert '<h1 class="profile-name" id="profile-name">Demo User</h1>' in response.get_data(as_text=True)


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_signed_in_user_is_sent_from_auth_pages_to_profile(client, path):
    sign_up_and_log_in(client)

    response = client.get(path, follow_redirects=True)

    assert response.request.path == "/profile"
    assert response.status_code == 200


# ------------------------------------------------------------------ #
# Rendering                                                           #
# ------------------------------------------------------------------ #

def test_profile_renders_for_logged_in_user(client):
    sign_up_and_log_in(client)

    response = client.get("/profile")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "<title>Profile — Spendly</title>" in page
    assert '<h1 class="profile-name" id="profile-name">Asha Rao</h1>' in page
    assert '<p class="profile-email">asha@example.com</p>' in page
    assert '<span class="profile-avatar" aria-hidden="true">A</span>' in page
    assert 'href="/static/css/profile.css"' in page
    assert "profile.css" not in client.get("/").get_data(as_text=True)


def test_profile_renders_all_sections(client):
    page = profile_page(client)

    for heading in ("Spending summary", "By category", "Recent expenses"):
        assert f">{heading}</h2>" in page
    for label in ("Total spent", "Expenses", "Top category"):
        assert re.search(rf'<dt class="stat-label">.*?</span>{label}</dt>', page, re.S)
    assert '<span class="sample-badge">Sample data</span>' in page
    assert f'<p class="card-subtitle">{get_profile_sample()["period_label"]}</p>' in page


def test_profile_shows_sample_figures(client):
    page = profile_page(client)
    sample = get_profile_sample()

    assert '<dd class="stat-value">₹7,267.00</dd>' in page
    assert re.search(r'Expenses</dt>\s*<dd class="stat-value">8</dd>', page)
    assert '<dd class="stat-value">Bills</dd>' in page
    assert '<dd class="stat-note">₹2,499.00</dd>' in page
    assert '<dd class="stat-meta">Across 7 categories</dd>' in page
    assert '<dd class="stat-meta">Avg ₹908.38 each</dd>' in page  # 7267 / 8
    assert '<dd class="stat-meta">34% of total spending</dd>' in page
    for row in sample["category_totals"]:
        assert f'<span class="category-name">{row["category"]}</span>' in page
        assert f'<span class="category-amount">{inr(row["amount"])}</span>' in page
        assert f'<span class="category-share">{row["share"]}%</span>' in page
        assert f'style="--share: {row["share"]}%"' in page

    [tbody] = re.findall(r"<tbody>(.*?)</tbody>", page, re.S)
    assert tbody.count("<tr>") == 5
    positions = [tbody.index(e["description"]) for e in sample["recent_expenses"]]
    assert positions == sorted(positions)  # newest first, as given
    for e in sample["recent_expenses"]:
        assert short_date(e["date"]) in tbody
        assert f'<td class="num">{inr(e["amount"])}</td>' in tbody


def test_profile_figures_come_from_sample_module(client, monkeypatch):
    use_sample(monkeypatch, {
        "period_label": "March 2027",
        "summary": {"total": 123.45, "count": 1, "top_category": "Food", "top_amount": 123.45},
        "category_totals": [{"category": "Food", "amount": 123.45, "share": 100}],
        "recent_expenses": [
            {"date": "2027-03-02", "description": "Chai", "category": "Food", "amount": 123.45},
        ],
    })

    page = profile_page(client)

    for shown in ("₹123.45", "Chai", "March 2027", "2 Mar 2027"):
        assert shown in page
    for hidden in ("₹7,267.00", "Dinner with friends", "October 2026"):
        assert hidden not in page


def test_profile_template_has_no_hardcoded_figures(app):
    source = Path(app.root_path, "templates", "profile.html").read_text(encoding="utf-8")

    assert "₹" not in source
    assert not re.search(r"\b20\d\d\b", source)
    assert not any(month in source for month in calendar.month_name[1:])


def test_profile_renders_empty_sample(client, monkeypatch):
    use_sample(monkeypatch, {
        "period_label": "October 2026",
        "summary": {"total": 0, "count": 0, "top_category": None, "top_amount": None},
        "category_totals": [],
        "recent_expenses": [],
    })
    sign_up_and_log_in(client)

    response = client.get("/profile")
    page = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "No spending to show yet." in page
    assert "No expenses yet." in page
    assert "<table" not in page
    assert '<dd class="stat-value">₹0.00</dd>' in page
    assert '<dd class="stat-value">—</dd>' in page
    assert "Avg " not in page  # no average without expenses (and no division by zero)
    assert "of total spending" not in page
    assert "Across " not in page
    assert "None" not in page


def test_profile_escapes_user_data(client):
    register(client, name="<b>Asha</b>", email="a<i>@example.com")
    assert login(client, email="a<i>@example.com").headers["Location"] == "/profile"

    page = client.get("/profile").get_data(as_text=True)

    assert '<h1 class="profile-name" id="profile-name">&lt;b&gt;Asha&lt;/b&gt;</h1>' in page
    assert '<span class="nav-user-text">Hi, &lt;b&gt;Asha&lt;/b&gt;</span>' in page
    assert '<p class="profile-email">a&lt;i&gt;@example.com</p>' in page
    assert '<span class="profile-avatar" aria-hidden="true">&lt;</span>' in page
    assert "<b>" not in page
    assert "<i>" not in page


def test_profile_table_and_bars_are_accessible(client):
    page = profile_page(client)
    categories = get_profile_sample()["category_totals"]

    assert '<caption class="visually-hidden">Your 5 most recent expenses (sample data)</caption>' in page
    assert page.count('scope="col"') == 4
    assert '<ol class="category-list" role="list">' in page
    assert page.count('<span class="category-track" aria-hidden="true">') == len(categories)
    # 3 stat icons + one per category row + one per expense row; all decorative.
    svgs = re.findall(r"<svg[^>]*>", page)
    assert len(svgs) == 3 + len(categories) + 5
    assert all('aria-hidden="true"' in s and 'focusable="false"' in s for s in svgs)


def test_profile_has_no_dead_links(client):
    page = profile_page(client)
    urls = re.findall(r'(?:href|src)="([^"]*)"', page)
    internal = [u for u in urls if u.startswith("/")]
    external = [u for u in urls if not u.startswith("/")]

    assert all(
        u.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com")) for u in external
    )
    assert not any(u.startswith("/expenses") for u in internal)
    for url in internal:
        response = client.get(url)
        assert response.status_code == 200, url
        response.close()
    assert re.findall(r'action="([^"]*)"', page) == ["/logout"]


# ------------------------------------------------------------------ #
# Nav                                                                 #
# ------------------------------------------------------------------ #

def test_nav_links_to_profile_when_logged_in(client):
    sign_up_and_log_in(client)

    page = client.get("/").get_data(as_text=True)

    assert '<a href="/profile" class="nav-profile">' in page
    assert '<span class="nav-avatar" aria-hidden="true">A</span>' in page
    assert '<span class="nav-user-text">Hi, Asha Rao</span>' in page
    assert "aria-current" not in page


def test_nav_marks_profile_as_current_page(client):
    sign_up_and_log_in(client)

    page = client.get("/profile").get_data(as_text=True)

    assert page.count('<a href="/profile" class="nav-profile" aria-current="page">') == 1


@pytest.mark.parametrize("path", ["/", "/login", "/register", "/terms", "/privacy"])
def test_nav_has_no_profile_link_when_logged_out(client, path):
    assert 'href="/profile"' not in client.get(path).get_data(as_text=True)


# ------------------------------------------------------------------ #
# Sample data                                                         #
# ------------------------------------------------------------------ #

def test_sample_data_is_consistent():
    sample = get_profile_sample()
    summary = sample["summary"]
    categories = sample["category_totals"]
    recent = sample["recent_expenses"]

    assert set(sample) == {"period_label", "summary", "category_totals", "recent_expenses"}

    names = [c["category"] for c in categories]
    amounts = [c["amount"] for c in categories]
    assert sum(amounts) == pytest.approx(summary["total"])
    assert amounts == sorted(amounts, reverse=True)
    assert len(set(names)) == len(names)
    assert set(names) <= set(CATEGORIES)
    assert (summary["top_category"], summary["top_amount"]) == (names[0], amounts[0])
    for c in categories:
        assert c["share"] == round(c["amount"] / summary["total"] * 100)
    assert sum(c["share"] for c in categories) == 100

    dates = [date.fromisoformat(e["date"]) for e in recent]
    assert len(recent) == 5 <= summary["count"]
    assert dates == sorted(dates, reverse=True)
    assert all(f"{d:%B %Y}" == sample["period_label"] for d in dates)
    assert all(e["category"] in names and e["amount"] > 0 for e in recent)


def test_sample_data_mirrors_seed():
    sample = get_profile_sample()
    seeded_totals = defaultdict(float)
    for category, amount, _ in SAMPLE_EXPENSES:
        seeded_totals[category] += amount

    assert sample["summary"]["total"] == pytest.approx(sum(seeded_totals.values()))
    assert sample["summary"]["count"] == len(SAMPLE_EXPENSES)
    assert {c["category"]: c["amount"] for c in sample["category_totals"]} == seeded_totals
    for e in sample["recent_expenses"]:
        assert (e["category"], e["amount"], e["description"]) in SAMPLE_EXPENSES


def test_sample_data_returns_fresh_copy():
    first = get_profile_sample()
    first["summary"]["total"] = 0
    first["recent_expenses"].clear()

    second = get_profile_sample()

    assert second["summary"]["total"] == 7267.00
    assert len(second["recent_expenses"]) == 5


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@pytest.mark.parametrize(
    "value, expected",
    [
        (0, "₹0.00"),
        (999, "₹999.00"),
        (1000, "₹1,000.00"),
        (7267, "₹7,267.00"),
        (99999.99, "₹99,999.99"),
        (100000, "₹1,00,000.00"),
        (248500, "₹2,48,500.00"),
        (1234567.5, "₹12,34,567.50"),
        (10000000, "₹1,00,00,000.00"),
        (-1200, "\u2212₹1,200.00"),
        (-0.001, "₹0.00"),
        (2499.999, "₹2,500.00"),
    ],
)
def test_inr(value, expected):
    assert inr(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-10-26", "26 Oct 2026"),
        ("2026-01-05", "5 Jan 2026"),
        ("", ""),
        ("not-a-date", "not-a-date"),
        ("2026-02-30", "2026-02-30"),
        (None, None),
    ],
)
def test_short_date(value, expected):
    assert short_date(value) == expected


def test_filters_are_registered(app):
    assert app.jinja_env.filters["inr"] is inr
    assert app.jinja_env.filters["short_date"] is short_date
