import os
import sys

import pytest


sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402


@pytest.fixture()
def app():
    # WICHTIG: In-Memory-DB via Env VOR create_app() setzen. Sonst bindet die Engine an
    # die Datei-DB (instance/app.db, DATABASE_URL-Default) und db.drop_all() im Teardown
    # löscht die lokale Dev-DB! (config.update("SQLALCHEMY_DATABASE_URI") danach greift nicht mehr.)
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config.update(TESTING=True, ADMIN_KEY="test-admin-key-123")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    """Test client for the app"""
    return app.test_client()


@pytest.fixture()
def admin_key(app):
    """Admin key for protected routes"""
    return app.config.get("ADMIN_KEY")


@pytest.fixture()
def database(app):
    """Database instance"""
    with app.app_context():
        yield db
