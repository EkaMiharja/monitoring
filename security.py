import secrets
from hmac import compare_digest

from flask import abort, current_app, request, session


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def get_bearer_token():
    header = request.headers.get("Authorization") or ""
    prefix = "bearer "
    if header.lower().startswith(prefix):
        return header[len(prefix):].strip()
    return ""


def bearer_token_valid():
    """True bila Authorization: Bearer cocok dengan DASHBOARD_API_TOKEN."""
    expected = current_app.config.get("DASHBOARD_API_TOKEN") or ""
    if not expected:
        return False
    token = get_bearer_token()
    return bool(token) and compare_digest(token, expected)


def csrf_protect():
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token")
    if not token or not expected or not compare_digest(token, expected):
        abort(400, description="CSRF token tidak valid. Muat ulang halaman lalu coba lagi.")
