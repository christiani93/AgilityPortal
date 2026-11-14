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
from flask_babel import _
from flask_login import login_required, current_user
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


def _make_confirm_token(event_id: int | list[int], dog_id: int, cat: str, cls: int) -> str:
    """
    Erzeugt einen Bestätigungs-Token.
    event_id kann ein einzelnes Event (int) oder eine Liste von Events (list[int]) sein.
    Backward-compatible: single event_id wird als 'event_id' gespeichert.
    """
    if isinstance(event_id, list):
        data = {"event_ids": event_id, "dog_id": dog_id, "cat": cat, "cls": cls}
    else:
        data = {"event_id": event_id, "dog_id": dog_id, "cat": cat, "cls": cls}
    return _get_serializer().dumps(data)


def _decode_confirm_token(token: str) -> dict | None:
    try:
        return _get_serializer().loads(token)
    except BadSignature:
        return None


# ── 0. Lizenzcheck-Auswahl (Multi-Event) ─────────────────────────────────────

@club_bp.get("/lizenzcheck")
@login_required
def club_lizenzcheck_select():
	"""
	Seite zur Auswahl von Events für Wochenend-Lizenzcheck.
	Zeigt Events mit Checkboxen für Multi-Event-Bundle.
	"""
	if not current_user.can_manage_club:
		abort(403)

	# Nur offene Events (nach Datum sortiert)
	events = db.session.execute(
		db.select(Event)
		.filter_by(status='open')
		.order_by(Event.starts_at.asc())
	).scalars().all()

	return render_template(
		"club/lizenzcheck_select.html",
		events=events,
	)


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
        .order_by(Registration.category_code, Registration.class_level, Registration.id)
    ).scalars().all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    writer.writerow(["Lizenznummer", "Kategorie", "Klasse", "Hundename",
                     "Vereinsnummer", "Vorname", "Nachname", "HF-Mail"])

    for reg in registrations:
        dog     = reg.dog
        handler = reg.handler
        if not dog or not handler:
            continue
        if dog.license_kind == LicenseKind.FOREIGN:
            continue

        # Vereinsnummer: primär aus dem AOA/SportyDog-Import (reg.club_name,
        # befüllt mit der dortigen "Vereinsnummer"-Spalte) — die meisten
        # Teilnehmer sind Gäste ohne Portal-Login und haben keinen User-Account.
        # Fallback: eigene Portal-Mitglieder über User → Club.
        vereinsnummer = (reg.club_name or "").strip()
        if not vereinsnummer:
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
            dog.tka_name or dog.name or "",
            vereinsnummer,
            handler.first_name or "",
            handler.last_name or "",
            handler.email or "",
        ])

    # TKAMO liest die Datei als Windows-1252 (nicht UTF-8) ein — bei UTF-8-Encoding
    # entstehen Mojibake-Artefakte bei Umlauten/Akzenten (z.B. "Taïgan" → "TaÃ¯gan").
    # errors="replace" verhindert einen Crash bei Zeichen ausserhalb von cp1252
    # (z.B. seltene Sonderzeichen in Hundenamen).
    return Response(
        output.getvalue().encode("cp1252", errors="replace"),
        content_type="text/csv; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="lizenzcheck_{event_id}.csv"'},
    )


# ── 1b. Multi-Event CSV-Export (Wochenend-Bundle) ────────────────────────────

