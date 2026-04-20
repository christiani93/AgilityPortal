"""
AOA-Import – Registrierungen aus einem AOA-/SportyDog-CSV-Export importieren.

Das CSV-Format entspricht dem SportyDog-Export (Turnierplattform).
Importierte Datensätze werden direkt als CONFIRMED eingetragen,
der TKA-Lizenzcheck wird auf PENDING gesetzt (noch nicht geprüft).
Es werden keine E-Mails versendet.
"""
import csv
import io
from functools import wraps

from flask import (Blueprint, abort, current_app, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user

from app.extensions import db
from app.models import (Dog, DogOwner, DogOwnerRole, Event, LicenseKind, Person,
                        Registration, RegistrationStatus, TkaEventCheckStatus)

aoa_import_bp = Blueprint("aoa_import", __name__)


# ── Auth (gleich wie cups_admin) ──────────────────────────────────────────────

def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and getattr(current_user, 'is_superadmin', False):
            return func(*args, **kwargs)
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def _admin_key():
    if current_user.is_authenticated and getattr(current_user, 'is_superadmin', False):
        return ""
    return request.args.get("key") or ""


# ── Konstanten ────────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "large": "Large",
    "l": "Large",
    "intermediate": "Intermediate",
    "i": "Intermediate",
    "medium": "Medium",
    "m": "Medium",
    "small": "Small",
    "s": "Small",
}

# Kurzpräfixe → 3-Zeichen ISO-Code (Dog-Validator braucht genau 3 Buchstaben)
LICENSE_PREFIX_NORMALIZE = {
    "A": "AUT",
    "D": "DEU",
    "F": "FRA",
    "B": "BEL",
    "I": "ITA",
    "E": "ESP",
    "NL": "NLD",
    "CH": "CHE",
}


def _normalize_license(license_no: str) -> str:
    """
    Normalisiert die Lizenznummer:
    - Numerisch: unverändert (CH)
    - Präfix: auf 3 Großbuchstaben normalisieren (z.B. A-1234 → AUT-1234)
    """
    license_no = license_no.strip()
    if license_no.isdigit():
        return license_no
    if "-" in license_no:
        prefix, rest = license_no.split("-", 1)
        prefix_up = prefix.upper()
        normalized = LICENSE_PREFIX_NORMALIZE.get(prefix_up, prefix_up)
        # Auf 3 Zeichen auffüllen wenn nötig (Fallback)
        if len(normalized) < 3:
            normalized = normalized.ljust(3, "X")
        return f"{normalized}-{rest}"
    return license_no


def _detect_license_kind(license_no: str) -> LicenseKind:
    """Numerisch = CH, Präfix = FOREIGN."""
    if license_no.strip().isdigit():
        return LicenseKind.CH
    return LicenseKind.FOREIGN


def _find_column(headers: list[str], *candidates: str) -> str | None:
    """Sucht eine Spalte anhand mehrerer möglicher Namen (case-insensitive)."""
    lower = {h.lower().strip(): h for h in headers}
    for c in candidates:
        match = lower.get(c.lower())
        if match:
            return match
    return None


def _parse_csv(file_content: str) -> tuple[list[dict], list[str]]:
    """
    Parst das SportyDog/AOA CSV.
    Gibt (rows, headers) zurück.
    Versucht Semikolon und Komma als Trennzeichen.
    """
    # Trennzeichen automatisch erkennen
    sample = file_content[:2048]
    dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    reader = csv.DictReader(io.StringIO(file_content), dialect=dialect)
    rows = list(reader)
    headers = reader.fieldnames or []
    return rows, list(headers)


# ── Routes ────────────────────────────────────────────────────────────────────

@aoa_import_bp.get("/admin/aoa-import")
@_require_admin_key
def aoa_import_home():
    events = Event.query.order_by(Event.starts_at.desc()).limit(100).all()
    return render_template(
        "admin/aoa_import/home.html",
        events=events,
        admin_key=_admin_key(),
    )


