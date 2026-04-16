import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, render_template
from flask_login import current_user

from .blueprints import register_blueprints
from .extensions import db, migrate, login_manager

# .env laden (absoluter Pfad für Gunicorn-Kompatibilität)
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"), override=False)
if "DATABASE_URL" not in os.environ:
    load_dotenv(override=False)


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)

    # --- Datenbank ---
    database_uri = os.environ.get("DATABASE_URL")
    if not database_uri:
        database_uri = f"sqlite:///{os.path.join(app.instance_path, 'app.db')}"

    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-only-secret-change-in-prod")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_uri
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # --- API-Keys (für Admin, Live, Results) ---
    app.config["ADMIN_KEY"] = os.environ.get("ADMIN_KEY", "dev-admin-key")
    app.config["LIVE_API_KEY"] = os.environ.get("LIVE_API_KEY", "dev-live-key")
    app.config["RESULTS_API_KEY"] = os.environ.get("RESULTS_API_KEY", "dev-results-key")

    # --- Superadmin (Portal-Verwaltung: Vereine & Club-Admins) ---
    app.config["SUPERADMIN_USERNAME"] = os.environ.get("SUPERADMIN_USERNAME", "")
    app.config["SUPERADMIN_PASSWORD"] = os.environ.get("SUPERADMIN_PASSWORD", "")

    # --- Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)

    # User-Loader für Flask-Login
    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # --- Blueprints ---
    register_blueprints(app)

    @app.get("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("club.dashboard"))
        return render_template("home.html")

    return app