@club_bp.get("/lizenzcheck-multi/csv")
@login_required
def club_lizenzcheck_multi_csv():
    """
    Exportiert Anmeldungen aus mehreren Events als kombiniertes CSV.
    Input: ?events=34,35 (komma-separierte Event-IDs)
    Output: CSV mit zusätzlicher Spalte "Event"
    """
    events_param = request.args.get("events", "").strip()
    if not events_param:
        abort(400)

    try:
        event_ids = [int(x.strip()) for x in events_param.split(",")]
    except ValueError:
        abort(400)

    if not event_ids:
        abort(400)

    # Access-Check: aktueller User muss auf alle Events Zugriff haben
    events = []
    for event_id in event_ids:
        event = db.session.get(Event, event_id)
        if not event:
            abort(404)
        _assert_event_access(event)
        events.append(event)

    # Registrierungen aus allen Events sammeln
    all_regs = []
    for event_id in event_ids:
        regs = db.session.execute(
            db.select(Registration)
            .filter_by(event_id=event_id)
            .filter(Registration.status.in_([
                RegistrationStatus.PENDING,
                RegistrationStatus.CONFIRMED,
                RegistrationStatus.SUBMITTED,
            ]))
            .order_by(Registration.category_code, Registration.class_level, Registration.id)
        ).scalars().all()
        for reg in regs:
            all_regs.append((event_id, reg))

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";", lineterminator="\r\n")
    # Header + "Event"-Spalte
    writer.writerow(["Event", "Lizenznummer", "Kategorie", "Klasse", "Hundename",
                     "Vereinsnummer", "Vorname", "Nachname", "HF-Mail"])

    for event_id, reg in all_regs:
        dog     = reg.dog
        handler = reg.handler
        if not dog or not handler:
            continue
        if dog.license_kind == LicenseKind.FOREIGN:
            continue

        # Event-Name oder Datum
        event = db.session.get(Event, event_id)
        event_label = event.name if event else f"Event {event_id}"

        # Vereinsnummer (wie im Single-Event-Export)
        vereinsnummer = (reg.club_name or "").strip()
        if not vereinsnummer:
            user = db.session.execute(
                db.select(User).filter_by(person_id=handler.id)
            ).scalar_one_or_none()
            vereinsnummer = (user.club.vereinsnummer if user and user.club else "") or ""

        cat_csv = _CAT_LABEL.get(
            reg.category_code[:1].upper() if reg.category_code else "", reg.category_code or ""
        )
        writer.writerow([
            event_label,
            dog.license_no or "",
            cat_csv,
            reg.class_level or "",
            dog.tka_name or dog.name or "",
            vereinsnummer,
            handler.first_name or "",
            handler.last_name or "",
            handler.email or "",
        ])

    return Response(
        output.getvalue().encode("cp1252", errors="replace"),
        content_type="text/csv; charset=windows-1252",
        headers={"Content-Disposition": f'attachment; filename="lizenzcheck_multi_{len(event_ids)}_events.csv"'},
    )


# ── 2. TKAMO-Antwort verarbeiten ─────────────────────────────────────────────

