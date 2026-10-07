"""
Admin-Routen für die Spezialturnier-Freigabe (welche Vereine dürfen Turniere
mit einem bestimmten special_ruleset anlegen, z.B. Edelweiss Challenge).

Unabhängig vom Cup-System (CupAllowedOrganiser): diese Freigabe gilt direkt
für das Event/die Vorlage, nicht erst beim Einhängen in einen Saison-Cup.

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie die übrigen Admin-Routen).
"""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app
from flask_login import current_user

from app.extensions import db
from app.models import Club, Event, SpecialRulesetAllowedClub

special_rulesets_admin_bp = Blueprint("special_rulesets_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
            return func(*args, **kwargs)
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def _admin_key():
    if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
        return ""
    return request.args.get("key") or ""


# ── Übersicht ───────────────────────────────────────────────────────────────

@special_rulesets_admin_bp.get("/admin/special-ruleset-assignments")
@_require_admin_key
def special_ruleset_assignments():
    """Übersicht: welche Vereine dürfen welches Spezialturnier-Ruleset anlegen."""
    clubs = Club.query.order_by(Club.name).all()
    rulesets = list(Event.SPECIAL_RULESET_LABELS.items())  # [(code, label), ...]
    # Matrix: {club.id: {ruleset_code: bool}}
    matrix = {}
    for club in clubs:
        matrix[club.id] = {
            code: Event.special_ruleset_allows_club(code, club.id)
            for code, _label in rulesets
        }
    restricted = [code for code, _label in rulesets if Event.special_ruleset_restricts(code)]
    allowed_club_ids = {code: Event.special_ruleset_allowed_club_ids(code) for code in restricted}
    return render_template(
        "admin/special_rulesets/assignments.html",
        clubs=clubs,
        rulesets=rulesets,
        matrix=matrix,
        restricted=restricted,
        allowed_club_ids=allowed_club_ids,
        admin_key=_admin_key(),
    )


# ── Freigabe pro Ruleset bearbeiten ──────────────────────────────────────────

@special_rulesets_admin_bp.route("/admin/special-ruleset-assignments/<ruleset>/edit", methods=["GET", "POST"])
@_require_admin_key
def special_ruleset_edit(ruleset):
    if ruleset not in Event.SPECIAL_RULESET_LABELS:
        abort(404)
    clubs = Club.query.order_by(Club.name).all()

    if request.method == "POST":
        selected_club_ids = {int(v) for v in request.form.getlist("allowed_club_ids") if v.isdigit()}
        SpecialRulesetAllowedClub.query.filter_by(ruleset=ruleset).delete()
        for club_id in selected_club_ids:
            club = db.session.get(Club, club_id)
            if club:
                db.session.add(SpecialRulesetAllowedClub(ruleset=ruleset, club_id=club_id))
        db.session.commit()
        flash(f"Freigabe für «{Event.SPECIAL_RULESET_LABELS[ruleset]}» gespeichert.", "success")
        return redirect(url_for("special_rulesets_admin.special_ruleset_assignments", key=_admin_key()))

    allowed_club_ids = Event.special_ruleset_allowed_club_ids(ruleset)
    return render_template(
        "admin/special_rulesets/edit.html",
        ruleset=ruleset,
        ruleset_label=Event.SPECIAL_RULESET_LABELS[ruleset],
        clubs=clubs,
        allowed_club_ids=allowed_club_ids,
        admin_key=_admin_key(),
    )
