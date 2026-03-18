"""
auth.py — Flask-Login user authentication blueprint.

Provides /signup, /login, /logout routes and the Flask-Login User model.
Register this blueprint and the login_manager in dm_web.py.
"""

import re
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

import db_manager

auth_bp = Blueprint("auth", __name__)
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access that page."
login_manager.login_message_category = "info"


# ── User model ────────────────────────────────────────────────────────────────

class User(UserMixin):
    def __init__(self, row: dict):
        self.id                  = row["id"]
        self.email               = row["email"]
        self.subscription_status = row.get("subscription_status", "free")
        self.stripe_customer_id  = row.get("stripe_customer_id")
        self.stripe_sub_id       = row.get("stripe_sub_id")

    def is_pro(self) -> bool:
        return self.subscription_status in ("active", "trialing")


@login_manager.user_loader
def load_user(user_id: str) -> User | None:
    row = db_manager.get_user_by_id(int(user_id))
    return User(row) if row else None


def is_pro(user) -> bool:
    """Convenience function — works with a User object or None."""
    return bool(user and user.is_authenticated and user.is_pro())


# ── Helpers ───────────────────────────────────────────────────────────────────

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _valid_email(email: str) -> bool:
    return bool(_EMAIL_RE.match(email))


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("gm_index"))

    error = None
    if request.method == "POST":
        email    = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm  = request.form.get("confirm") or ""

        if not _valid_email(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif db_manager.get_user_by_email(email):
            error = "An account with that email already exists."
        else:
            pw_hash = generate_password_hash(password)
            user_id = db_manager.create_user(email, pw_hash)
            row     = db_manager.get_user_by_id(user_id)
            login_user(User(row), remember=True)
            return redirect(url_for("gm_index"))

    return render_template("signup.html", error=error)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("gm_index"))

    error = None
    if request.method == "POST":
        email    = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        row      = db_manager.get_user_by_email(email)

        if row and check_password_hash(row["password_hash"], password):
            login_user(User(row), remember=True)
            next_url = request.args.get("next") or url_for("gm_index")
            return redirect(next_url)
        else:
            error = "Incorrect email or password."

    return render_template("login.html", error=error)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))
