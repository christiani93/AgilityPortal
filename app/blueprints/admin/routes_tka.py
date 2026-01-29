from functools import wraps

from flask import Blueprint, Response, abort, current_app, jsonify, render_template, request

from app.extensions import db
from app.models import Dog, Event, LicenseKind, Registration, RegistrationStatus, TkaExportBatch, TkaExportType
from app.services.tka_service import (
    apply_tka_import,
    build_event_check_batch,
    build_master_check_batch,
    render_batch_to_csv,
)


tka_admin_bp = Blueprint("tka_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def _get_raw_text():
    if "file" in request.files:
        uploaded = request.files["file"]
        return uploaded.read().decode("utf-8")
    return request.form.get("raw_text", "")


def _latest_batch_id(export_type, event_id=None):
    query = TkaExportBatch.query.filter_by(export_type=export_type)
    if event_id is not None:
        query = query.filter_by(event_id=event_id)
    batch = query.order_by(TkaExportBatch.exported_at.desc()).first()
    return batch.id if batch else None


@tka_admin_bp.get("/admin/tka")
@_require_admin_key
def tka_home():
    return render_template("admin/tka_home.html", admin_key=request.args.get("key", ""))


@tka_admin_bp.get("/admin/tka/master/export")
@_require_admin_key
def export_master_check():
    batch = build_master_check_batch(created_by_user_id=None)
    csv_data = render_batch_to_csv(batch.id)
    response = Response(csv_data, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=master_check.csv"
    response.headers["X-Tka-Batch-Id"] = str(batch.id)
    return response


@tka_admin_bp.post("/admin/tka/master/import")
@_require_admin_key
def import_master_check():
    batch_id = request.form.get("batch_id", type=int) or _latest_batch_id(TkaExportType.MASTER_CHECK)
    raw_text = _get_raw_text()
    if not batch_id:
        return jsonify({"error": "batch_id required"}), 400
    tka_import = apply_tka_import(batch_id=batch_id, raw_text=raw_text, imported_by_user_id=None)
    return jsonify({"import_id": tka_import.id, "batch_id": batch_id})


@tka_admin_bp.get("/admin/tka/events/<int:event_id>")
@_require_admin_key
def tka_event(event_id):
    return render_template(
        "admin/tka_event.html", event_id=event_id, admin_key=request.args.get("key", "")
    )


@tka_admin_bp.get("/admin/tka/events/<int:event_id>/export")
@_require_admin_key
def export_event_check(event_id):
    batch = build_event_check_batch(event_id=event_id, created_by_user_id=None)
    csv_data = render_batch_to_csv(batch.id)
    response = Response(csv_data, mimetype="text/csv")
    response.headers["Content-Disposition"] = "attachment; filename=event_check.csv"
    response.headers["X-Tka-Batch-Id"] = str(batch.id)
    return response


@tka_admin_bp.post("/admin/tka/events/<int:event_id>/import")
@_require_admin_key
def import_event_check(event_id):
    batch_id = request.form.get("batch_id", type=int) or _latest_batch_id(
        TkaExportType.EVENT_CHECK, event_id=event_id
    )
    raw_text = _get_raw_text()
    if not batch_id:
        return jsonify({"error": "batch_id required"}), 400
    tka_import = apply_tka_import(batch_id=batch_id, raw_text=raw_text, imported_by_user_id=None)
    return jsonify({"import_id": tka_import.id, "batch_id": batch_id})


@tka_admin_bp.get("/admin/tka/dev/seed")
@_require_admin_key
def seed_tka_data():
    event = Event(name="Agility Test Event", location="Test Hall")
    dog_ch = Dog(name="Rex", license_no="12345", license_kind=LicenseKind.CH)
    dog_foreign = Dog(name="Luna", license_no="AAA-999", license_kind=LicenseKind.FOREIGN)

    reg_ch = Registration(
        event=event,
        dog=dog_ch,
        status=RegistrationStatus.SUBMITTED,
        class_level=1,
        category_code="Large",
    )
    reg_foreign = Registration(
        event=event,
        dog=dog_foreign,
        status=RegistrationStatus.SUBMITTED,
        class_level=1,
        category_code="Small",
    )
    reg_foreign.apply_license_kind_defaults()

    db.session.add_all([event, dog_ch, dog_foreign, reg_ch, reg_foreign])
    db.session.commit()

    return jsonify({"event_id": event.id, "dog_ch_id": dog_ch.id, "dog_foreign_id": dog_foreign.id})
