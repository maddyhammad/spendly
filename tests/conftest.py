import pytest

from app import app as flask_app
from database.db import init_db


@pytest.fixture
def app(tmp_path, monkeypatch):
    """The Flask app wired to a fresh, throwaway database (never spendly.db)."""
    monkeypatch.setitem(flask_app.config, "TESTING", True)
    monkeypatch.setitem(flask_app.config, "DATABASE", str(tmp_path / "test.db"))
    with flask_app.app_context():
        init_db()
    return flask_app


@pytest.fixture
def client(app):
    return app.test_client()
