from functools import wraps

from flask import jsonify, redirect, request, session, url_for

from security import bearer_token_valid


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            if request.path.startswith("/api/"):
                return (
                    jsonify(
                        error="unauthorized",
                        message="Sesi berakhir. Silakan login kembali.",
                    ),
                    401,
                )
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def login_or_token_required(view):
    """Izinkan session login ATAU header Authorization: Bearer <DASHBOARD_API_TOKEN>."""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") or bearer_token_valid():
            return view(*args, **kwargs)
        if request.path.startswith("/api/"):
            return (
                jsonify(
                    error="unauthorized",
                    message="Sesi berakhir. Silakan login kembali atau pakai Bearer token.",
                ),
                401,
            )
        return redirect(url_for("auth.login", next=request.path))

    return wrapped
