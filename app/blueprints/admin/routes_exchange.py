from datetime import datetime
from functools import wraps

from flask import Blueprint, Response, abort, current_app, jsonify, request

from app.extensions import db
from app.models import Event, ExchangeExportLog
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


@exchange_admin_bp.route("/admin/exchange/debug/ensure_test_event/<external_id>",
                         methods=["GET", "POST"])
@_require_admin_key
def ensure_test_event(external_id):
    """
    Stellt sicher dass ein Event mit dieser external_id im Portal existiert.
    Wenn nicht: legt es als Test-Event an (is_test=True, alles unsichtbar).

    Default-Behaviour ist non-destructive: bestehende Events werden NICHT
    überschrieben (auch wenn sie nicht is_test=True sind).

    Query/Form-Parameter (optional):
      - name:  Event-Bezeichnung (Default: "Test Event <id>")
      - date:  Datum YYYY-MM-DD (Default: heute)

    Antwort: JSON mit {created, event_id, external_id, is_test, is_published}.
    Geeignet als HTTP-Call vom Software-Generator oder manueller Browser-Aufruf.
    """
    existing = Event.query.filter_by(external_id=external_id).first()
    if existing:
        return jsonify({
            "created":       False,
            "event_id":      existing.id,
            "external_id":   external_id,
            "is_test":       existing.is_test,
            "is_published":  existing.is_published,
            "name":          existing.name,
        })

    name = (request.values.get("name") or f"Test Event {external_id[:8]}").strip()
    date_str = (request.values.get("date") or "").strip()
    starts_at = None
    if date_str:
        try:
            starts_at = datetime.fromisoformat(date_str)
        except ValueError:
            starts_at = None
    if not starts_at:
        starts_at = datetime.utcnow()

    event = Event(
        external_id=external_id,
        name=name,
        starts_at=starts_at,
        is_test=True,
        is_published=False,
        startlist_public=False,
        schedule_public=False,
        results_public=False,
    )
    db.session.add(event)
    db.session.commit()
    return jsonify({
        "created":       True,
        "event_id":      event.id,
        "external_id":   external_id,
        "is_test":       event.is_test,
        "is_published":  event.is_published,
        "name":          event.name,
    })
