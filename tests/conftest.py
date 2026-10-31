import pytest

import db as dbmod
from app import create_app
from helpers import login


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "SECRET_KEY": "test-secret",
    })
    with app.app_context():
        dbmod.seed()
    return app


@pytest.fixture
def anon(app):
    return app.test_client()


@pytest.fixture
def admin(app):
    client = app.test_client()
    login(client, "admin@example.com", "admin123")
    return client


@pytest.fixture
def student(app):
    client = app.test_client()
    login(client, "aarav@example.com", "user123")
    return client
