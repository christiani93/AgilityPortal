"""
Lizenzcheck — TKAMO-Workflow.

Ablauf:
  1. GET  /events/<id>/lizenzcheck/csv        → CSV aus Anmeldungen (→ an TKAMO)
  2. POST /events/<id>/lizenzcheck            → TKAMO-Antworttext einfügen & verarbeiten
  3. GET  /lizenzcheck/confirm/<token>        → Teilnehmer bestätigt Klasse per Link (öffentlich)

Automatische Aktionen beim Einfügen des TKAMO-Texts:
  - Hundename abweichend  → direkt in DB übernehmen
  - Falsche Klasse        → Mail mit zwei Bestätigungs-Links an Teilnehmer
  - Inaktive Lizenz       → wird im Bericht rot markiert (kein Start erlaubt)
"""

import csv
import io
import re
import time
from datetime import datetime

from flask import abort, current_app, render_template, request, Response, url_for
from flask_login import login_required
from flask_mail import Message
from itsdangerous import URLSafeSerializer, BadSignature

from app.extensions import db, mail
from app.models import Dog, Event, LicenseKind, Registration, RegistrationStatus, User
from .routes import club_bp, _assert_event_access

# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

_CAT_LABEL = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}
_CAT_FROM_CODE = {"L": "L", "I": "I", "M": "M", "S": "S"}


def _get_serializer() -> URLSafeSerializer:
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="lizenzcheck-confirm")


def _make_confirm_token(event_id: int, dog_id: int, cat: str, cls: int) -> str:
    return _get_serializer().dumps(
        {"event_id": event_id, "dog_id": dog_id, "cat": cat, "cls": cls}
    )


def _decode_confirm_token(token: str) -> dict | None:
    try:
        return _get_serializer().loads(token)
    except BadSignature:
        return None


# ── 1. CSV-Export für TKAMO ──────────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/lizenzcheck/csv")
@login_required
def event_lizenzcheck_csv(event_id):
    """Exportiert Anmeldungen als CSV im TKAMO-Format (nur CH-Lizenzen)."""
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
        if dog.license_kind == LicenseKind.FOREIGN:
            continue

        user = db.session.execute(
            db.select(User).filter_by(person_id=handler.id)
        ).scalar_one_or_none()
        vereinsnummer = (user.club.vereinsnummer if user and user.club else "") or ""

        cat_csv = _CAT_LABEL.get(
            reg.category_code[:1].upper() if reg.category_code else "", reg.category_code or ""
        )
        writer.writerow([
            dog.license_no or "",
            cat_csv,
            reg.class_level or "",
            dog.name or "",
            vereinsnummer,
            handler.first_name or "",
            handler.last_name or "",
            handler.email or "",
        ])

    return Response(
        output.getvalue().encode("utf-8"),
        content_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="lizenzcheck_{event_id}.csv"'},
    )


# ── 2. TKAMO-Antwort verarbeiten ─────────────────────────────────────────────

