from .admin.routes_events import event_admin_bp
from .admin.routes_exchange import exchange_admin_bp
from .admin.routes_schedule import schedule_admin_bp
from .admin.routes_start_numbers import start_numbers_admin_bp
from .admin.routes_tka import tka_admin_bp
from .api.routes_live import live_api_bp
from .api.routes_results import results_api_bp
from .public.routes_events import public_events_bp


def register_blueprints(app):
    app.register_blueprint(tka_admin_bp)
    app.register_blueprint(exchange_admin_bp)
    app.register_blueprint(event_admin_bp)
    app.register_blueprint(start_numbers_admin_bp)
    app.register_blueprint(schedule_admin_bp)
    app.register_blueprint(live_api_bp)
    app.register_blueprint(results_api_bp)
    app.register_blueprint(public_events_bp)
