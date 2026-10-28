import re

import pytest
from markupsafe import escape
from werkzeug.security import check_password_hash

from database.db import get_db, seed_db

PASSWORD = "correct-horse"
WELCOME_MESSAGE = (
    "Welcome to Spendly! 🎉 Your account has been created successfully. "
    "Please sign in to continue."
)
# Jinja escapes the apostrophe, so this is how the sign-out message appears in the HTML.
SIGNED_OUT_HTML = str(escape("You've been signed out."))


def register(client, name="Asha Rao", email="asha@example.com", password=PASSWORD):
    return client.post(
        "/register", data={"name": name, "email": email, "password": password}
    )


def login(client, email="asha@example.com", password=PASSWORD):
    return client.post("/login", data={"email": email, "password": password})


def logout(client):
    return client.post("/logout")


def sign_up_and_log_in(client):
    # Registration doesn't log in, so tests that need a session sign in explicitly.
    register(client)
    return login(client)


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
    assert response.headers["Location"] == "/login"
    [user] = fetch_users(app)
    assert user["name"] == "Asha Rao"
    assert user["email"] == "asha@example.com"
    assert user["password_hash"] != PASSWORD
    assert PASSWORD not in user["password_hash"]
    assert check_password_hash(user["password_hash"], PASSWORD)
    assert session_user_id(client) is None  # not logged in automatically


def test_register_normalises_email(app, client):
    register(client, email="  Asha@Example.COM ")
    [user] = fetch_users(app)
    assert user["email"] == "asha@example.com"