@aoa_import_bp.post("/admin/aoa-import/preview")
@_require_admin_key
def aoa_import_preview():
    """CSV hochladen und Vorschau der zu importierenden Datensätze zeigen."""
    event_id = request.form.get("event_id", type=int)
    if not event_id:
        flash("Bitte ein Event auswählen.", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    event = db.session.get(Event, event_id)
    if not event:
        flash("Event nicht gefunden.", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    file = request.files.get("csv_file")
    if not file or not file.filename:
        flash("Bitte eine CSV-Datei hochladen.", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    content = file.read().decode("utf-8-sig", errors="replace")
    try:
        rows, headers = _parse_csv(content)
    except Exception as e:
        flash(f"CSV konnte nicht gelesen werden: {e}", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    # Spaltenmapping ermitteln
    col_license = _find_column(headers, "Lizenz", "LicenseNo", "License", "Lizenznummer")
    col_dog_name = _find_column(headers, "Hundename", "DogName", "Hund", "Name Hund")
    col_category = _find_column(headers, "Kategorie", "Category", "Kat")
    col_class = _find_column(headers, "Klasse", "Class", "KL", "Kl")
    col_first_name = _find_column(headers, "Vorname", "FirstName", "Fname")
    col_last_name = _find_column(headers, "Nachname", "LastName", "Lname", "Name")
    col_email = _find_column(headers, "Email", "E-Mail", "EMail")
    col_phone = _find_column(headers, "Telefon", "Phone", "Tel", "Mobile")
    col_club = _find_column(headers, "Verein", "Club", "ClubName")
    col_club_no = _find_column(headers, "Vereinsnummer", "ClubNo", "VereinsNr")

    missing = [n for n, c in [
        ("Lizenz", col_license), ("Hundename", col_dog_name),
        ("Kategorie", col_category), ("Klasse", col_class),
    ] if not c]

    if missing:
        flash(f"Pflichtspalten nicht gefunden: {', '.join(missing)}. "
              f"Gefundene Spalten: {', '.join(headers)}", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    # Vorschau aufbauen
    previews = []
    for i, row in enumerate(rows):
        license_no = _normalize_license((row.get(col_license) or "").strip())
        if not license_no:
            continue
        dog_name = (row.get(col_dog_name) or "").strip()
        cat_raw = (row.get(col_category) or "").strip()
        category = CATEGORY_MAP.get(cat_raw.lower(), cat_raw)
        try:
            class_level = int((row.get(col_class) or "").strip())
        except ValueError:
            class_level = 1

        first_name = (row.get(col_first_name) or "").strip() if col_first_name else ""
        last_name = (row.get(col_last_name) or "").strip() if col_last_name else ""
        email = (row.get(col_email) or "").strip() if col_email else ""
        phone = (row.get(col_phone) or "").strip() if col_phone else ""
        club_name = (row.get(col_club) or "").strip() if col_club else ""

        # Prüfen ob bereits registriert
        existing_dog = Dog.query.filter_by(license_no=license_no).first()
        existing_reg = None
        if existing_dog:
            existing_reg = Registration.query.filter_by(
                event_id=event_id, dog_id=existing_dog.id
            ).first()

        previews.append({
            "row_no": i + 1,
            "license_no": license_no,
            "license_kind": _detect_license_kind(license_no).value,
            "dog_name": dog_name,
            "category": category,
            "class_level": class_level,
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "club_name": club_name,
            "existing_dog": existing_dog is not None,
            "already_registered": existing_reg is not None,
        })

    # CSV-Inhalt für späteren Import als Hidden Field (base64)
    import base64
    csv_b64 = base64.b64encode(content.encode("utf-8")).decode()

    return render_template(
        "admin/aoa_import/preview.html",
        event=event,
        previews=previews,
        csv_b64=csv_b64,
        admin_key=_admin_key(),
        col_license=col_license,
        col_dog_name=col_dog_name,
        col_category=col_category,
        col_class=col_class,
        col_first_name=col_first_name,
        col_last_name=col_last_name,
        col_email=col_email,
        col_phone=col_phone,
        col_club=col_club,
    )


@aoa_import_bp.post("/admin/aoa-import/execute")
@_require_admin_key
def aoa_import_execute():
    """Führt den eigentlichen Import durch."""
    import base64

    event_id = request.form.get("event_id", type=int)
    csv_b64 = request.form.get("csv_b64", "")
    skip_existing = bool(request.form.get("skip_existing"))

    event = db.session.get(Event, event_id)
    if not event:
        flash("Event nicht gefunden.", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    try:
        content = base64.b64decode(csv_b64.encode()).decode("utf-8")
        rows, headers = _parse_csv(content)
    except Exception as e:
        flash(f"CSV-Fehler: {e}", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    col_license = _find_column(headers, "Lizenz", "LicenseNo", "License", "Lizenznummer")
    col_dog_name = _find_column(headers, "Hundename", "DogName", "Hund", "Name Hund")
    col_category = _find_column(headers, "Kategorie", "Category", "Kat")
    col_class = _find_column(headers, "Klasse", "Class", "KL", "Kl")
    col_first_name = _find_column(headers, "Vorname", "FirstName", "Fname")
    col_last_name = _find_column(headers, "Nachname", "LastName", "Lname", "Name")
    col_email = _find_column(headers, "Email", "E-Mail", "EMail")
    col_phone = _find_column(headers, "Telefon", "Phone", "Tel", "Mobile")
    # col_breed nicht verwendet – Dog-Modell hat kein breed-Feld

    created = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows):
        license_no = _normalize_license((row.get(col_license) or "").strip())
        if not license_no:
            continue

        dog_name = (row.get(col_dog_name) or "").strip()
        cat_raw = (row.get(col_category) or "").strip()
        category = CATEGORY_MAP.get(cat_raw.lower(), cat_raw)
        try:
            class_level = int((row.get(col_class) or "").strip())
        except ValueError:
            class_level = 1

        first_name = (row.get(col_first_name) or "").strip() if col_first_name else ""
        last_name = (row.get(col_last_name) or "").strip() if col_last_name else ""
        email = (row.get(col_email) or "").strip() if col_email else None
        phone = (row.get(col_phone) or "").strip() if col_phone else None

        try:
            # 1. Hund finden oder anlegen
            dog = Dog.query.filter_by(license_no=license_no).first()
            if not dog:
                dog = Dog(
                    name=dog_name,
                    license_no=license_no,
                    license_kind=_detect_license_kind(license_no),
                    category=category[0].upper() if category else None,  # L/I/M/S
                    class_level=class_level,
                )
                db.session.add(dog)
                db.session.flush()

            # 2. Person (Hundeführer) finden oder anlegen
            person = None
            if first_name or last_name:
                # Suche nach Name + E-Mail, sonst neu anlegen
                if email:
                    person = Person.query.filter_by(email=email).first()
                if not person and first_name and last_name:
                    person = Person.query.filter_by(
                        first_name=first_name, last_name=last_name
                    ).first()
                if not person:
                    person = Person(
                        first_name=first_name,
                        last_name=last_name,
                        email=email or None,
                        phone=phone or None,
                    )
                    db.session.add(person)
                    db.session.flush()

                # DogOwner-Verknüpfung wenn noch nicht vorhanden
                if person:
                    exists_owner = DogOwner.query.filter_by(
                        dog_id=dog.id, person_id=person.id
                    ).first()
                    if not exists_owner:
                        db.session.add(DogOwner(
                            dog_id=dog.id,
                            person_id=person.id,
                            role=DogOwnerRole.HANDLER,
                        ))

            # 3. Bereits registriert?
            existing_reg = Registration.query.filter_by(
                event_id=event_id, dog_id=dog.id
            ).first()
            if existing_reg:
                if skip_existing:
                    skipped += 1
                    continue
                # Bestehende Registrierung aktualisieren
                existing_reg.status = RegistrationStatus.CONFIRMED
                existing_reg.category_code = category
                existing_reg.class_level = class_level
                existing_reg.handler_id = person.id if person else existing_reg.handler_id
                created += 1
                continue

            # 4. Neue Registrierung anlegen
            reg = Registration(
                event_id=event_id,
                dog_id=dog.id,
                handler_id=person.id if person else None,
                category_code=category,
                class_level=class_level,
                status=RegistrationStatus.CONFIRMED,
                tka_event_check_status=TkaEventCheckStatus.PENDING,
            )
            db.session.add(reg)
            created += 1

        except Exception as exc:
            errors.append(f"Zeile {i + 2}: {exc}")
            db.session.rollback()
            continue

    db.session.commit()

    if errors:
        for err in errors[:10]:
            flash(err, "warning")
    flash(
        f"Import abgeschlossen: {created} Registrierungen erstellt/aktualisiert, "
        f"{skipped} übersprungen.",
        "success" if not errors else "warning",
    )
    return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))
