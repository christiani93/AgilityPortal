"""
Admin-Routen für Turnier-Vorlagen (jährlich wiederkehrende Veranstaltungen).

Eine Vorlage speichert die stabilen Felder (Name, Typ/Ruleset, Veranstalter,
Läufe, Config). Beim Erzeugen eines konkreten Turniers werden nur die jährlich
wechselnden Felder abgefragt (Daten + AIS-Nummer(n)).

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie die übrigen Admin-Routen).
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

from flask import (Blueprint, abort, flash, redirect, render_template, request,
                   url_for, current_app)
from flask_login import current_user

from app.extensions import db
from app.models import (Club, Event, EventRun, EventTemplate, EventTemplateRun)


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
            db.session.add(EventTemplateRun(
                template_id=tpl.id, run_type=run_type, category=category,
                class_level=class_level, is_final=is_final))
            db.session.commit()
            flash("Lauf hinzugefügt.", "success")
        else:
            flash("Dieser Lauf existiert bereits.", "warning")
    return redirect(url_for("templates_admin.template_edit", tpl_id=tpl.id, key=_admin_key()))


@templates_admin_bp.post("/admin/templates/<int:tpl_id>/runs/generate")
@_require_admin_key
def template_runs_generate(tpl_id):
    """Standard-Läufe erzeugen: Agility + Jumping, alle Kategorien, Klassen 1-3."""
    tpl = db.session.get(EventTemplate, tpl_id)
    if not tpl:
        abort(404)
    existing = {(r.run_type, r.category, r.class_level, r.is_final) for r in tpl.runs}
    added = 0
    for discipline in _DISCIPLINES:
        for cat in _CATEGORIES:
            for kl in _CLASSES:
                key = (discipline, cat, kl, False)
                if key not in existing:
                    db.session.add(EventTemplateRun(
                        template_id=tpl.id, run_type=discipline,
                        category=cat, class_level=kl, is_final=False))
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
        name = (request.form.get("name") or tpl.default_event_name or tpl.name).strip()
        starts_raw = request.form.get("starts_at")
        ends_raw = request.form.get("ends_at")
        try:
            starts_at = datetime.strptime(starts_raw, "%Y-%m-%d") if starts_raw else None
        except ValueError:
            starts_at = None
        try:
            ends_at = datetime.strptime(ends_raw, "%Y-%m-%d") if ends_raw else None
        except ValueError:
            ends_at = None

        if not starts_at:
            flash("Startdatum ist erforderlich.", "danger")
            return render_template("admin/templates/create_event.html", tpl=tpl,
                                   day_range=range(1, tpl.day_count + 1),
                                   admin_key=_admin_key())

        # AIS-Nummern: Feld ais_1 = Haupttag, ais_2.. = Folgetage (kommagetrennt)
        ais_values = []
        for i in range(1, tpl.day_count + 1):
            v = (request.form.get(f"ais_{i}") or "").strip()
            if v:
                ais_values.append(v)
        ais_haupt = _parse_int(ais_values[0]) if ais_values else None
        ais_extra = ",".join(ais_values[1:]) if len(ais_values) > 1 else None

        event = Event(
            name=name,
            location=tpl.location,
            starts_at=starts_at,
            ends_at=ends_at or starts_at,
            type=tpl.type,
            special_ruleset=tpl.special_ruleset,
            status="draft",
            organiser_club_id=tpl.organiser_club_id,
            pruefungsleiter=tpl.pruefungsleiter,
            entry_fee=tpl.entry_fee,
            max_participants=tpl.max_participants,
            allows_bitches_in_season=tpl.allows_bitches_in_season,
            bitches_in_season_start_last=tpl.bitches_in_season_start_last,
            ring_count=tpl.ring_count,
            notes_public=tpl.notes_public,
            event_description_de=tpl.event_description_de,
            startnumber_schema=tpl.startnumber_schema,
            run_time_config=tpl.run_time_config,
            ring_start_times=tpl.ring_start_times,
            ais_turniernummer=ais_haupt,
            ais_turniernummer_extra=ais_extra,
        )
        db.session.add(event)
        db.session.flush()

        for r in tpl.runs:
            db.session.add(EventRun(
                event_id=event.id, run_type=r.run_type, category=r.category,
                class_level=r.class_level, is_final=r.is_final))

        db.session.commit()
        flash(f"Turnier «{event.name}» aus Vorlage erstellt (Status: Entwurf).", "success")

        # Optionale Sync-Verknüpfungen direkt anstoßen
        if request.form.get("do_website"):
            try:
                from app.services.website_sync import sync_to_website
                ok, err = sync_to_website(event)
                if ok:
                    db.session.commit()
                    flash("Webseiten-Event erstellt.", "success")
                else:
                    flash(f"Webseiten-Sync übersprungen: {err}", "warning")
            except Exception as e:
                db.session.rollback()
                flash(f"Webseiten-Sync fehlgeschlagen: {e}", "warning")

        if request.form.get("do_reservation"):
            contact_name = (request.form.get("contact_name") or tpl.contact_name or "").strip()
            contact_email = (request.form.get("contact_email") or tpl.contact_email or "").strip()
            if not contact_name or not contact_email:
                flash("Reservationsanfrage übersprungen: Kontakt-Name und E-Mail fehlen.", "warning")
            else:
                try:
                    from app.services.reservation_sync import create_reservation
                    ok, err = create_reservation(
                        event, contact_name, contact_email,
                        (request.form.get("contact_phone") or tpl.contact_phone or "").strip(),
                        tpl.organiser_club.name if tpl.organiser_club else "",
                        tpl.reservation_notes or "",
                        tpl.option_special_eval, tpl.option_website, tpl.option_event_support,
                    )
                    if ok:
                        db.session.commit()
                        flash("Reservationsanfrage gesendet.", "success")
                    else:
                        flash(f"Reservationsanfrage übersprungen: {err}", "warning")
                except Exception as e:
                    db.session.rollback()
                    flash(f"Reservationsanfrage fehlgeschlagen: {e}", "warning")

        return redirect(url_for("club.event_detail", event_id=event.id))

    return render_template("admin/templates/create_event.html", tpl=tpl,
                           day_range=range(1, tpl.day_count + 1),
                           admin_key=_admin_key())
