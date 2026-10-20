from functools import wraps

from flask import jsonify, redirect, request, session, url_for


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
