import os

from flask import Flask

from .blueprints import register_blueprints
from .extensions import db


def create_app(config_name=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    database_uri = os.environ.get("SQLALCHEMY_DATABASE_URI")
    if not database_uri:
        database_uri = f"sqlite:///{os.path.join(app.instance_path, 'app.db')}"

    app.config.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "dev-only-secret"))
    app.config.setdefault("SQLALCHEMY_DATABASE_URI", database_uri)
    app.config.setdefault("SQLALCHEMY_TRACK_MODIFICATIONS", False)
    app.config.setdefault("ADMIN_KEY", os.environ.get("ADMIN_KEY", "dev-admin-key"))
    app.config.setdefault("LIVE_API_KEY", os.environ.get("LIVE_API_KEY", "dev-live-key"))
    app.config.setdefault("RESULTS_API_KEY", os.environ.get("RESULTS_API_KEY", "dev-results-key"))

    db.init_app(app)
    register_blueprints(app)

    @app.get("/")
    def health_check():
        return "AgilityPortal OK"

    return app
