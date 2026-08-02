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
    app.config.update(TESTING=True)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
