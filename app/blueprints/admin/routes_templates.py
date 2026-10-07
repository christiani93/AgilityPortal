"""
Admin-Routen für Turnier-Vorlagen (jährlich wiederkehrende Veranstaltungen).

Eine Vorlage speichert die stabilen Felder (Name, Typ/Ruleset, Veranstalter,
Läufe, Config). Beim Erzeugen eines konkreten Turniers werden nur die jährlich
wechselnden Felder abgefragt (Daten + AIS-Nummer(n)).

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie die übrigen Admin-Routen).
"""
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for, current_app)
from flask_login import current_user

from app.extensions import db
from app.models import (Club, Event, EventTemplate, EventTemplateRun)
from app.services.template_service import create_event_from_template


templates_admin_bp = Blueprint("templates_admin", __name__)

_CATEGORIES = ("L", "I", "M", "S")
_CLASSES = (1, 2, 3)
_DISCIPLINES = ("agility", "jumping")


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


def _parse_decimal(raw):
    if not raw:
        return None
    try:
        return Decimal(raw.replace(",", "."))
    except (InvalidOperation, AttributeError):
        return None


def _parse_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _template_from_form(tpl: EventTemplate) -> EventTemplate:
    """Übernimmt die Formularfelder in die Vorlage (ohne Läufe)."""
    tpl.name = (request.form.get("name") or "").strip()
    tpl.default_event_name = (request.form.get("default_event_name") or "").strip() or None
    tpl.location = (request.form.get("location") or "").strip() or None
    tpl.day_count = _parse_int(request.form.get("day_count")) or 1
    tpl.type = (request.form.get("type") or "regular").strip()
    tpl.special_ruleset = (request.form.get("special_ruleset") or "").strip() or None
    tpl.organiser_club_id = _parse_int(request.form.get("organiser_club_id"))
    tpl.pruefungsleiter = (request.form.get("pruefungsleiter") or "").strip() or None
    tpl.entry_fee = _parse_decimal(request.form.get("entry_fee"))
    tpl.max_participants = _parse_int(request.form.get("max_participants"))
    tpl.allows_bitches_in_season = bool(request.form.get("allows_bitches_in_season"))
    tpl.bitches_in_season_start_last = bool(request.form.get("bitches_in_season_start_last"))
    tpl.ring_count = _parse_int(request.form.get("ring_count")) or 1
    tpl.notes_public = (request.form.get("notes_public") or "").strip() or None
    # Webseite + Reservation
    tpl.event_description_de = (request.form.get("event_description_de") or "").strip() or None
    tpl.contact_name = (request.form.get("contact_name") or "").strip() or None
    tpl.contact_email = (request.form.get("contact_email") or "").strip() or None
    tpl.contact_phone = (request.form.get("contact_phone") or "").strip() or None
    tpl.reservation_notes = (request.form.get("reservation_notes") or "").strip() or None
    tpl.option_special_eval = bool(request.form.get("option_special_eval"))
    tpl.option_website = bool(request.form.get("option_website"))
    tpl.option_event_support = bool(request.form.get("option_event_support"))
    tpl.reservation_shared = bool(request.form.get("reservation_shared"))
    tpl.registration_external = bool(request.form.get("registration_external"))
    tpl.registration_url = (request.form.get("registration_url") or "").strip() or None
    return tpl


# ── Liste ──────────────────────────────────────────────────────────────────────

@templates_admin_bp.get("/admin/templates")
@_require_admin_key
def template_list():
    templates = EventTemplate.query.order_by(EventTemplate.name).all()
    return render_template("admin/templates/list.html",
                           templates=templates, admin_key=_admin_key())


# ── Anlegen ────────────────────────────────────────────────────────────────────

@templates_admin_bp.route("/admin/templates/new", methods=["GET", "POST"])
@_require_admin_key
def template_new():
    clubs = Club.query.order_by(Club.name).all()
    if request.method == "POST":
        tpl = _template_from_form(EventTemplate())
        if not tpl.name:
            flash("Name der Vorlage ist erforderlich.", "danger")
            return render_template("admin/templates/form.html", tpl=None, clubs=clubs,
                                   type_labels=Event.TYPE_LABELS,
                                   ruleset_labels=Event.SPECIAL_RULESET_LABELS,
                                   admin_key=_admin_key())
        db.session.add(tpl)
        db.session.commit()
        flash(f"Vorlage «{tpl.name}» wurde angelegt.", "success")
        return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))
    return render_template("admin/templates/form.html", tpl=None, clubs=clubs,
                           type_labels=Event.TYPE_LABELS,
                           ruleset_labels=Event.SPECIAL_RULESET_LABELS,
                           admin_key=_admin_key())


# ── Bearbeiten (inkl. Läufe) ────────────────────────────────────────────────────

