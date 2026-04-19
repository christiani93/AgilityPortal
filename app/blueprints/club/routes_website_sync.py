"""
TKAMO-Import, Website-Sync und Reservationsanfrage für einzelne Events.

Routen:
  POST /club/events/<id>/tkamo-import        → TKAMO-Daten laden + anwenden
  POST /club/events/<id>/website-sync        → body_md generieren + AdminPortal API
  POST /club/events/<id>/description-save    → Freitext-Beschreibung speichern
  POST /club/events/<id>/reservation-request → Neue Reservationsanfrage erstellen
  POST /club/events/<id>/reservation-sync    → Bestehende Reservation aktualisieren
"""

from flask import redirect, url_for, flash, request
from flask_login import login_required, current_user

from app.blueprints.club.routes import club_bp
from app.extensions import db
from app.models import Event


# ── TKAMO-Import ───────────────────────────────────────────────────────────────

@club_bp.route("/events/<int:event_id>/tkamo-import", methods=["POST"])
@login_required
def event_tkamo_import(event_id):
    event = db.get_or_404(Event, event_id)

    # Nur Superadmin oder eigener Verein
    if not (current_user.is_superadmin or
            (current_user.club_id and current_user.club_id == event.organiser_club_id)):
        flash("Keine Berechtigung.", "danger")
        return redirect(url_for("club.event_detail", event_id=event_id))

    ais = event.ais_turniernummer
    if not ais:
        flash("Keine AIS-Nummer am Turnier hinterlegt.", "warning")
        return redirect(url_for("club.event_detail", event_id=event_id))

    try:
        from app.services.tkamo_importer import fetch_tkamo_event, apply_to_event
        data = fetch_tkamo_event(ais)
        changes = apply_to_event(event, data)
        db.session.commit()
        if changes:
            flash(f"TKAMO-Import erfolgreich: {', '.join(changes)}", "success")
        else:
            flash("TKAMO-Import: Keine neuen Daten gefunden.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"TKAMO-Import fehlgeschlagen: {e}", "danger")

    return redirect(url_for("club.event_detail", event_id=event_id))


# ── Freitext-Beschreibung speichern ───────────────────────────────────────────

@club_bp.route("/events/<int:event_id>/description-save", methods=["POST"])
@login_required
def event_description_save(event_id):
    event = db.get_or_404(Event, event_id)

    if not (current_user.is_superadmin or
            (current_user.club_id and current_user.club_id == event.organiser_club_id)):
        flash("Keine Berechtigung.", "danger")
        return redirect(url_for("club.event_detail", event_id=event_id))

    event.event_description_de = request.form.get("event_description_de", "").strip() or None
    db.session.commit()
    flash("Beschreibung gespeichert.", "success")
    return redirect(url_for("club.event_detail", event_id=event_id))


# ── Website-Sync ──────────────────────────────────────────────────────────────

@club_bp.route("/events/<int:event_id>/website-sync", methods=["POST"])
@login_required
def event_website_sync(event_id):
    event = db.get_or_404(Event, event_id)

    if not (current_user.is_superadmin or
            (current_user.club_id and current_user.club_id == event.organiser_club_id)):
        flash("Keine Berechtigung.", "danger")
        return redirect(url_for("club.event_detail", event_id=event_id))

    try:
        from app.services.website_sync import sync_to_website
        ok, err = sync_to_website(event)
        if ok:
            db.session.commit()
            flash("Webseite erfolgreich synchronisiert.", "success")
        else:
            flash(f"Synchronisation fehlgeschlagen: {err}", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler beim Synchronisieren: {e}", "danger")

    return redirect(url_for("club.event_detail", event_id=event_id))


# ── Reservationsanfrage erstellen ────────────────────────────────────────────

@club_bp.route("/events/<int:event_id>/reservation-request", methods=["POST"])
@login_required
def event_reservation_request(event_id):
    event = db.get_or_404(Event, event_id)

    if not (current_user.is_superadmin or
            (current_user.club_id and current_user.club_id == event.organiser_club_id)):
        flash("Keine Berechtigung.", "danger")
        return redirect(url_for("club.event_detail", event_id=event_id))

    if event.reservation_id:
        flash("Es besteht bereits eine Reservationsanfrage. Verwende 'Daten aktualisieren'.", "warning")
        return redirect(url_for("club.event_detail", event_id=event_id))

    contact_name  = request.form.get("contact_name", "").strip()
    contact_email = request.form.get("contact_email", "").strip()
    contact_phone = request.form.get("contact_phone", "").strip()
    club          = request.form.get("club", "").strip()
    notes         = request.form.get("notes", "").strip()
    option_special_eval  = bool(request.form.get("option_special_eval"))
    option_website       = bool(request.form.get("option_website"))
    option_event_support = bool(request.form.get("option_event_support"))

    if not contact_name or not contact_email:
        flash("Name und E-Mail des Ansprechpartners sind Pflichtfelder.", "warning")
        return redirect(url_for("club.event_detail", event_id=event_id))

    try:
        from app.services.reservation_sync import create_reservation
        ok, err = create_reservation(
            event, contact_name, contact_email, contact_phone, club, notes,
            option_special_eval, option_website, option_event_support,
        )
        if ok:
            db.session.commit()
            flash("Reservationsanfrage erfolgreich gesendet.", "success")
        else:
            flash(f"Anfrage fehlgeschlagen: {err}", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler: {e}", "danger")

    return redirect(url_for("club.event_detail", event_id=event_id))


# ── Reservation mit aktuellen Event-Daten aktualisieren ──────────────────────

@club_bp.route("/events/<int:event_id>/reservation-sync", methods=["POST"])
@login_required
def event_reservation_sync(event_id):
    event = db.get_or_404(Event, event_id)

    if not (current_user.is_superadmin or
            (current_user.club_id and current_user.club_id == event.organiser_club_id)):
        flash("Keine Berechtigung.", "danger")
        return redirect(url_for("club.event_detail", event_id=event_id))

    try:
        from app.services.reservation_sync import update_reservation
        ok, err = update_reservation(event)
        if ok:
            db.session.commit()
            flash("Reservationsdaten erfolgreich aktualisiert.", "success")
        else:
            flash(f"Aktualisierung fehlgeschlagen: {err}", "danger")
    except Exception as e:
        db.session.rollback()
        flash(f"Fehler: {e}", "danger")

    return redirect(url_for("club.event_detail", event_id=event_id))
