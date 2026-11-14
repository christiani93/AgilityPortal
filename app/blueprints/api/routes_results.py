from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from app.extensions import db
from app.models import Event, ResultPDF
from app.services.exchange_service import import_result_export_zip
from app.services.bccs_qualification_service import calculate_bccs_finalists


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


@results_api_bp.post("/api/events/<int:event_id>/bccs-finalists")
def calculate_bccs_event_finalists(event_id):
    """
    Berechnet die BCCS-SM-Finalisten für ein Event und speichert sie.

    Authentifizierung: RESULTS_API_KEY

    Input: event_id (URL)

    Output:
      {
        "status": "ok",
        "event_id": int,
        "divisions": {
          "Intermediate/sm": { quota, finalists_count, ... },
          ...
        },
        "finalists_count": int,
      }
    """
    if not _require_api_key(current_app.config.get("RESULTS_API_KEY")):
        return jsonify({"error": "unauthorized"}), 403

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"error": "event not found"}), 404

    if event.type != "bccs_sm":
        return jsonify({"error": "event is not a bccs_sm event"}), 400

    try:
        result = calculate_bccs_finalists(event)

        # Konstruiere Response
        divisions_summary = {}
        for div_key, div_data in result.get("divisions", {}).items():
            divisions_summary[div_key] = {
                "quota": div_data.get("quota"),
                "finalists_count": len(div_data.get("finalists", [])),
                "open_spots": div_data.get("open_spots", 0),
            }

        return jsonify({
            "status": "ok",
            "event_id": event.id,
            "divisions": divisions_summary,
            "finalists_count": len(result.get("finalists", [])),
        })

    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        current_app.logger.exception(f"Error calculating BCCS finalists for event {event_id}")
        return jsonify({"error": f"internal error: {str(e)}"}), 500
