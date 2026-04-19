from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Event, ResultPDF
from app.services.exchange_service import import_result_export_zip


results_api_bp = Blueprint("results_api", __name__)


def _require_api_key(expected_key):
    provided = request.headers.get("X-Api-Key")
    return provided == expected_key


@results_api_bp.post("/api/resultexport")
def result_export():
    if not _require_api_key(current_app.config.get("RESULTS_API_KEY")):
        return jsonify({"error": "unauthorized"}), 403

    zip_bytes = None
    if "file" in request.files:
        zip_bytes = request.files["file"].read()
    else:
        zip_bytes = request.get_data()

    if not zip_bytes:
        return jsonify({"error": "missing file"}), 400

    result_import = import_result_export_zip(zip_bytes)
    event_external_id = None
    if result_import.event_id:
        event = Event.query.get(result_import.event_id)
        event_external_id = event.external_id if event else None

    return jsonify(
        {
            "status": "ok",
            "event_external_id": event_external_id,
            "final": result_import.final,
        }
    )


@results_api_bp.post("/api/resultpdf")
def result_pdf_upload():
    """Nimmt ein Ranglisten-PDF von AgilitySoftware entgegen und speichert es."""
    if not _require_api_key(current_app.config.get("RESULTS_API_KEY")):
        return jsonify({"error": "unauthorized"}), 403

    if "file" not in request.files:
        return jsonify({"error": "missing file"}), 400

    pdf_bytes = request.files["file"].read()
    if not pdf_bytes:
        return jsonify({"error": "empty file"}), 400

    event_external_id = request.form.get("event_external_id", "").strip()
    run_name          = request.form.get("run_name", "")
    ring              = request.form.get("ring", "")
    discipline        = request.form.get("discipline", "").lower()   # normalisiert wie Result-Tabelle
    category_code     = request.form.get("category_code", "")
    class_level_str   = request.form.get("class_level", "0")
    is_final          = request.form.get("is_final", "false").lower() == "true"

    try:
        class_level = int(class_level_str)
    except (ValueError, TypeError):
        class_level = 0

    event = Event.query.filter_by(external_id=event_external_id).first()
    if not event:
        return jsonify({"error": "event not found", "external_id": event_external_id}), 404

    # Bestehendes PDF für denselben Lauf ersetzen
    existing = ResultPDF.query.filter_by(
        event_id=event.id,
        ring=ring,
        discipline=discipline,
        category_code=category_code,
        class_level=class_level,
    ).first()

    if existing:
        existing.pdf_data  = pdf_bytes
        existing.run_name  = run_name
        existing.is_final  = is_final
        existing.created_at = datetime.utcnow()
    else:
        pdf = ResultPDF(
            event_id=event.id,
            run_name=run_name,
            ring=ring,
            discipline=discipline,
            category_code=category_code,
            class_level=class_level,
            pdf_data=pdf_bytes,
            is_final=is_final,
        )
        db.session.add(pdf)

    db.session.commit()
    return jsonify({"status": "ok", "event_id": event.id})