def test_register_rejects_duplicate_email_case_insensitively(app, client):
    register(client)

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
        ("Asha", "a" * 243 + "@example.com", PASSWORD, "valid email"),  # 255 chars
        ("Asha\x00Rao", "a@example.com", PASSWORD, "invalid characters"),
        ("\x00Asha", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\nRao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\rRao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\tRao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\x7fRao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\u2028Rao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha\u2029Rao", "a@example.com", PASSWORD, "invalid characters"),
        ("Asha", "a@example.com", "short", "at least 8"),
        ("Asha", "a@example.com", "7-chars", "at least 8"),
        ("Asha", "a@example.com", " " * 3, "at least 8"),
        ("Asha", "a@example.com", "x" * 129, "128 characters or fewer"),
        ("Asha", "a@example.com", " " * 8, "only spaces"),
        ("Asha", "a@example.com", " \t" * 4, "only spaces"),
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


@pytest.mark.parametrize(
    "email, password",
    [
        ("a" * 242 + "@example.com", PASSWORD),  # 254-char email
        ("asha@example.com", "x" * 128),
    ],
    ids=["email-254", "password-128"],
)
def test_register_accepts_max_lengths(app, client, email, password):
    response = register(client, email=email, password=password)
    assert response.status_code == 302
    assert len(fetch_users(app)) == 1


def test_register_stores_password_exactly_as_entered(app, client):
    password = "  pass word  "
    assert register(client, password=password).status_code == 302

    [user] = fetch_users(app)
    assert check_password_hash(user["password_hash"], password)
    assert not check_password_hash(user["password_hash"], password.strip())


def test_register_accepts_non_ascii_name(app, client):
    assert register(client, name="José Ñúñez").status_code == 302
    [user] = fetch_users(app)
    assert user["name"] == "José Ñúñez"


def test_register_hashes_password_with_scrypt(app, client):
    register(client)
    [user] = fetch_users(app)
    assert user["password_hash"].startswith("scrypt:")


def test_register_rejects_padded_mixed_case_duplicate(app, client):
    register(client, email="  Asha@Example.COM ")

    response = register(client, name="Someone Else", email="  ASHA@example.com ")

    assert response.status_code == 409
    assert len(fetch_users(app)) == 1


def test_register_post_when_logged_in_redirects_without_creating_user(app, client):
    sign_up_and_log_in(client)
    user_id = session_user_id(client)
    assert user_id is not None

    response = register(client, name="Someone Else", email="other@example.com")

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    assert len(fetch_users(app)) == 1
    assert session_user_id(client) == user_id


def test_register_shows_welcome_message_on_login_page_exactly_once(client):
    response = register(client)
    assert response.headers["Location"] == "/login"

    page = client.get("/login").get_data(as_text=True)
    assert page.count(WELCOME_MESSAGE) == 1
    assert 'class="auth-success" role="status"' in page
    assert page.index(WELCOME_MESSAGE) < page.index('action="/login"')  # above the form
    assert "Sign out" not in page

    refreshed = client.get("/login").get_data(as_text=True)
    assert WELCOME_MESSAGE not in refreshed
    assert 'class="auth-success"' not in refreshed


def test_failed_registration_shows_no_welcome_message(client):
    assert register(client, password="short").status_code == 400
    assert WELCOME_MESSAGE not in client.get("/login").get_data(as_text=True)

    register(client)
    client.get("/login")  # shows (and consumes) the first account's welcome
    assert register(client, name="Someone Else").status_code == 409
    assert WELCOME_MESSAGE not in client.get("/login").get_data(as_text=True)


def test_register_form_has_autocomplete_and_error_alert(client):
    form = client.get("/register").get_data(as_text=True)
    for value in ("name", "email", "new-password"):
        assert f'autocomplete="{value}"' in form
    assert 'maxlength="128"' in form

    error_page = register(client, password="short").get_data(as_text=True)
    assert 'role="alert"' in error_page


# ------------------------------------------------------------------ #
# Login / logout                                                      #
# ------------------------------------------------------------------ #

def test_login_with_valid_credentials(client):
    register(client)

    response = login(client, email="ASHA@example.com")

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    assert session_user_id(client) is not None
    profile = client.get("/profile").get_data(as_text=True)
    assert "Hi, Asha Rao" in profile
    assert "Sign out" in profile


def test_login_accepts_padded_mixed_case_email(client):
    register(client)

    response = login(client, email="  Asha@Example.COM ")

    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"
    assert session_user_id(client) is not None


def test_login_password_must_match_exactly(client):
    password = "  pass word  "
    register(client, password=password)

    for typed in ("pass word", "  pass word", "pass word  "):
        assert login(client, password=typed).status_code == 401
        assert session_user_id(client) is None

    assert login(client, password=password).status_code == 302
    assert session_user_id(client) is not None


@pytest.mark.parametrize(
    "email, password",
    [("asha@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)],
)
def test_login_rejects_invalid_credentials(client, email, password):
    register(client)

    response = login(client, email=email, password=password)

    assert response.status_code == 401
    assert "Invalid email or password." in response.get_data(as_text=True)
    assert session_user_id(client) is None


@pytest.mark.parametrize(
    "password, status",
    [("wrong-password", 401), ("", 400)],
    ids=["wrong-password", "empty-password"],
)
def test_login_error_keeps_email_but_not_password(client, password, status):
    register(client)

    response = login(client, email="  Asha@Example.com ", password=password)

    assert response.status_code == status
    html = response.get_data(as_text=True)
    assert 'value="asha@example.com"' in html  # re-filled, normalised
    [password_input] = re.findall(r'<input type="password"[^>]*>', html)
    assert "value=" not in password_input  # the password field is never re-filled
    assert "wrong-password" not in html


@pytest.mark.parametrize(
    "email, password",
    [("", ""), ("asha@example.com", ""), ("", PASSWORD), ("   ", PASSWORD)],
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
    with client.session_transaction() as sess:
        sess["planted"] = "value"

    login(client)

    with client.session_transaction() as sess:
        assert "planted" not in sess
        assert sess.get("user_id") is not None


def test_login_session_contains_only_user_id(app, client):
    register(client)  # leaves the welcome flash pending in the session

    login(client)

    [user] = fetch_users(app)
    with client.session_transaction() as sess:
        assert dict(sess) == {"user_id": user["id"]}


def test_login_post_when_logged_in_redirects_without_checking(client):
    sign_up_and_log_in(client)
    user_id = session_user_id(client)

    response = login(client, password="wrong-password")

    assert response.status_code == 302  # not 401: the password was never checked
    assert response.headers["Location"] == "/profile"
    assert session_user_id(client) == user_id


def test_login_form_has_autocomplete_and_error_alert(client):
    form = client.get("/login").get_data(as_text=True)
    assert 'autocomplete="email"' in form
    assert 'autocomplete="current-password"' in form
    assert 'maxlength="254"' in form
    assert 'maxlength="128"' not in form  # no password cap at login (spec §12)

    error_page = login(client, password="wrong-password").get_data(as_text=True)
    assert 'role="alert"' in error_page


def test_logout_clears_session(client):
    sign_up_and_log_in(client)
    assert session_user_id(client) is not None
    with client.session_transaction() as sess:
        sess["planted"] = "value"

    response = logout(client)

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    with client.session_transaction() as sess:
        assert list(sess) == ["_flashes"]  # only the sign-out message, until it's shown
    landing = client.get("/").get_data(as_text=True)
    assert "Sign in" in landing
    assert "Sign out" not in landing


def test_logout_shows_signed_out_message_once(client):
    sign_up_and_log_in(client)

    response = logout(client)
    assert response.headers["Location"] == "/login"

    page = client.get("/login").get_data(as_text=True)
    assert page.count(SIGNED_OUT_HTML) == 1
    assert page.count('class="auth-success" role="status"') == 1
    assert "Sign out" not in page

    refreshed = client.get("/login").get_data(as_text=True)
    assert SIGNED_OUT_HTML not in refreshed
    assert 'class="auth-success"' not in refreshed


def test_logout_rejects_get(client):
    sign_up_and_log_in(client)
    user_id = session_user_id(client)

    response = client.get("/logout")

    assert response.status_code == 405
    assert session_user_id(client) == user_id


def test_logout_when_logged_out_is_harmless(client):
    register(client)  # logged out, with the welcome flash waiting in the session

    response = logout(client)

    assert response.status_code == 302
    assert response.headers["Location"] == "/login"
    page = client.get("/login").get_data(as_text=True)
    assert WELCOME_MESSAGE in page  # the session was left alone
    assert SIGNED_OUT_HTML not in page


def test_logout_without_session_cookie_sets_no_cookie(client):
    # Models another site's form POSTing here: SameSite=Lax keeps the session cookie off
    # cross-site POSTs, so the request has no session. A Set-Cookie in the response would
    # still delete the user's real cookie, so there must be none.
    response = logout(client)

    assert response.status_code == 302
    assert "Set-Cookie" not in response.headers


def test_nav_sign_out_is_a_post_form(client):
    sign_up_and_log_in(client)

    page = client.get("/").get_data(as_text=True)

    assert '<form method="POST" action="/logout" class="nav-logout">' in page
    assert '<button type="submit" class="nav-cta">Sign out</button>' in page
    assert 'href="/logout"' not in page


def test_session_for_deleted_user_is_treated_as_logged_out(app, client):
    sign_up_and_log_in(client)
    assert session_user_id(client) is not None
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM users")
        db.commit()

    landing = client.get("/").get_data(as_text=True)

    assert "Sign in" in landing
    assert client.get("/login").status_code == 200
    logout(client)  # a stale id still counts as a session to end
    assert session_user_id(client) is None


@pytest.mark.parametrize("path", ["/login", "/register"])
def test_logged_in_user_is_redirected_away_from_auth_pages(client, path):
    sign_up_and_log_in(client)
    response = client.get(path)
    assert response.status_code == 302
    assert response.headers["Location"] == "/profile"


def test_session_cookie_is_httponly_and_samesite_lax(client):
    response = sign_up_and_log_in(client)
    assert response.status_code == 302
    assert session_user_id(client) is not None
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
