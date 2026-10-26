import re
from datetime import date

from werkzeug.security import check_password_hash

from database.db import get_db, seed_db

SPEC_CATEGORIES = {"Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"}


def seed_and_fetch(app, times=1):
    with app.app_context():
        for _ in range(times):
            seed_db()
        db = get_db()
        users = [dict(r) for r in db.execute("SELECT * FROM users ORDER BY id")]
        expenses = [dict(r) for r in db.execute("SELECT * FROM expenses ORDER BY id")]
    return users, expenses


def test_seed_creates_demo_user_with_hashed_password(app):
    [user], _ = seed_and_fetch(app)

    assert (user["name"], user["email"]) == ("Demo User", "demo@spendly.com")
    assert user["password_hash"] != "demo123"
    assert user["password_hash"].startswith("scrypt:")
    assert check_password_hash(user["password_hash"], "demo123")


def test_seed_creates_eight_expenses_covering_every_category(app):
    [user], expenses = seed_and_fetch(app)

    assert len(expenses) == 8
    assert {e["user_id"] for e in expenses} == {user["id"]}
    assert {e["category"] for e in expenses} == SPEC_CATEGORIES
    assert all(isinstance(e["amount"], float) and e["amount"] > 0 for e in expenses)
    assert all(e["description"] for e in expenses)


def test_seed_dates_are_this_month_and_not_in_the_future(app):
    _, expenses = seed_and_fetch(app)
    today = date.today()

    for e in expenses:
        assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", e["date"])
        d = date.fromisoformat(e["date"])
        assert (d.year, d.month) == (today.year, today.month)
        assert d <= today


def test_seed_is_idempotent(app):
    users, expenses = seed_and_fetch(app, times=3)
    assert len(users) == 1
    assert len(expenses) == 8


def test_seed_runs_when_other_users_already_exist(app):
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("John Doe", "john@example.com", "!"),
        )
        db.commit()

    users, expenses = seed_and_fetch(app)

    assert [u["email"] for u in users] == ["john@example.com", "demo@spendly.com"]
    assert len(expenses) == 8
