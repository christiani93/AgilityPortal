from .admin.routes_tka import tka_admin_bp


def register_blueprints(app):
    app.register_blueprint(tka_admin_bp)
