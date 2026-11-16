import calendar
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

from app import inr, short_date
from database.db import (
    CATEGORIES,
    DEMO_EMAIL,
    DEMO_PASSWORD,
    SAMPLE_EXPENSES,
    get_db,
    seed_db,
)
from tests.test_auth import login, register, session_user_id, sign_up_and_log_in


def profile_page(client):
    sign_up_and_log_in(client)
    return client.get("/profile").get_data(as_text=True)


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
