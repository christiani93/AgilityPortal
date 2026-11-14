from functools import wraps

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, url_for

from app.extensions import db
from app.models import BillingMode, Event, EventFinalist


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


@event_admin_bp.route("/admin/events/<int:event_id>/title-defenders", methods=["GET", "POST"])
@_require_admin_key
def event_title_defenders(event_id):
    """TV-Register: Titelverteidiger für HCS, SKBS-SM, BCCS-SM, WiMeSma"""
    event = Event.query.get_or_404(event_id)

    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            license_no = (request.form.get("license_no") or "").strip()
            dog_name = (request.form.get("dog_name") or "").strip()
            handler_name = (request.form.get("handler_name") or "").strip()
            category = request.form.get("category") or None  # BCCS: Large/Intermediate
            division = request.form.get("division") or None   # BCCS: sm/nachwuchs

            if not all([license_no, dog_name, handler_name]):
                return jsonify({"error": "Lizenz, Hund und Läufer erforderlich"}), 400

            # Duplikat-Check pro Kategorie/Division
            existing = EventFinalist.query.filter_by(
                event_id=event_id,
                license=license_no,
                source="title_defender",
                category=category,
                division=division,
            ).first()
            if existing:
                return jsonify({"error": "TV existiert bereits"}), 400

            # Position = nächste Nummer
            max_pos = db.session.query(db.func.max(EventFinalist.position)).filter_by(
                event_id=event_id, source="title_defender"
            ).scalar() or 0

            finalist = EventFinalist(
                event_id=event_id,
                license=license_no,
                dog_name=dog_name,
                handler_name=handler_name,
                source="title_defender",
                from_class=None,
                category=category,
                division=division,
                position=max_pos + 1,
            )
            db.session.add(finalist)
            db.session.commit()
            return redirect(url_for("event_admin.event_title_defenders", event_id=event_id, key=request.args.get("key")))

        elif action == "delete":
            finalist_id = request.form.get("finalist_id", type=int)
            finalist = EventFinalist.query.filter_by(id=finalist_id, event_id=event_id, source="title_defender").first_or_404()
            db.session.delete(finalist)
            db.session.commit()
            return redirect(url_for("event_admin.event_title_defenders", event_id=event_id, key=request.args.get("key")))

    # GET: Zeige Liste der TV
    title_defenders = EventFinalist.query.filter_by(
        event_id=event_id, source="title_defender"
    ).order_by(EventFinalist.category, EventFinalist.division, EventFinalist.position).all()

    return render_template(
        "admin/event_title_defenders.html",
        event=event,
        title_defenders=title_defenders,
        admin_key=request.args.get("key", ""),
    )
