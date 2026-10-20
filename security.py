import secrets
from hmac import compare_digest

from flask import abort, current_app, request, session


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    return token


def csrf_protect():
    if not current_app.config.get("CSRF_ENABLED", True):
        return
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    expected = session.get("csrf_token")
    if not token or not expected or not compare_digest(token, expected):
        abort(400, description="CSRF token tidak valid. Muat ulang halaman lalu coba lagi.")
