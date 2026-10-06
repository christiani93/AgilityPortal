"""
AOA-Import – Registrierungen aus einem AOA-/SportyDog-CSV-Export importieren.

Das CSV-Format entspricht dem SportyDog-Export (Turnierplattform).
Importierte Datensätze werden direkt als CONFIRMED eingetragen,
der TKA-Lizenzcheck wird auf PENDING gesetzt (noch nicht geprüft).
Es werden keine E-Mails versendet.
"""
import csv
import io
import json
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


def _unescape(text: str) -> str:
    """
    Entfernt Backslash-Escaping aus dem SportyDog/AOA-Export (DBISAM-Eigenart:
    Apostrophe/Anführungszeichen werden als \\' bzw. \\" exportiert).
    Betrifft Hundenamen, Personennamen und Vereinsnamen (z.B. "Cypat\\'Agil").
    """
    if not text:
        return text
    return text.replace("\\'", "'").replace('\\"', '"')


def _normalize_header(name: str) -> str:
    """Normalisiert einen Spaltennamen für den Vergleich: case-insensitive und
    ohne das AOA-/SportyDog-Suffix ' AOA' (echte Exporte haben z.B. 'H Lizenz AOA',
    während die Alias-Liste nur 'H Lizenz' kennt)."""
    s = (name or "").lower().strip()
    if s.endswith(" aoa"):
        s = s[:-4].strip()
    return s


def _find_column(headers: list[str], *candidates: str) -> str | None:
    """Sucht eine Spalte anhand mehrerer möglicher Namen (case-insensitive,
    ' AOA'-Suffix wird ignoriert)."""
    lookup: dict[str, str] = {}
    for h in headers:
        lookup.setdefault(_normalize_header(h), h)
    for c in candidates:
        match = lookup.get(_normalize_header(c))
        if match:
            return match
    return None


def _detect_columns(headers: list[str]) -> dict[str, str | None]:
    """Zentrale Spaltenerkennung für Preview UND Import (vorher divergent).
    Deckt AOA-/SportyDog-Original ('Lizenz'), TKAMO-Variante mit 'H '-/'HF '-
    Präfixen sowie das reale AOA-Export-Format mit ' AOA'-Suffix ab."""
    return {
        "license": _find_column(headers, "Lizenz", "LicenseNo", "License", "Lizenznummer", "H Lizenz"),
        "dog_name": _find_column(headers, "Hundename", "DogName", "Hund", "Name Hund", "H Name"),
        "category": _find_column(headers, "Kategorie", "Category", "Kat", "H Kategorie"),
        "class": _find_column(headers, "Klasse", "Class", "KL", "Kl", "H Kl Eingabe", "H Klasse"),
        "first_name": _find_column(headers, "Vorname", "FirstName", "Fname", "HF Vorname"),
        "last_name": _find_column(headers, "Nachname", "LastName", "Lname", "Name", "HF Name"),
        "email": _find_column(headers, "Email", "E-Mail", "EMail", "HF Email"),
        "phone": _find_column(headers, "Telefon", "Phone", "Tel", "Mobile", "HF Telefon"),
        "club": _find_column(headers, "Verein", "Club", "ClubName", "HF Verein"),
        "club_no": _find_column(headers, "Vereinsnummer", "ClubNo", "VereinsNr", "HF Vereinnr"),
        "breed": _find_column(headers, "Rasse", "Breed", "H Rasse"),
    }


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