@templates_admin_bp.route("/admin/templates/<int:tpl_id>/edit", methods=["GET", "POST"])
@_require_admin_key
def template_edit(tpl_id):
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    clubs = Club.query.order_by(Club.name).all()
    if request.method == "POST":
        _template_from_form(tpl)
        if not tpl.name:
            flash("Name der Vorlage ist erforderlich.", "danger")
        else:
            db.session.commit()
            flash("Vorlage gespeichert.", "success")
            return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))
    return render_template("admin/templates/form.html", tpl=tpl, clubs=clubs,
                           type_labels=Event.TYPE_LABELS,
                           ruleset_labels=Event.SPECIAL_RULESET_LABELS,
                           admin_key=_admin_key())


@templates_admin_bp.post("/admin/templates/<int:tpl_id>/delete")
@_require_admin_key
def template_delete(tpl_id):
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    name = tpl.name
    db.session.delete(tpl)
    db.session.commit()
    flash(f"Vorlage «{name}» gelöscht.", "success")
    return redirect(url_for("templates_admin.template_list", key=_admin_key()))


# ── Läufe der Vorlage ───────────────────────────────────────────────────────────

@templates_admin_bp.post("/admin/templates/<int:tpl_id>/runs/add")
@_require_admin_key
def template_run_add(tpl_id):
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    run_type = (request.form.get("run_type") or "").strip()
    category = (request.form.get("category") or "").strip()
    class_level = _parse_int(request.form.get("class_level"))
    is_final = bool(request.form.get("is_final"))
    if run_type and category and class_level:
        exists = any(r.run_type == run_type and r.category == category
                     and r.class_level == class_level and r.is_final == is_final
                     for r in tpl.runs)
        if not exists:
            next_sort = max((r.sort_index for r in tpl.runs), default=0) + 1
            db.session.add(EventTemplateRun(
                template_id=tpl.id, run_type=run_type, category=category,
                class_level=class_level, is_final=is_final, sort_index=next_sort))
            db.session.commit()
            flash("Lauf hinzugefügt.", "success")
        else:
            flash("Dieser Lauf existiert bereits.", "warning")
    return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))


@templates_admin_bp.post("/admin/templates/<int:tpl_id>/runs/<int:run_id>/move")
@_require_admin_key
def template_run_move(tpl_id, run_id):
    """Verschiebt einen Lauf in der Reihenfolge (up/down) durch sort_index-Tausch."""
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    run = db.session.get(EventTemplateRun, run_id)
    if not run or run.template_id != tpl.id:
        abort(404)
    direction = request.form.get("direction")
    ordered = list(tpl.runs)  # bereits nach sort_index sortiert
    idx = ordered.index(run)
    swap_with = None
    if direction == "up" and idx > 0:
        swap_with = ordered[idx - 1]
    elif direction == "down" and idx < len(ordered) - 1:
        swap_with = ordered[idx + 1]
    if swap_with is not None:
        run.sort_index, swap_with.sort_index = swap_with.sort_index, run.sort_index
        db.session.commit()
    return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))


@templates_admin_bp.post("/admin/templates/<int:tpl_id>/runs/generate")
@_require_admin_key
def template_runs_generate(tpl_id):
    """Standard-Läufe erzeugen: Agility + Jumping, alle Kategorien, Klassen 1-3."""
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    existing = {(r.run_type, r.category, r.class_level, r.is_final) for r in tpl.runs}
    next_sort = max((r.sort_index for r in tpl.runs), default=0) + 1
    added = 0
    for discipline in _DISCIPLINES:
        for cat in _CATEGORIES:
            for kl in _CLASSES:
                key = (discipline, cat, kl, False)
                if key not in existing:
                    db.session.add(EventTemplateRun(
                        template_id=tpl.id, run_type=discipline,
                        category=cat, class_level=kl, is_final=False,
                        sort_index=next_sort))
                    next_sort += 1
                    added += 1
    db.session.commit()
    flash(f"{added} Standard-Läufe erzeugt.", "success")
    return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))


@templates_admin_bp.post("/admin/templates/<int:tpl_id>/runs/<int:run_id>/delete")
@_require_admin_key
def template_run_delete(tpl_id, run_id):
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    run = db.session.get(EventTemplateRun, run_id)
    if run and run.template_id == tpl.id:
        db.session.delete(run)
        db.session.commit()
        flash("Lauf entfernt.", "success")
    return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))


# ── Turnier aus Vorlage erzeugen ────────────────────────────────────────────────

@templates_admin_bp.route("/admin/templates/<int:tpl_id>/create-event", methods=["GET", "POST"])
@_require_admin_key
def template_create_event(tpl_id):
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)

    if request.method == "POST":
        event, messages = create_event_from_template(tpl, request.form)
        for text, category in messages:
            flash(text, category)
        if event is None:
            return render_template("admin/templates/create_event.html", tpl=tpl,
                                   day_range=range(1, tpl.day_count + 1),
                                   admin_key=_admin_key())
        return redirect(url_for("club.event_detail", event_id=event.id))

    return render_template("admin/templates/create_event.html", tpl=tpl,
                           day_range=range(1, tpl.day_count + 1),
                           admin_key=_admin_key())
