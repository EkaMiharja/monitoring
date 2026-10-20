import re
import sqlite3
from urllib.parse import urlparse

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from db import get_db
from security import csrf_protect
from utils import iso, utc_now

bp = Blueprint("auth", __name__)

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
MIN_PASSWORD_LENGTH = 8


def _safe_next(value):
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _find_user(username):
    return (
        get_db()
        .execute("SELECT * FROM users WHERE username = ? COLLATE NOCASE", (username,))
        .fetchone()
    )


@bp.route("/register", methods=("GET", "POST"))
def register():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    form = {"username": ""}
    errors = []

    if request.method == "POST":
        csrf_protect()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm_password") or ""
        form["username"] = username

        if not USERNAME_RE.match(username):
            errors.append("Username 3-32 karakter, hanya huruf, angka, titik, garis bawah, atau strip.")
        if len(password) < MIN_PASSWORD_LENGTH:
            errors.append(f"Password minimal {MIN_PASSWORD_LENGTH} karakter.")
        if password != confirm:
            errors.append("Konfirmasi password tidak sama.")
            form["username"] = username

        if not errors:
            try:
                db = get_db()
                db.execute(
                    "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                    (username, generate_password_hash(password), iso(utc_now())),
                )
                db.commit()
            except sqlite3.IntegrityError:
                errors.append("Username sudah digunakan. Pilih username lain.")

        if not errors:
            flash("Registrasi berhasil. Silakan login.", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form, errors=errors)


@bp.route("/login", methods=("GET", "POST"))
def login():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    form = {"username": ""}
    errors = []
    next_url = _safe_next(request.args.get("next") or request.form.get("next"))

    if request.method == "POST":
        csrf_protect()
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        form["username"] = username

        if not username or not password:
            errors.append("Username dan password wajib diisi.")
        else:
            user = _find_user(username)
            if user is None or not check_password_hash(user["password_hash"], password):
                errors.append("Username atau password salah.")

        if not errors:
            session.clear()
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session.permanent = True
            flash("Login berhasil. Selamat datang.", "success")
            return redirect(next_url or url_for("dashboard"))

    return render_template("auth/login.html", form=form, errors=errors, next_url=next_url or "")


@bp.route("/logout", methods=("POST",))
def logout():
    if session.get("user_id"):
        csrf_protect()
    session.clear()
    flash("Anda telah logout.", "success")
    return redirect(url_for("auth.login"))
