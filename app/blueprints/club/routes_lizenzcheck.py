"""
Lizenzcheck — TKAMO-Workflow.

Ablauf:
  1. GET  /events/<id>/lizenzcheck/csv   → CSV aus Anmeldungen exportieren (→ an TKAMO)
  2. POST /events/<id>/lizenzcheck       → TKAMO-Antworttext hochladen & anzeigen

Routes sind auf club_bp registriert (via __init__.py).
"""

import csv
import io
from datetime import datetime

from flask import abort, render_template, request, Response
from flask_login import login_required

from app.extensions import db
from app.models import Event, LicenseKind, Registration, RegistrationStatus, User
from .routes import club_bp, _assert_event_access

# Mapping DB-Kategorie (1 Buchstabe) → Klartext für TKAMO-CSV
_CAT_LABEL = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}


# ── 1. CSV-Export für TKAMO ──────────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/lizenzcheck/csv")
@login_required
def event_lizenzcheck_csv(event_id):
    """
    Exportiert alle bestätigten/ausstehenden Anmeldungen als CSV
    im TKAMO-Format (Lizenznummer;Kategorie;Klasse;Hundename;Vereinsnummer;Vorname;Nachname;E-Mail).
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    registrations = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id)
        .filter(Registration.status.in_([
            RegistrationStatus.PENDING,
            RegistrationStatus.CONFIRMED,
            RegistrationStatus.SUBMITTED,
        ]))
        .order_by(Registration.category_code, Registration.class_level)
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Lizenznummer", "Kategorie", "Klasse", "Hundename",
                     "Vereinsnummer", "Vorname", "Nachname", "E-Mail"])

    for reg in registrations:
        dog     = reg.dog
        handler = reg.handler
        if not dog or not handler:
            continue

        # Ausländische Lizenzen überspringen (TKAMO prüft nur Schweizer Lizenzen)
        if dog.license_kind == LicenseKind.FOREIGN:
            continue

        # Vereinsnummer des Führers ermitteln (über User → Club)
        user = db.session.execute(
            db.select(User).filter_by(person_id=handler.id)
        ).scalar_one_or_none()
        vereinsnummer = ""
        if user and user.club:
            vereinsnummer = user.club.vereinsnummer or ""

        # Kategorie: DB-Kürzel → Klartext
        cat_csv  = _CAT_LABEL.get(reg.category_code[:1].upper() if reg.category_code else "",
                                   reg.category_code or "")
        cls_csv  = reg.class_level or ""

        writer.writerow([
            dog.license_no or "",
            cat_csv,
            cls_csv,
            dog.name or "",
            vereinsnummer,
            handler.first_name or "",
            handler.last_name or "",
            handler.email or "",
        ])

    csv_bytes = output.getvalue().encode("utf-8")   # kein BOM — TKAMO verträgt keinen BOM

    return Response(
        csv_bytes,
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="lizenzcheck_{event_id}.csv"'
        },
    )


# ── 2. TKAMO-Antwort hochladen ───────────────────────────────────────────────

@club_bp.post("/events/<int:event_id>/lizenzcheck")
@login_required
def event_lizenzcheck(event_id):
    """
    Nimmt den TKAMO-Antworttext (aus Textarea) entgegen und zeigt ihn an.
    Markiert den Lizenzcheck als durchgeführt.
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    report_text = request.form.get("tkamo_result", "").strip()
    if not report_text:
        from flask import redirect, url_for, flash
        flash("Bitte TKAMO-Ergebnis einfügen.", "warning")
        return redirect(url_for("club.event_detail", event_id=event_id))

    # Lizenzcheck als erledigt markieren
    event.lizenzcheck_done_at = datetime.utcnow()
    db.session.commit()

    return render_template(
        "club/lizenzcheck_result.html",
        event=event,
        report_text=report_text,
    )