def _parse_and_apply_tkamo(event, report_text: str) -> tuple[list, list, list]:
    """
    Parst TKAMO-Text und führt automatische Aktionen aus.

    Rückgabe: (name_changes, class_emails, inactive_licenses)
      name_changes   : Liste von Strings (was geändert wurde)
      class_emails   : Liste von Strings (wer angeschrieben wurde)
      inactive_licenses: Liste von Strings (inaktive Lizenzen → nicht startberechtigt)
    """
    event_id = event.id

    # Zeilennummer → Lizenznummer aufbauen (gleiche Reihenfolge wie CSV-Export)
    regs = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id)
        .filter(Registration.status.in_([
            RegistrationStatus.PENDING,
            RegistrationStatus.CONFIRMED,
            RegistrationStatus.SUBMITTED,
        ]))
        .order_by(Registration.category_code, Registration.class_level)
    ).scalars().all()

    # Nur CH-Lizenzen zählen — identische Reihenfolge wie CSV-Export
    # (FOREIGN werden im CSV übersprungen, dürfen hier nicht mitzählen)
    row_to_license: dict[int, str] = {}
    row_num = 2  # Zeile 1 = Header
    for reg in regs:
        if reg.dog and reg.dog.license_kind != LicenseKind.FOREIGN:
            row_to_license[row_num] = reg.dog.license_no
            row_num += 1

    # Reply-To = Vereins-E-Mail des Veranstalters
    reply_to = None
    if event.organiser_club and event.organiser_club.email:
        reply_to = event.organiser_club.email

    name_changes:    list[str] = []
    class_emails:    list[str] = []
    inactive_licenses: list[str] = []

    for line in report_text.splitlines():
        line = line.strip()
        if not line:
            continue

        # ── "Verein stimmt nicht überein" → ignorieren (keine Aktion) ────────
        if re.search(r'Verein stimmt', line, re.IGNORECASE):
            continue

        # ── Warnung (z.B. Oldie) → als Info in class_emails ──────────────────
        if line.lower().startswith('warnung'):
            class_emails.append(f"ℹ️ {line}")
            continue

        # ── Inaktive Lizenz ───────────────────────────────────────────────────
        if re.search(r'inaktiv|nicht aktiv|gesperrt|inactif|inactive', line, re.IGNORECASE):
            m_lic = re.search(r'Lizenz\s+(\S+)', line, re.IGNORECASE)
            license_no = m_lic.group(1).rstrip('.,') if m_lic else "?"
            inactive_licenses.append(f"⛔ Inaktive Lizenz {license_no} — nicht startberechtigt!")
            continue

        # ── Falsche Klasse → Mail mit Bestätigungs-Links ─────────────────────
        if 'Klasse im System' in line:
            m_cls = re.search(
                r'Lizenz\s+(\S+).*?Klasse im System:\s*([SMIL])(\d)',
                line, re.IGNORECASE
            )
        else:
            m_cls = None
        if m_cls and 'Klasse im System' in line:
            license_no  = m_cls.group(1).rstrip('.')
            sys_cat_raw = m_cls.group(2).upper()
            sys_cls     = int(m_cls.group(3))
            sys_cat     = _CAT_FROM_CODE.get(sys_cat_raw, sys_cat_raw)

            # Import-Klasse aus der Zeile lesen
            m_imp = re.search(r'Klasse im Import:\s*([SMIL])(\d)', line, re.IGNORECASE)
            if m_imp:
                imp_cat = _CAT_FROM_CODE.get(m_imp.group(1).upper(), m_imp.group(1).upper())
                imp_cls = int(m_imp.group(2))
            else:
                imp_cat, imp_cls = sys_cat, sys_cls

            dog = db.session.execute(
                db.select(Dog).filter_by(license_no=license_no)
            ).scalar_one_or_none()

            if not dog:
                class_emails.append(f"Lizenz {license_no} nicht im System — Mail nicht gesendet.")
                continue

            # Handler für dieses Event finden
            reg = db.session.execute(
                db.select(Registration).filter_by(event_id=event_id, dog_id=dog.id)
            ).scalar_one_or_none()

            handler_email = reg.handler.email if reg and reg.handler else None
            handler_name  = (
                f"{reg.handler.first_name} {reg.handler.last_name}".strip()
                if reg and reg.handler else license_no
            )

            # Tokens für beide Optionen
            token_import = _make_confirm_token(event_id, dog.id, imp_cat, imp_cls)
            token_system = _make_confirm_token(event_id, dog.id, sys_cat, sys_cls)

            # URLs — wir sind bereits im Request-Kontext, _external=True genügt
            url_import = url_for(
                "club.lizenzcheck_confirm", token=token_import, _external=True
            )
            url_system = url_for(
                "club.lizenzcheck_confirm", token=token_system, _external=True
            )

            if handler_email and current_app.config.get("MAIL_SERVER"):
                try:
                    html = render_template(
                        "email/class_confirm.html",
                        event=event,
                        handler_name=handler_name,
                        dog_name=dog.name,
                        license_no=license_no,
                        cat_import_label=_CAT_LABEL.get(imp_cat, imp_cat),
                        cls_import=imp_cls,
                        cat_system_label=_CAT_LABEL.get(sys_cat, sys_cat),
                        cls_system=sys_cls,
                        url_confirm_import=url_import,
                        url_confirm_system=url_system,
                    )
                    msg = Message(
                        subject=f"Klassen-Bestätigung / Confirmation de classe – {event.name}",
                        recipients=[handler_email],
                        html=html,
                        reply_to=reply_to,
                    )
                    mail.send(msg)
                    class_emails.append(
                        f"📧 Mail gesendet an {handler_email} — {dog.name} ({license_no}): "
                        f"{_CAT_LABEL.get(imp_cat, imp_cat)} Kl.{imp_cls} vs. "
                        f"{_CAT_LABEL.get(sys_cat, sys_cat)} Kl.{sys_cls}"
                    )
                    time.sleep(0.5)
                except Exception as exc:
                    class_emails.append(f"⚠️ Mail-Fehler {license_no}: {exc}")
            else:
                class_emails.append(
                    f"Keine Mail-Adresse für {license_no} — Klasse offen: "
                    f"{_CAT_LABEL.get(imp_cat, imp_cat)} Kl.{imp_cls} vs. "
                    f"{_CAT_LABEL.get(sys_cat, sys_cat)} Kl.{sys_cls}"
                )
            continue

        # ── Hundename → immer TKAMO-System-Namen übernehmen ─────────────────
        # Lizenz ist NIE in dieser Zeile — immer nur Zeile N
        if 'Hundename' in line:
            m_name = re.search(r'Im System\s+(.+)$', line, re.IGNORECASE)
            if not m_name:
                continue
            system_name = m_name.group(1).strip()

            license_no = None
            m_lic = re.search(r'Lizenz\s+(\S+)', line, re.IGNORECASE)
            if m_lic:
                license_no = m_lic.group(1).rstrip('.,')
            else:
                m_row = re.search(r'Zeile\s+(\d+)', line, re.IGNORECASE)
                if m_row:
                    license_no = row_to_license.get(int(m_row.group(1)))

            if license_no:
                dog = db.session.execute(
                    db.select(Dog).filter_by(license_no=license_no)
                ).scalar_one_or_none()
                if dog:
                    old_name = dog.name
                    dog.name = system_name  # immer übernehmen
                    if old_name != system_name:
                        name_changes.append(
                            f"✏️ Hundename: {license_no} '{old_name}' → '{system_name}'"
                        )
                    else:
                        name_changes.append(
                            f"✏️ Hundename: {license_no} '{system_name}' (Schreibweise bestätigt)"
                        )

    db.session.commit()
    return name_changes, class_emails, inactive_licenses


