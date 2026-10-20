import sqlite3

from app import create_app


def test_register_login_logout_flow(client, app):
    response = client.post(
        "/register",
        data={
            "username": "newuser",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/login")

    with sqlite3.connect(app.config["DATABASE"]) as db:
        row = db.execute(
            "SELECT username, password_hash FROM users WHERE username = ?", ("newuser",)
        ).fetchone()
    assert row is not None
    assert row[1] != "password123"
    assert row[1].startswith(("pbkdf2:", "scrypt:"))

    assert client.get("/dashboard").status_code == 302

    response = client.post(
        "/login", data={"username": "newuser", "password": "password123"}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")
    assert client.get("/dashboard").status_code == 200

    response = client.post("/logout")
    assert response.status_code == 302
    assert client.get("/dashboard").status_code == 302


def test_security_feed_is_separate_page(auth_client):
    dashboard = auth_client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"Security Feed" in dashboard.data
    assert b'href="/security"' in dashboard.data
    assert b'id="panel-blocked"' not in dashboard.data

    response = auth_client.get("/security")
    assert response.status_code == 200
    assert b"Security Feed" in response.data
    assert b"Feed keamanan global" in response.data
    assert b'id="panel-blocked"' in response.data
    assert b'id="panel-attacks"' in response.data
    assert b'id="panel-telegram"' in response.data


def test_login_rejects_wrong_password(client):
    client.post(
        "/register",
        data={
            "username": "tester",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    response = client.post(
        "/login", data={"username": "tester", "password": "wrong-password"}
    )
    assert response.status_code == 200
    assert b"Username atau password salah" in response.data
    assert client.get("/dashboard").status_code == 302


def test_register_validates_input(client):
    response = client.post(
        "/register",
        data={
            "username": "ab",
            "password": "short",
            "confirm_password": "different",
        },
    )
    assert response.status_code == 200
    assert b"Username 3-32 karakter" in response.data
    assert b"Password minimal 8 karakter" in response.data
    assert b"Konfirmasi password tidak sama" in response.data


def test_register_rejects_duplicate_username(client):
    data = {
        "username": "duplicate",
        "password": "password123",
        "confirm_password": "password123",
    }
    client.post("/register", data=data)
    response = client.post("/register", data=data)
    assert response.status_code == 200
    assert b"Username sudah digunakan" in response.data


def test_api_requires_authentication(client):
    response = client.get("/api/overview")
    assert response.status_code == 401
    assert response.get_json()["error"] == "unauthorized"


def test_csrf_rejects_post_without_token(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "csrf.db"),
            "SECRET_KEY": "csrf-test",
            "CSRF_ENABLED": True,
            "DATA_MODE": "demo",
        }
    )
    client = app.test_client()
    response = client.post(
        "/register",
        data={
            "username": "csrfuser",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    assert response.status_code == 400
    assert b"CSRF token tidak valid" in response.data


def test_security_feed_requires_auth(client):
    assert client.get("/security").status_code == 302
