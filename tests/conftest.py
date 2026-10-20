import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402


@pytest.fixture
def app(tmp_path):
    application = create_app(
        {
            "TESTING": True,
            "DATABASE": str(tmp_path / "dashboard-test.db"),
            "SECRET_KEY": "test-secret",
            "CSRF_ENABLED": False,
            "DATA_MODE": "demo",
        }
    )
    yield application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(client):
    client.post(
        "/register",
        data={
            "username": "tester",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    response = client.post(
        "/login",
        data={"username": "tester", "password": "password123"},
    )
    assert response.status_code == 302
    return client
