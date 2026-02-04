from flask import Blueprint, current_app, jsonify, request

from app.services.exchange_service import store_live_update


live_api_bp = Blueprint("live_api", __name__)


def _require_api_key(expected_key):
    provided = request.headers.get("X-Api-Key")
    return provided == expected_key


@live_api_bp.post("/api/liveupdate")
def live_update():
    if not _require_api_key(current_app.config.get("LIVE_API_KEY")):
        return jsonify({"error": "unauthorized"}), 403
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify({"error": "invalid payload"}), 400
    created, record = store_live_update(payload)
    return jsonify({"status": "ok", "stored": created, "id": record.id})
