"""
Lizenzcheck — CSV-Upload gegen die Portal-Datenbank prüfen.

Route:
  POST /events/<event_id>/lizenzcheck

CSV-Format (Semikolon-getrennt, UTF-8 oder Latin-1):
  Lizenznummer;Kategorie;Klasse;Hundename;Vereinsnummer;Vorname;Nachname;E-Mail

Aktionen:
  - Hundename abweichend → direkt im DB übernehmen (kein Report-Eintrag)
  - Falsche Klasse/Kategorie → Report-Zeile + Frage-Mail an Teilnehmer
  - Verein-Diskrepanz → ignoriert
  - Lizenz nicht im System → Report-Zeile

Rückgabe: plain/text-Datei (Download) mit allen Abweichungen.
"""

import csv
import io
import time
from datetime import datetime

from flask import abort, current_app, render_template, request, Response
from flask_login import login_required
from flask_mail import Message

from app.extensions import db, mail
from app.models import Dog, Event
from .routes import club_bp, _assert_event_access

# Mapping CSV-Kategorie → DB-Kategorie (1 Buchstabe)
_CAT_MAP = {
    "large":        "L",
    "intermediate": "I",
    "medium":       "M",
    "small":        "S",
}
_CAT_LABEL = {v: k.capitalize() for k, v in _CAT_MAP.items()}


@club_bp.post("/events/<int:event_id>/lizenzcheck")
@login_required
def event_lizenzcheck(event_id):
    """
    Nimmt eine CSV-Datei entgegen, prüft jeden Eintrag gegen die DB
    und gibt einen Reintext-Bericht zurück.
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    uploaded = request.files.get("csv_file")
    if not uploaded or not uploaded.filename:
        abort(400, "Keine Datei hochgeladen.")

    # Datei lesen — UTF-8 mit Latin-1-Fallback (Schweizer Sonderzeichen)
    raw = uploaded.read()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    report_lines: list[str] = []
    emails_sent = 0
    row_count = 0

    # Reply-To = Vereins-E-Mail des Veranstalters
    reply_to = None
    if event.organiser_club and event.organiser_club.email:
        reply_to = event.organiser_club.email

    for row_idx, row in enumerate(reader, start=2):   # Zeile 2 = erster Datensatz
        row_count += 1
        license_no   = (row.get("Lizenznummer") or "").strip()
        cat_csv_raw  = (row.get("Kategorie")    or "").strip().lower()
        cls_csv_str  = (row.get("Klasse")       or "").strip()
        name_csv     = (row.get("Hundename")    or "").strip()
        vorname      = (row.get("Vorname")      or "").strip()
        nachname     = (row.get("Nachname")     or "").strip()
        email_csv    = (row.get("E-Mail")       or "").strip()

        if not license_no:
            continue

        # Kategorie + Klasse aus CSV normalisieren
        cat_csv = _CAT_MAP.get(cat_csv_raw, cat_csv_raw.upper()[:1])
        try:
            cls_csv = int(cls_csv_str)
        except ValueError:
            cls_csv = None

        # Hund in DB suchen
        dog = db.session.execute(
            db.select(Dog).filter_by(license_no=license_no)
        ).scalar_one_or_none()

        if dog is None:
            report_lines.append(
                f"Lizenz {license_no} ({name_csv}) auf Zeile {row_idx} nicht im System gefunden."
            )
            continue

        changed = False

        # ── 1. Hundename: direkt übernehmen wenn abweichend ─────────────────
        if name_csv and name_csv.lower() != (dog.name or "").lower():
            report_lines.append(
                f"Hundename aktualisiert auf Zeile {row_idx}, Lizenz {license_no}: "
                f"'{dog.name}' → '{name_csv}'"
            )
            dog.name = name_csv
            changed = True

        # ── 2. Klasse / Kategorie prüfen ─────────────────────────────────────
        cat_mismatch = cat_csv and dog.category and cat_csv != dog.category
        cls_mismatch = cls_csv is not None and dog.class_level is not None and cls_csv != dog.class_level

        if cat_mismatch or cls_mismatch:
            cat_import_label = _CAT_LABEL.get(cat_csv, cat_csv)
            cat_system_label = _CAT_LABEL.get(dog.category, dog.category or "?")
            cls_import = cls_csv or "?"
            cls_system = dog.class_level or "?"

            report_lines.append(
                f"Falsche Klasse oder Kategorie auf Zeile {row_idx}, "
                f"Lizenz {license_no} {dog.name}. "
                f"Klasse im Import: {cat_csv}{cls_import}. "
                f"Klasse im System: {dog.category}{cls_system}"
            )

            # Frage-Mail senden
            if email_csv and current_app.config.get("MAIL_SERVER"):
                try:
                    handler_name = f"{vorname} {nachname}".strip() or email_csv
                    html_body = render_template(
                        "email/class_question.html",
                        event=event,
                        handler_name=handler_name,
                        dog_name=dog.name,
                        license_no=license_no,
                        cat_import=cat_import_label,
                        cls_import=cls_import,
                        cat_system=cat_system_label,
                        cls_system=cls_system,
                    )
                    msg = Message(
                        subject=f"Klassen-Diskrepanz / Divergence de classe – {event.name}",
                        recipients=[email_csv],
                        html=html_body,
                        reply_to=reply_to,
                    )
                    mail.send(msg)
                    emails_sent += 1
                    # Kurze Pause zwischen Mails
                    time.sleep(0.5)
                except Exception as exc:
                    current_app.logger.warning(
                        "Klassen-Frage-Mail fehlgeschlagen an %s: %s", email_csv, exc
                    )

        if changed:
            db.session.flush()

    # Lizenzcheck als durchgeführt markieren
    event.lizenzcheck_done_at = datetime.utcnow()
    db.session.commit()

    # Bericht zusammenstellen
    if report_lines:
        report_text = "\n".join(report_lines)
    else:
        report_text = "Kein Fehler gefunden. Alle Einträge stimmen überein."

    if emails_sent:
        report_text += f"\n\n{emails_sent} Klassen-Frage-Mail(s) versendet."

    return render_template(
        "club/lizenzcheck_result.html",
        event=event,
        report_text=report_text,
        emails_sent=emails_sent,
        row_count=row_count,
    )
