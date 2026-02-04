from functools import wraps

from flask import Blueprint, Response, abort, current_app, request

from app.extensions import db
from app.models import ExchangeExportLog
from app.services.exchange_service import EVENT_EXPORT_SCHEMA, build_event_export_zip


exchange_admin_bp = Blueprint("exchange_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


@exchange_admin_bp.get("/admin/exchange/events/<int:event_id>/export")
@_require_admin_key
def export_event_exchange(event_id):
    zip_bytes, filename, sha256 = build_event_export_zip(event_id)
    export_log = ExchangeExportLog(
        event_id=event_id,
        export_type="EVENT_EXPORT",
        schema=EVENT_EXPORT_SCHEMA,
        file_path=filename,
        sha256=sha256,
    )
    db.session.add(export_log)
    db.session.commit()

    response = Response(zip_bytes, mimetype="application/zip")
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response
