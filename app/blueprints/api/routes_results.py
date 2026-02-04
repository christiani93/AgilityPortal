from flask import Blueprint, current_app, jsonify, request

from app.models import Event
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
