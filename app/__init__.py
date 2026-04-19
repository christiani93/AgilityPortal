import os

from dotenv import load_dotenv
from flask import Flask, redirect, url_for, render_template, session, request as flask_request
from flask_login import current_user

from .blueprints import register_blueprints
from .extensions import db, migrate, login_manager, mail, babel

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

    # --- Website-Sync (AdminPortal / z-b.tech) ---
    app.config["WEBSITE_API_URL"] = os.environ.get("WEBSITE_API_URL", "")
    app.config["WEBSITE_API_TOKEN"] = os.environ.get("WEBSITE_API_TOKEN", "")
    app.config["PORTAL_PUBLIC_URL"] = os.environ.get("PORTAL_PUBLIC_URL", "")

    # --- Superadmin (Portal-Verwaltung: Vereine & Club-Admins) ---
    app.config["SUPERADMIN_USERNAME"] = os.environ.get("SUPERADMIN_USERNAME", "")
    app.config["SUPERADMIN_PASSWORD"] = os.environ.get("SUPERADMIN_PASSWORD", "")

    # --- Mail ---
    app.config["MAIL_SERVER"] = os.environ.get("MAIL_SERVER", "")
    app.config["MAIL_PORT"] = int(os.environ.get("MAIL_PORT", 587))
    app.config["MAIL_USE_TLS"] = os.environ.get("MAIL_USE_TLS", "false").lower() == "true"
    app.config["MAIL_USE_SSL"] = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    app.config["MAIL_USERNAME"] = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"] = os.environ.get("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = os.environ.get("MAIL_DEFAULT_SENDER", "noreply@z-b.tech")
    app.config["MAIL_TIMEOUT"] = 5
    app.config["NOTIFY_EMAIL"] = os.environ.get("ADMIN_EMAIL", os.environ.get("NOTIFY_EMAIL", "info@z-b.tech"))

    # --- Babel / i18n ---
    app.config["BABEL_DEFAULT_LOCALE"] = "de"
    app.config["BABEL_SUPPORTED_LOCALES"] = ["de", "fr", "en"]

    def get_locale():
        lang = session.get("lang")
        if lang in ["de", "fr", "en"]:
            return lang
        return flask_request.accept_languages.best_match(["de", "fr", "en"], default="de")

    # --- Extensions ---
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    mail.init_app(app)
    babel.init_app(app, locale_selector=get_locale)

    @app.context_processor
    def inject_globals():
        from flask_wtf.csrf import generate_csrf
        return {"get_locale": get_locale, "csrf_token": generate_csrf}

    @app.template_filter("localtime")
    def localtime_filter(dt, fmt="%d.%m. %H:%M"):
        """Konvertiert ein UTC-datetime in Schweizer Lokalzeit (Europe/Zurich)."""
        if dt is None:
            return "—"
        try:
            from zoneinfo import ZoneInfo
            from datetime import timezone
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            zurich = ZoneInfo("Europe/Zurich")
            return dt.astimezone(zurich).strftime(fmt)
        except Exception:
            return dt.strftime(fmt)

    # User-Loader für Flask-Login
    from .models import User

    @login_manager.user_loader
    def load_user(user_id: str):
        return db.session.get(User, int(user_id))

    # --- Blueprints ---
    register_blueprints(app)

    # --- CLI-Befehle ---
    from .commands import seed_test_regs, clear_test_regs, create_test_event
    app.cli.add_command(seed_test_regs)
    app.cli.add_command(clear_test_regs)
    app.cli.add_command(create_test_event)

    @app.get("/")
    def home():
        if current_user.is_authenticated:
            return redirect(url_for("club.dashboard"))
        return render_template("home.html")

    @app.get("/lang/<lang_code>")
    def set_language(lang_code):
        if lang_code in ["de", "fr", "en"]:
            session["lang"] = lang_code
        return redirect(flask_request.referrer or url_for("club.dashboard"))

    return app