@club_bp.post("/events/<int:event_id>/lizenzcheck")
@login_required
def event_lizenzcheck(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    report_text = request.form.get("tkamo_result", "").strip()
    if not report_text:
        from flask import redirect, url_for, flash
        flash("Bitte TKAMO-Ergebnis einfügen.", "warning")
        return redirect(url_for("club.event_detail", event_id=event_id))

    name_changes, class_emails, inactive_licenses = _parse_and_apply_tkamo(event, report_text)

    event.lizenzcheck_done_at = datetime.utcnow()
    event.lizenzcheck_report  = report_text
    db.session.commit()

    return render_template(
        "club/lizenzcheck_result.html",
        event=event,
        report_text=report_text,
        name_changes=name_changes,
        class_emails=class_emails,
        inactive_licenses=inactive_licenses,
    )


# ── 3. Bestätigung durch Teilnehmer (öffentlich) ─────────────────────────────

@club_bp.get("/lizenzcheck/confirm/<token>")
def lizenzcheck_confirm(token):
    """
    Öffentliche Route — Teilnehmer klickt Link in der Mail.
    Token enthält event_id, dog_id, cat, cls.
    """
    data = _decode_confirm_token(token)
    if not data:
        abort(400)

    dog   = db.session.get(Dog, data["dog_id"])
    event = db.session.get(Event, data["event_id"])
    if not dog or not event:
        abort(404)

    new_cat = data["cat"]
    new_cls = data["cls"]

    # Dog aktualisieren
    dog.category    = new_cat
    dog.class_level = new_cls

    # Anmeldung aktualisieren
    regs = db.session.execute(
        db.select(Registration).filter_by(event_id=event.id, dog_id=dog.id)
    ).scalars().all()
    cat_full = _CAT_LABEL.get(new_cat, new_cat)
    for reg in regs:
        reg.class_level   = new_cls
        reg.category_code = cat_full

    db.session.commit()

    return render_template(
        "club/lizenzcheck_confirm.html",
        event=event,
        dog_name=dog.name,
        license_no=dog.license_no,
        cat_label=cat_full,
        cls=new_cls,
    )
