import functools
import os
import re
import secrets
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from flask import Flask, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from database.db import (
    close_db,
    create_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
    CATEGORIES,
    get_db,
    get_profile_data,
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
MAX_PASSWORD_LENGTH = 128


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


def login_required(view):
    # A redirect, not abort(401): sending someone to sign in is navigation, not an error.
    # No flash (login.html only renders "success" ones), no `next`, and the session is
    # left alone, so a deleted user's stale user_id simply counts as signed out.
    @functools.wraps(view)  # keeps the endpoint name, so url_for("profile") still works
    def wrapped_view(**kwargs):
        if g.user is None:
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


def validate_registration(name, email, password):
    """Return an error message for invalid registration input, else None."""
    if not name or not email or not password:
        return "All fields are required."
    if len(name) > 100:
        return "Name must be 100 characters or fewer."
    # "Cc" covers NUL, newlines, tabs and DEL; "Zl"/"Zp" are the Unicode line and
    # paragraph separators. Format chars ("Cf") such as zero-width joiners are left
    # alone because some scripts need them.
    if any(unicodedata.category(char) in ("Cc", "Zl", "Zp") for char in name):
        return "Name contains invalid characters."
    if len(email) > 254 or not EMAIL_PATTERN.match(email):
        return "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > MAX_PASSWORD_LENGTH:
        return f"Password must be {MAX_PASSWORD_LENGTH} characters or fewer."
    # Checked as-is: passwords are never stripped, so inner/edge spaces are kept.
    if password.isspace():
        return "Password cannot be only spaces."
    return None


# ------------------------------------------------------------------ #
# Template filters                                                    #
# ------------------------------------------------------------------ #

@app.template_filter("inr")
def inr(value):
    """Rupees with Indian digit grouping: 248500 -> "₹2,48,500.00", -1200 -> "−₹1,200.00"."""
    text = f"{abs(value):.2f}"
    rupees, paise = text.split(".")
    if len(rupees) > 3:
        # Last three digits, then pairs: 12345678 -> 1,23,45,678.
        rupees = re.sub(r"(\d)(?=(\d{2})+$)", r"\1,", rupees[:-3]) + "," + rupees[-3:]
    # U+2212 minus sign; an amount that rounds to zero never shows as "−₹0.00".
    sign = "−" if value < 0 and text != "0.00" else ""
    return f"{sign}₹{rupees}.{paise}"


@app.template_filter("short_date")
def short_date(value):
    """ISO "2026-10-26" -> "26 Oct 2026"; anything else is returned unchanged."""
    try:
        parsed = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value
    # parsed.day, not %-d: Windows strftime has no flag to drop the leading zero.
    return f"{parsed.day} {parsed:%b %Y}"


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("profile"))
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

    # No auto-login: the new user signs in themselves. login.html shows this message once.
    flash(
        "Welcome to Spendly! 🎉 Your account has been created successfully. "
        "Please sign in to continue.",
        "success",
    )
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("profile"))
    if request.method == "GET":
        return render_template("login.html")

    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    if not email or not password:
        error = "Email and password are required."
        return render_template("login.html", error=error, email=email), 400

    user = get_user_by_email(email)
    # Accounts with the unusable-password marker ("!") or a legacy NULL can't log in;
    # the explicit check matters because check_password_hash(None, ...) raises.
    if (
        user is None
        or not user["password_hash"]
        or not check_password_hash(user["password_hash"], password)
    ):
        error = "Invalid email or password."
        return render_template("login.html", error=error, email=email), 401

    start_session(user["id"])
    return redirect(url_for("profile"))


@app.route("/logout", methods=["POST"])
def logout():
    # POST-only, and a no-op without a user_id: SameSite=Lax keeps the cookie off another
    # site's POST, and skipping clear() means no delete-cookie header is sent back to it.
    if "user_id" in session:
        session.clear()
        # After clear(), or the clear would wipe the message. login.html shows it once.
        flash("You've been signed out.", "success")
    return redirect(url_for("login"))


@app.route("/terms")
def terms():
    return render_template("terms.html")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/profile")
@login_required
def profile():
    return render_template("profile.html", **get_profile_data(g.user["id"]))


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

def expense_token():
    if "expense_csrf" not in session:
        session["expense_csrf"] = secrets.token_hex(32)
    return session["expense_csrf"]


app.jinja_env.globals["expense_token"] = expense_token


def check_expense_token():
    token = session.get("expense_csrf")
    if not token or not secrets.compare_digest(token, request.form.get("csrf_token", "")):
        abort(400, "Invalid form token. Reload the form and try again.")


def owned_expense(id):
    expense = get_db().execute(
        "SELECT * FROM expenses WHERE id = ? AND user_id = ?", (id, g.user["id"])
    ).fetchone()
    if expense is None:
        abort(404)
    return expense


def expense_form(expense=None):
    values = dict(expense) if expense else {"date": date.today().isoformat()}
    error = None
    if request.method == "POST":
        check_expense_token()
        values = {key: request.form.get(key, "").strip()
                  for key in ("amount", "category", "date", "description")}
        try:
            amount = Decimal(values["amount"])
            if not amount.is_finite() or not Decimal("0") < amount <= Decimal("999999999.99"):
                raise ValueError
            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError
        except (InvalidOperation, ValueError):
            error = "Enter an amount between 0.01 and 999,999,999.99 with at most two decimal places."
        if values["category"] not in CATEGORIES:
            error = "Choose a valid category."
        try:
            parsed = date.fromisoformat(values["date"])
            if parsed > date.today():
                raise ValueError
            values["date"] = parsed.isoformat()
        except ValueError:
            error = "Enter a valid date that is not in the future."
        if len(values["description"]) > 500:
            error = "Description must be 500 characters or fewer."
        if error is None:
            db = get_db()
            args = (float(amount), values["category"], values["date"], values["description"])
            if expense:
                db.execute("UPDATE expenses SET amount=?, category=?, date=?, description=? WHERE id=? AND user_id=?",
                           args + (expense["id"], g.user["id"]))
            else:
                db.execute("INSERT INTO expenses (amount, category, date, description, user_id) VALUES (?, ?, ?, ?, ?)",
                           args + (g.user["id"],))
            db.commit()
            flash("Expense updated." if expense else "Expense added.", "expense")
            return redirect(url_for("profile"))
    return render_template("expense_form.html", values=values, error=error,
                           editing=expense is not None, categories=CATEGORIES,
                           today=date.today().isoformat()), 400 if error else 200


@app.route("/expenses/add", methods=["GET", "POST"])
@login_required
def add_expense():
    return expense_form()


@app.route("/expenses/<int:id>/edit", methods=["GET", "POST"])
@login_required
def edit_expense(id):
    return expense_form(owned_expense(id))


@app.route("/expenses/<int:id>/delete", methods=["GET", "POST"])
@login_required
def delete_expense(id):
    expense = owned_expense(id)
    if request.method == "POST":
        check_expense_token()
        db = get_db()
        db.execute("DELETE FROM expenses WHERE id=? AND user_id=?", (id, g.user["id"]))
        db.commit()
        flash("Expense deleted.", "expense")
        return redirect(url_for("profile"))
    return render_template("expense_delete.html", expense=expense)

@app.cli.command("init-db")
def init_db_command():
    """Create the database tables and apply pending migrations."""
    init_db()
    print("Initialized the database!")

if __name__ == "__main__":
    # Only when run directly: importing app (e.g. from tests) must never touch spendly.db.
    with app.app_context():
        init_db()
        seed_db()
    app.run(debug=True, port=5001)
