import pytest
from werkzeug.security import check_password_hash

from database.db import get_db, seed_db

PASSWORD = "correct-horse"


def register(client, name="Asha Rao", email="asha@example.com", password=PASSWORD):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def login(client, email="asha@example.com", password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def session_user_id(client):
    with client.session_transaction() as sess:
        return sess.get("user_id")


def fetch_users(app):
    with app.app_context():
        rows = get_db().execute("SELECT * FROM users ORDER BY id").fetchall()
        return [dict(row) for row in rows]


# ------------------------------------------------------------------ #
# Registration                                                        #
# ------------------------------------------------------------------ #

def test_register_creates_user_with_hashed_password(app, client):
    response = register(client)

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    [user] = fetch_users(app)
    assert user["name"] == "Asha Rao"
    assert user["email"] == "asha@example.com"
    assert user["password_hash"] != PASSWORD
    assert PASSWORD not in user["password_hash"]
    assert check_password_hash(user["password_hash"], PASSWORD)
    assert session_user_id(client) == user["id"]


def test_register_normalises_email(app, client):
    register(client, email="  Asha@Example.COM ")
    [user] = fetch_users(app)
    assert user["email"] == "asha@example.com"


def test_register_rejects_duplicate_email_case_insensitively(app, client):
    register(client)
    client.get("/logout")

    response = register(client, name="Someone Else", email="ASHA@example.com")

    assert response.status_code == 409
    assert "already exists" in response.get_data(as_text=True)
    assert len(fetch_users(app)) == 1
    assert session_user_id(client) is None


@pytest.mark.parametrize(
    "name, email, password, message",
    [
        ("", "a@example.com", PASSWORD, "All fields are required"),
        ("Asha", "", PASSWORD, "All fields are required"),
        ("Asha", "a@example.com", "", "All fields are required"),
        ("   ", "a@example.com", PASSWORD, "All fields are required"),
        ("x" * 101, "a@example.com", PASSWORD, "100 characters"),
        ("Asha", "not-an-email", PASSWORD, "valid email"),
        ("Asha", "a@b", PASSWORD, "valid email"),
        ("Asha", "a" * 245 + "@example.com", PASSWORD, "valid email"),
        ("Asha", "a@example.com", "short", "at least 8"),
        ("Asha", "a@example.com", "7-chars", "at least 8"),
    ],
)
def test_register_validation(app, client, name, email, password, message):
    response = register(client, name=name, email=email, password=password)

    assert response.status_code == 400
    assert message in response.get_data(as_text=True)
    assert fetch_users(app) == []
    assert session_user_id(client) is None


def test_register_accepts_boundary_values(app, client):
    response = register(client, name="x" * 100, password="8-chars!")
    assert response.status_code == 302
    assert len(fetch_users(app)) == 1


def test_register_error_keeps_name_and_email_but_not_password(client):
    html = register(client, password="short").get_data(as_text=True)
    assert 'value="Asha Rao"' in html
    assert 'value="asha@example.com"' in html
    assert 'value="short"' not in html


# ------------------------------------------------------------------ #
# Login / logout                                                      #
# ------------------------------------------------------------------ #

def test_login_with_valid_credentials(client):
    register(client)
    client.get("/logout")

    response = login(client, email="ASHA@example.com")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    assert session_user_id(client) is not None
    landing = client.get("/").get_data(as_text=True)
    assert "Hi, Asha Rao" in landing
    assert "Sign out" in landing


@pytest.mark.parametrize(
    "email, password",
    [("asha@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)],
)
def test_login_rejects_invalid_credentials(client, email, password):
    register(client)
    client.get("/logout")

    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert "Invalid email or password." in response.get_data(as_text=True)
    assert session_user_id(client) is None


@pytest.mark.parametrize(
    "email, password",
    [("", ""), ("asha@example.com", ""), ("", PASSWORD)],
)
def test_login_requires_both_fields(client, email, password):
    response = login(client, email=email, password=password)
    assert response.status_code == 400
    assert "Email and password are required." in response.get_data(as_text=True)
    assert session_user_id(client) is None


@pytest.mark.parametrize("password", ["anything-at-all", "!"])
def test_login_user_with_unusable_password_is_rejected(app, client, password):
    # Mirrors John Doe, who was migrated with the "!" marker instead of a hash.
    with app.app_context():
        db = get_db()
        db.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("John Doe", "john@example.com", "!"),
        )
        db.commit()

    response = login(client, email="john@example.com", password=password)

    assert response.status_code == 401
    assert session_user_id(client) is None


def test_seeded_demo_user_can_log_in(app, client):
    with app.app_context():
        seed_db()

    response = login(client, email="demo@spendly.com", password="demo123")

    assert response.status_code == 302
    assert session_user_id(client) is not None
    assert "Hi, Demo User" in client.get("/").get_data(as_text=True)


def test_login_replaces_existing_session_data(client):
    register(client)
    client.get("/logout")
    with client.session_transaction() as sess:
        sess["planted"] = "value"

    login(client)

    with client.session_transaction() as sess:
        assert "planted" not in sess
        assert sess.get("user_id") is not None


def test_logout_clears_session(client):
    register(client)
    assert session_user_id(client) is not None
    with client.session_transaction() as sess:
        sess["planted"] = "value"

    response = client.get("/logout")

    assert response.status_code == 302
    assert response.headers["Location"] == "/"
    with client.session_transaction() as sess:
        assert dict(sess) == {}
    landing = client.get("/").get_data(as_text=True)
    assert "Sign in" in landing
    assert "Sign out" not in landing


def test_session_for_deleted_user_is_treated_as_logged_out(app, client):
    register(client)
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM users")
        db.commit()

    landing = client.get("/").get_data(as_text=True)

    assert "Sign in" in landing
    assert client.get("/login").status_code == 200


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_user_is_redirected_away_from_auth_pages(client, path):
    register(client)
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == "/"


def test_session_cookie_is_httponly_and_samesite_lax(client):
    cookie = register(client).headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
