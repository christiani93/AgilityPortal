from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models import BillingMode, Event


event_admin_bp = Blueprint("event_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


@event_admin_bp.route("/admin/events/<int:event_id>/billing", methods=["GET", "POST"])
@_require_admin_key
def event_billing(event_id):
    event = Event.query.get_or_404(event_id)
    if request.method == "POST":
        billing_mode = request.form.get("billing_mode")
        billing_notes = request.form.get("billing_notes")
        if billing_mode not in {mode.value for mode in BillingMode}:
            return jsonify({"error": "invalid billing_mode"}), 400
        event.billing_mode = BillingMode(billing_mode)
        event.billing_notes = billing_notes
        db.session.commit()
        return redirect(url_for("event_admin.event_billing", event_id=event.id, key=request.args.get("key")))

    return render_template(
        "admin/event_billing.html",
        event=event,
        billing_modes=[mode.value for mode in BillingMode],
        admin_key=request.args.get("key", ""),
    )
