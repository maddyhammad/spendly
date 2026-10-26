import os
import re
import secrets

from flask import Flask, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    close_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
)

app = Flask(__name__)
# Absolute path so the same file is used no matter which directory the app
# (or `flask init-db`) is started from.
app.config["DATABASE"] = os.path.join(app.root_path, "spendly.db")
# Set SECRET_KEY in the environment to keep sessions valid across restarts;
# the random fallback is safe but logs everyone out whenever the server reloads.
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

app.teardown_appcontext(close_db)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LENGTH = 8


# ------------------------------------------------------------------ #
# Auth helpers                                                        #
# ------------------------------------------------------------------ #

@app.before_request
def load_logged_in_user():
    user_id = session.get("user_id")
    g.user = get_user_by_id(user_id) if user_id is not None else None


def start_session(user_id):
    # Clear first so a pre-login session id can't be reused (session fixation).
    session.clear()
    session["user_id"] = user_id


def validate_registration(name, email, password):
    """Return an error message for invalid registration input, else None."""
    if not name or not email or not password:
        return "All fields are required."
    if len(name) > 100:
        return "Name must be 100 characters or fewer."
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("landing"))
    if request.method == "GET":
        return render_template("register.html")

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")

    error = validate_registration(name, email, password)
    if error:
        return render_template("register.html", error=error, name=name, email=email), 400

    user_id = create_user(name, email, generate_password_hash(password))
    if user_id is None:
        error = "An account with that email already exists."
        return render_template("register.html", error=error, name=name, email=email), 409

    start_session(user_id)
    return redirect(url_for("landing"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("landing"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email or not password:
        error = "Email and password are required."
        return render_template("login.html", error=error, email=email), 400

    user = get_user_by_email(email)
    # Users created before auth existed have no password_hash and can't log in.
    if (
        user is None
        or not user["password_hash"]
        or not check_password_hash(user["password_hash"], password)
    ):
        error = "Invalid email or password."
        return render_template("login.html", error=error, email=email), 401

    start_session(user["id"])
    return redirect(url_for("landing"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("landing"))


@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/profile")
def profile():
    return "Profile page — coming in Step 4"


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"

@app.cli.command("init-db")
def init_db_command():
    """Create the database tables and apply pending migrations."""
    init_db()
    print("Initialized the database!")

if __name__ == "__main__":
    app.run(debug=True, port=5001)