def _coerce_cell(value) -> str:
    """xlsx-Zellwerte (Zahl/Datum/None) zu Strings wie in einem CSV. Ganzzahlige
    Floats (openpyxl liest 1 als 1.0) ohne '.0', damit z.B. die Klasse '1' bleibt."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _parse_xlsx(raw: bytes) -> tuple[list[dict], list[str]]:
    """Liest die erste Tabelle eines echten .xlsx (OOXML). SportyDog exportiert
    sauberes UTF-8 – anders als beim Umweg über 'Speichern als CSV' (cp1252,
    Umlaute kaputt). Alle Werte werden wie beim CSV als Strings geliefert."""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
    try:
        ws = wb.active
        it = ws.iter_rows(values_only=True)
        try:
            header_row = next(it)
        except StopIteration:
            return [], []
        headers = [_coerce_cell(h).strip() for h in header_row]
        rows = []
        for r in it:
            if r is None:
                continue
            row = {headers[i]: _coerce_cell(v) for i, v in enumerate(r) if i < len(headers)}
            if any(val.strip() for val in row.values()):
                rows.append(row)
        return rows, headers
    finally:
        wb.close()


def _decode_text(raw: bytes) -> str:
    """Dekodiert eine hochgeladene Text-/CSV-Datei. Zuerst UTF-8 (mit/ohne BOM);
    schlägt das fehl, ist es fast immer ein Excel-'Speichern als CSV' auf einem
    DE-Windows → cp1252 (sonst würden Umlaute zu � zerstört)."""
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace")


def _read_upload(file) -> tuple[list[dict], list[str]]:
    """Liest den Upload als echtes .xlsx (openpyxl) ODER als CSV/Text.
    xlsx-Erkennung über Endung oder ZIP-Magic ('PK')."""
    raw = file.read()
    name = (file.filename or "").lower()
    if name.endswith((".xlsx", ".xlsm")) or raw[:4] == b"PK\x03\x04":
        return _parse_xlsx(raw)
    return _parse_csv(_decode_text(raw))


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

    try:
        rows, headers = _read_upload(file)
    except Exception as e:
        flash(f"Datei konnte nicht gelesen werden: {e}", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    # Spaltenmapping ermitteln (gemeinsam mit dem Import, s. _detect_columns)
    cols = _detect_columns(headers)
    col_license = cols["license"]
    col_dog_name = cols["dog_name"]
    col_category = cols["category"]
    col_class = cols["class"]
    col_first_name = cols["first_name"]
    col_last_name = cols["last_name"]
    col_email = cols["email"]
    col_phone = cols["phone"]
    col_club = cols["club"]
    col_club_no = cols["club_no"]

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
        dog_name = _unescape((row.get(col_dog_name) or "").strip())
        cat_raw = (row.get(col_category) or "").strip()
        category = CATEGORY_MAP.get(cat_raw.lower(), cat_raw)
        try:
            class_level = int((row.get(col_class) or "").strip())
        except ValueError:
            class_level = 1

        first_name = _unescape((row.get(col_first_name) or "").strip()) if col_first_name else ""
        last_name = _unescape((row.get(col_last_name) or "").strip()) if col_last_name else ""
        email = (row.get(col_email) or "").strip() if col_email else ""
        phone = (row.get(col_phone) or "").strip() if col_phone else ""
        club_name = _unescape((row.get(col_club) or "").strip()) if col_club else ""
        club_no = (row.get(col_club_no) or "").strip() if col_club_no else ""

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
            "club_no": club_no,
            "existing_dog": existing_dog is not None,
            "already_registered": existing_reg is not None,
        })

    # Eingelesene Daten (bereits normalisiert) für den Import als Hidden Field.
    # JSON statt Roh-CSV: deterministisch, kein erneutes Delimiter-Sniffing und
    # kein Format-/Encoding-Problem beim xlsx-Upload.
    import base64
    payload = json.dumps({"headers": headers, "rows": rows})
    csv_b64 = base64.b64encode(payload.encode("utf-8")).decode()

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
        payload = json.loads(base64.b64decode(csv_b64.encode()).decode("utf-8"))
        rows = payload["rows"]
        headers = payload["headers"]
    except Exception as e:
        flash(f"Import-Daten fehlerhaft: {e}", "danger")
        return redirect(url_for("aoa_import.aoa_import_home", key=_admin_key()))

    cols = _detect_columns(headers)
    col_license = cols["license"]
    col_dog_name = cols["dog_name"]
    col_category = cols["category"]
    col_class = cols["class"]
    col_first_name = cols["first_name"]
    col_last_name = cols["last_name"]
    col_email = cols["email"]
    col_phone = cols["phone"]
    col_club = cols["club"]
    col_club_no = cols["club_no"]
    # col_breed (cols["breed"]) erkannt, aber ungenutzt – Dog-Modell hat kein breed-Feld

    created = 0
    skipped = 0
    errors = []

    for i, row in enumerate(rows):
        license_no = _normalize_license((row.get(col_license) or "").strip())
        if not license_no:
            continue

        dog_name = _unescape((row.get(col_dog_name) or "").strip())
        cat_raw = (row.get(col_category) or "").strip()
        category = CATEGORY_MAP.get(cat_raw.lower(), cat_raw)
        try:
            class_level = int((row.get(col_class) or "").strip())
        except ValueError:
            class_level = 1

        first_name = _unescape((row.get(col_first_name) or "").strip()) if col_first_name else ""
        last_name = _unescape((row.get(col_last_name) or "").strip()) if col_last_name else ""
        email = (row.get(col_email) or "").strip() if col_email else None
        phone = (row.get(col_phone) or "").strip() if col_phone else None
        # Vereinsnummer bevorzugt (für TKAMO-Lizenzcheck-Export benötigt),
        # sonst Klartext-Vereinsname als Fallback. "0" = Ausland/kein CH-Verein,
        # dann lieber den Klartext-Namen (z.B. "--- AUSLAND ---") behalten.
        club_no = (row.get(col_club_no) or "").strip() if col_club_no else ""
        if club_no == "0":
            club_no = ""
        club_name_raw = _unescape((row.get(col_club) or "").strip()) if col_club else ""
        club_value = club_no or club_name_raw

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
            elif dog_name and dog.name != dog_name:
                # Dedup per Lizenz: Namen auf die maßgebliche Startliste aktualisieren,
                # sonst bleiben veraltete Seed-/Platzhalternamen stehen.
                dog.name = dog_name

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
                if club_value:
                    existing_reg.club_name = club_value
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
                club_name=club_value or None,
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