def _parse_and_apply_tkamo_multi(events: list, report_text: str) -> tuple[list, list, list]:
	"""
	Parst TKAMO-Text für mehrere Events zusammen.
	Ähnlich wie Single-Event, aber verarbeitet Anmeldungen aus allen Events.

	Rückgabe: (name_changes, class_emails, inactive_licenses)
	"""
	event_ids = [e.id for e in events]

	# Zeilennummer → (license_no, event_id) aufbauen
	# Events in der gleichen Reihenfolge wie im TKAMO-Export (Sortierung!)
	regs_by_event = {}
	for event_id in event_ids:
		regs = db.session.execute(
			db.select(Registration)
			.filter_by(event_id=event_id)
			.filter(Registration.status.in_([
				RegistrationStatus.PENDING,
				RegistrationStatus.CONFIRMED,
				RegistrationStatus.SUBMITTED,
			]))
			.order_by(Registration.category_code, Registration.class_level, Registration.id)
		).scalars().all()
		regs_by_event[event_id] = regs

	# Row-Mapping
	row_to_license_event: dict[int, tuple[str, int]] = {}
	row_num = 2  # Header
	for event_id in event_ids:
		for reg in regs_by_event[event_id]:
			if reg.dog and reg.dog.license_kind != LicenseKind.FOREIGN:
				row_to_license_event[row_num] = (reg.dog.license_no, event_id)
				row_num += 1

	# Reply-To vom ersten Event
	reply_to = None
	if events[0].organiser_club and events[0].organiser_club.email:
		reply_to = events[0].organiser_club.email

	name_changes: list[str] = []
	class_emails: list[str] = []
	inactive_licenses: list[str] = []

	for line in report_text.splitlines():
		line = line.strip()
		if not line:
			continue

		if re.search(r'nicht mit Hundeführer überein', line, re.IGNORECASE):
			continue

		if line.lower().startswith('warnung'):
			class_emails.append(f"ℹ️ {line}")
			continue

		if re.search(r'inaktiv|nicht aktiv|gesperrt|inactif|inactive', line, re.IGNORECASE):
			m_lic = re.search(r'Lizenz\s+(\S+)', line, re.IGNORECASE)
			license_no = m_lic.group(1).rstrip('.,') if m_lic else "?"
			inactive_licenses.append(f"⛔ Inaktive Lizenz {license_no} — nicht startberechtigt!")
			continue

		# Falsche Klasse → Multi-Event-Token generieren
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

			# Alle Events mit diesem Dog sammeln
			event_ids_for_dog = []
			for event_id in event_ids:
				reg = db.session.execute(
					db.select(Registration).filter_by(event_id=event_id, dog_id=dog.id)
				).scalar_one_or_none()
				if reg:
					event_ids_for_dog.append(event_id)

			if not event_ids_for_dog:
				class_emails.append(f"Lizenz {license_no} in keinem Event — Mail nicht gesendet.")
				continue

			# Handler aus einer beliebigen Registration
			reg = db.session.execute(
				db.select(Registration).filter_by(dog_id=dog.id).filter(Registration.event_id.in_(event_ids_for_dog))
			).scalars().first()

			handler_email = reg.handler.email if reg and reg.handler else None
			handler_name  = (
				f"{reg.handler.first_name} {reg.handler.last_name}".strip()
				if reg and reg.handler else license_no
			)

			# Multi-Event-Token
			token_import = _make_confirm_token(event_ids_for_dog, dog.id, imp_cat, imp_cls)
			token_system = _make_confirm_token(event_ids_for_dog, dog.id, sys_cat, sys_cls)

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
						event=events[0],  # Primary event
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
						subject=f"Klassen-Bestätigung / Confirmation de classe – Wochenende",
						recipients=[handler_email],
						html=html,
						reply_to=reply_to,
					)
					mail.send(msg)
					event_count = len(event_ids_for_dog)
					class_emails.append(
						f"📧 Mail gesendet an {handler_email} — {dog.name} ({license_no}): "
						f"{_CAT_LABEL.get(imp_cat, imp_cat)} Kl.{imp_cls} vs. "
						f"{_CAT_LABEL.get(sys_cat, sys_cat)} Kl.{sys_cls} ({event_count} Events)"
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

		# Hundename
		if 'Hundename' in line:
			m_name = re.search(r'Im System\s+(.+)$', line, re.IGNORECASE)
			if not m_name:
				continue
			system_name = m_name.group(1).strip()

			license_no = None
			m_lic = re.search(r'Lizenz\s+(\S+)', line, re.IGNORECASE)
			if m_lic:
				license_no = m_lic.group(1).rstrip('.,')

			if license_no:
				dog = db.session.execute(
					db.select(Dog).filter_by(license_no=license_no)
				).scalar_one_or_none()
				if dog:
					old_tka_name = dog.tka_name
					dog.tka_name = system_name
					if old_tka_name != system_name:
						name_changes.append(
							f"✏️ TKAMO-Name: {license_no} '{old_tka_name or dog.name}' → '{system_name}'"
						)
					else:
						name_changes.append(
							f"✏️ TKAMO-Name: {license_no} '{system_name}' (Schreibweise bestätigt)"
						)

	db.session.commit()
	return name_changes, class_emails, inactive_licenses


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
        .order_by(Registration.category_code, Registration.class_level, Registration.id)
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

        # ── "Verein <Name> / ... / stimmt auf Zeile N nicht mit Hundeführer
        #    überein" → ignorieren (keine Aktion). Reiner Vereins-Mismatch,
        #    da unsere CSV i.d.R. einen Vereinsnamen statt einer Vereinsnummer
        #    liefert (fehlende Vereinsnummer im Quell-Export) — betrifft nicht
        #    die Startberechtigung.
        if re.search(r'nicht mit Hundeführer überein', line, re.IGNORECASE):
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

        # ── Hundename → TKAMO-System-Namen in tka_name übernehmen ───────────
        # Lizenz ist NIE in dieser Zeile — immer nur Zeile N.
        # Schreibt NICHT mehr in dog.name (das bleibt der AOA-Name für alle
        # normalen Listen) — sondern in das eigene tka_name-Feld, das nur
        # beim TKAMO-CSV-Export verwendet wird.
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
                    old_tka_name = dog.tka_name
                    dog.tka_name = system_name  # immer übernehmen
                    if old_tka_name != system_name:
                        name_changes.append(
                            f"✏️ TKAMO-Name: {license_no} '{old_tka_name or dog.name}' → '{system_name}'"
                        )
                    else:
                        name_changes.append(
                            f"✏️ TKAMO-Name: {license_no} '{system_name}' (Schreibweise bestätigt)"
                        )

    db.session.commit()
    return name_changes, class_emails, inactive_licenses


@club_bp.post("/lizenzcheck-multi")
@login_required
def club_lizenzcheck_multi():
	"""
	Multi-Event TKAMO-Import.
	Input: ?events=34,35 + tkamo_result im Body
	Verarbeitet Lizenzcheck für alle Events zusammen.
	"""
	events_param = request.args.get("events", "").strip()
	if not events_param:
		abort(400)

	try:
		event_ids = [int(x.strip()) for x in events_param.split(",")]
	except ValueError:
		abort(400)

	if not event_ids:
		abort(400)

	# Access-Check
	events = []
	for event_id in event_ids:
		event = db.session.get(Event, event_id)
		if not event:
			abort(404)
		_assert_event_access(event)
		events.append(event)

	report_text = request.form.get("tkamo_result", "").strip()
	if not report_text:
		from flask import redirect, url_for, flash
		flash(_("Bitte TKAMO-Ergebnis einfügen."), "warning")
		return redirect(url_for("club.club_home"))

	name_changes, class_emails, inactive_licenses = _parse_and_apply_tkamo_multi(events, report_text)

	# Speichere Lizenzcheck für alle Events
	for event in events:
		event.lizenzcheck_done_at = datetime.utcnow()
		event.lizenzcheck_report  = report_text
	db.session.commit()

	return render_template(
		"club/lizenzcheck_result_multi.html",
		events=events,
		report_text=report_text,
		name_changes=name_changes,
		class_emails=class_emails,
		inactive_licenses=inactive_licenses,
	)


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
        flash(_("Bitte TKAMO-Ergebnis einfügen."), "warning")
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
    Token enthält event_id (oder event_ids für Multi-Event), dog_id, cat, cls.
    Backward-compatible mit alten Single-Event-Tokens.
    """
    data = _decode_confirm_token(token)
    if not data:
        abort(400)

    dog = db.session.get(Dog, data["dog_id"])
    if not dog:
        abort(404)

    # Backward-compatibility: event_id (single) oder event_ids (multi)
    event_ids = data.get("event_ids") or [data.get("event_id")]
    if not event_ids or None in event_ids:
        abort(400)

    # Mindestens ein Event-Lookup für die Template-Anzeige (primary event)
    primary_event = db.session.get(Event, event_ids[0])
    if not primary_event:
        abort(404)

    new_cat = data["cat"]
    new_cls = data["cls"]

    # Dog aktualisieren
    dog.category    = new_cat
    dog.class_level = new_cls

    # Anmeldungen aktualisieren (für alle Events im Token)
    cat_full = _CAT_LABEL.get(new_cat, new_cat)
    for event_id in event_ids:
        regs = db.session.execute(
            db.select(Registration).filter_by(event_id=event_id, dog_id=dog.id)
        ).scalars().all()
        for reg in regs:
            reg.class_level   = new_cls
            reg.category_code = cat_full

    db.session.commit()

    return render_template(
        "club/lizenzcheck_confirm.html",
        event=primary_event,
        num_events=len(event_ids),
        dog_name=dog.name,
        license_no=dog.license_no,
        cat_label=cat_full,
        cls=new_cls,
    )
