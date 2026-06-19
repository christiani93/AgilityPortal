import hashlib
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import current_app

from app.extensions import db
from app.models import (
    Document,
    BillingMode,
    Dog,
    Event,
    EventFinalist,
    LicenseKind,
    LiveUpdate,
    Person,
    Registration,
    RegistrationStatus,
    Result,
    ResultImport,
    StartNumber,
    ScheduleBlock,
    TkaEventCheckStatus,
)

EVENT_EXPORT_SCHEMA = "agility.exchange.eventexport.v1"
LIVE_UPDATE_SCHEMA = "agility.exchange.liveupdate.v1"
RESULT_EXPORT_SCHEMA = "agility.exchange.resultexport.v1"


def _utc_now():
    return datetime.now(timezone.utc)


def _ensure_external_id(value):
    return value or uuid4().hex


def build_event_export_zip(event_id: int):
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")

    if not event.external_id:
        event.external_id = _ensure_external_id(event.external_id)

    registrations = Registration.query.filter_by(event_id=event_id).all()
    persons = {}
    dogs = {}

    for registration in registrations:
        dog = registration.dog
        handler = registration.handler
        if dog:
            if not dog.external_id:
                dog.external_id = _ensure_external_id(dog.external_id)
            dogs[dog.external_id] = {
                "external_id": dog.external_id,
                "name": dog.name,
                "license_no": dog.license_no,
                "license_kind": dog.license_kind.value,
            }
        if handler:
            if not handler.external_id:
                handler.external_id = _ensure_external_id(handler.external_id)
            persons[handler.external_id] = {
                "external_id": handler.external_id,
                "first_name": handler.first_name,
                "last_name": handler.last_name,
                "email": handler.email,
            }

        if not registration.external_id:
            registration.external_id = _ensure_external_id(registration.external_id)

    db.session.flush()

    manifest = {
        "schema": EVENT_EXPORT_SCHEMA,
        "generated_at": _utc_now().isoformat(),
    }
    event_payload = {
        "external_id": event.external_id,
        "name": event.name,
        "location": event.location,
        "starts_at": event.starts_at.isoformat() if event.starts_at else None,
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "billing_mode": event.billing_mode.value,
    }
    entities_payload = {
        "persons": list(persons.values()),
        "dogs": list(dogs.values()),
    }
    start_numbers_payload = _build_start_numbers_payload(event, registrations)
    schedule_payload = _build_schedule_payload(event)
    registrations_payload = []
    payment_status = "PAID"
    if event.billing_mode != BillingMode.PORTAL:
        payment_status = "NOT_MANAGED"

    for registration in registrations:
        registrations_payload.append(
            {
                "external_id": registration.external_id,
                "event_external_id": event.external_id,
                "dog_external_id": registration.dog.external_id if registration.dog else None,
                "handler_person_external_id": registration.handler.external_id
                if registration.handler
                else None,
                "category_code": registration.category_code,
                "class_level": registration.class_level,
                "status": registration.status.value,
                "tka_event_check_status": registration.tka_event_check_status.value,
                "can_start": True,
                "eligibility": {"payment_status": payment_status},
            }
        )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False))
        zip_file.writestr("event.json", json.dumps(event_payload, ensure_ascii=False))
        zip_file.writestr("entities.json", json.dumps(entities_payload, ensure_ascii=False))
        zip_file.writestr("registrations.json", json.dumps(registrations_payload, ensure_ascii=False))
        zip_file.writestr(
            "start_numbers.json", json.dumps(start_numbers_payload, ensure_ascii=False)
        )
        zip_file.writestr("schedule.json", json.dumps(schedule_payload, ensure_ascii=False))

    zip_bytes = buffer.getvalue()
    sha256 = hashlib.sha256(zip_bytes).hexdigest()
    filename = f"event_export_{event.external_id}.zip"

    return zip_bytes, filename, sha256


def _build_start_numbers_payload(event, registrations):
    numbers = []
    start_numbers = (
        StartNumber.query.filter_by(event_id=event.id)
        .order_by(StartNumber.start_no)
        .all()
    )
    for entry in start_numbers:
        registration = next(
            (reg for reg in registrations if reg.id == entry.registration_id), None
        )
        if registration and not registration.external_id:
            registration.external_id = _ensure_external_id(registration.external_id)
        numbers.append(
            {
                "registration_external_id": registration.external_id if registration else None,
                "start_no": entry.start_no,
            }
        )
    db.session.flush()
    rule_set = None
    if event.start_numbers_rule_set:
        try:
            rule_set = json.loads(event.start_numbers_rule_set)
        except json.JSONDecodeError:
            rule_set = event.start_numbers_rule_set
    return {
        "event_external_id": event.external_id,
        "locked": event.start_numbers_locked,
        "generated_at": event.start_numbers_generated_at.isoformat()
        if event.start_numbers_generated_at
        else None,
        "rule_set": rule_set,
        "numbers": numbers,
    }


def _build_schedule_payload(event):
    blocks = (
        ScheduleBlock.query.filter_by(event_id=event.id)
        .order_by(ScheduleBlock.sort_index, ScheduleBlock.start_at)
        .all()
    )
    payload_blocks = []
    for block in blocks:
        payload_blocks.append(
            {
                "ring": block.ring,
                "start_at": _format_schedule_datetime(block.start_at),
                "discipline": block.discipline,
                "category_code": block.category_code,
                "class_level": block.class_level,
                "notes": block.notes or "",
            }
        )
    return {
        "event_external_id": event.external_id,
        "timezone": "Europe/Zurich",
        "locked": event.schedule_locked,
        "blocks": payload_blocks,
    }


def _format_schedule_datetime(value):
    if not value:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=ZoneInfo("Europe/Zurich"))
    return value.isoformat()


def validate_live_update(payload: dict):
    if payload.get("schema") != LIVE_UPDATE_SCHEMA:
        raise ValueError("Invalid schema")
    event_external_id = payload.get("event_external_id")
    source = payload.get("source") or {}
    source_device = source.get("device")
    sequence_no = payload.get("sequence_no")
    if not event_external_id or not source_device or sequence_no is None:
        raise ValueError("Missing required fields")
    return event_external_id, source_device, sequence_no


def store_live_update(payload: dict):
    event_external_id, source_device, sequence_no = validate_live_update(payload)
    existing = LiveUpdate.query.filter_by(
        event_external_id=event_external_id,
        source_device=source_device,
        sequence_no=sequence_no,
    ).first()
    if existing:
        return False, existing

    event = Event.query.filter_by(external_id=event_external_id).first()
    source = payload.get("source") or {}
    record = LiveUpdate(
        event_id=event.id if event else None,
        event_external_id=event_external_id,
        source_system=source.get("system", "unknown"),
        source_version=source.get("version"),
        source_device=source_device,
        sent_at=_parse_datetime(payload.get("sent_at")),
        sequence_no=sequence_no,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    db.session.add(record)
    db.session.commit()
    return True, record


def import_result_export_zip(zip_bytes: bytes):
    sha256 = hashlib.sha256(zip_bytes).hexdigest()
    existing = ResultImport.query.filter_by(sha256=sha256).first()
    if existing:
        return existing

    buffer = io.BytesIO(zip_bytes)
    with zipfile.ZipFile(buffer) as zip_file:
        manifest = json.loads(zip_file.read("manifest.json"))
        if manifest.get("schema") != RESULT_EXPORT_SCHEMA:
            raise ValueError("Invalid schema")
        results_payload = json.loads(zip_file.read("results.json"))

        event_external_id = results_payload.get("event_external_id")
        event = Event.query.filter_by(external_id=event_external_id).first()

        exported_at = _parse_datetime(results_payload.get("exported_at"))
        final = bool(results_payload.get("final"))

        base_dir = os.path.join(
            current_app.instance_path,
            "uploads",
            "results",
            event_external_id or "unknown",
            _utc_now().strftime("%Y%m%d%H%M%S"),
        )
        os.makedirs(base_dir, exist_ok=True)
        zip_path = os.path.join(base_dir, "result_export.zip")
        with open(zip_path, "wb") as handle:
            handle.write(zip_bytes)

        result_import = ResultImport(
            event_id=event.id if event else None,
            schema=manifest.get("schema"),
            exported_at=exported_at,
            final=final,
            zip_path=zip_path,
            sha256=sha256,
        )
        db.session.add(result_import)
        db.session.flush()

        for class_block in results_payload.get("classes", []):
            for row in class_block.get("results", []):
                result_row = Result(
                    result_import_id=result_import.id,
                    event_id=event.id if event else None,
                    ring=class_block.get("ring"),
                    discipline=class_block.get("discipline"),
                    category_code=class_block.get("category_code"),
                    class_level=class_block.get("class_level"),
                    run_no=class_block.get("run_no"),
                    registration_external_id=row.get("registration_external_id"),
                    start_no=row.get("start_no"),
                    rank=row.get("rank"),
                    time_s=row.get("time_s"),
                    faults=row.get("faults"),
                    refusals=row.get("refusals"),
                    total_faults=row.get("total_faults"),
                    eliminated=row.get("eliminated"),
                    status=row.get("status"),
                    dog_name=row.get("dog_name"),
                    handler_name=row.get("handler_name"),
                )
                db.session.add(result_row)

        for doc in results_payload.get("documents", []):
            document = Document(
                result_import_id=result_import.id,
                kind=doc.get("kind"),
                name=doc.get("name"),
                path=doc.get("path", ""),
                sha256=doc.get("sha256"),
            )
            db.session.add(document)

        for name in zip_file.namelist():
            if name.startswith("pdfs/"):
                content = zip_file.read(name)
                pdf_path = os.path.join(base_dir, name)
                os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
                with open(pdf_path, "wb") as handle:
                    handle.write(content)
                document = Document(
                    result_import_id=result_import.id,
                    kind="RANKING_PDF",
                    name=os.path.basename(name),
                    path=pdf_path,
                    sha256=hashlib.sha256(content).hexdigest(),
                )
                db.session.add(document)

        # Schema v1.6: optionale Finalisten-Liste (SKBS-SM) übernehmen
        if "finalists.json" in zip_file.namelist() and event:
            _import_finalists(zip_file, event)

        if final and event:
            event.is_completed = True

        db.session.commit()
        return result_import


def _import_finalists(zip_file, event):
    """
    Liest finalists.json und ersetzt EventFinalist-Einträge für das Event
    idempotent (alte Einträge werden gelöscht, neue eingefügt).
    """
    payload = json.loads(zip_file.read("finalists.json"))
    finalists = payload.get("finalists") or []

    EventFinalist.query.filter_by(event_id=event.id).delete(synchronize_session=False)

    for pos, f in enumerate(finalists, start=1):
        db.session.add(EventFinalist(
            event_id=event.id,
            license=(f.get("license") or "")[:50],
            dog_name=(f.get("dog_name") or "")[:120],
            handler_name=(f.get("handler_name") or "")[:120],
            source=(f.get("source") or "")[:30],
            from_class=f.get("from_class"),
            quali_rank=f.get("quali_rank"),
            position=pos,
        ))


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Event-Package Import (inverse von build_event_export_zip)
# ---------------------------------------------------------------------------

class EventPackageImportResult:
    def __init__(self):
        self.created = False
        self.event_id = None
        self.external_id = None
        self.persons = 0
        self.dogs = 0
        self.registrations = 0
        self.start_numbers = 0
        self.schedule_blocks = 0
        self.warnings: list[str] = []


def import_event_package_zip(zip_bytes: bytes, is_test: bool = True) -> EventPackageImportResult:
    """
    Importiert ein eventexport.v1.zip ins Portal — invers zu build_event_export_zip.

    Idempotent: Match via external_id, create-or-update.
      - Event: erstellt oder aktualisiert Stammdaten (Name, Datum, Location)
      - Persons / Dogs: upsert via external_id, Fallback: Dog matched über license_no
      - Registrations: gelöscht und neu erstellt (einfacher als komplexer Diff)
      - StartNumbers: gelöscht und neu erstellt
      - ScheduleBlocks: gelöscht und neu erstellt

    is_test=True (Default): neue Events bekommen is_test=True und is_published=False
    (geeignet für Demo-Daten). Bei bestehendem Event werden Test-Flags NICHT geändert.
    """
    result = EventPackageImportResult()

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
        names = set(zip_file.namelist())
        if "manifest.json" not in names:
            raise ValueError("ZIP enthält kein manifest.json")
        manifest = json.loads(zip_file.read("manifest.json"))
        if manifest.get("schema") != EVENT_EXPORT_SCHEMA:
            raise ValueError(f"Ungültiges Schema: {manifest.get('schema')!r}, erwartet {EVENT_EXPORT_SCHEMA!r}")
        if "event.json" not in names:
            raise ValueError("ZIP enthält kein event.json")
        event_payload = json.loads(zip_file.read("event.json"))
        entities = json.loads(zip_file.read("entities.json")) if "entities.json" in names else {}
        regs_payload = json.loads(zip_file.read("registrations.json")) if "registrations.json" in names else []
        snums_payload = json.loads(zip_file.read("start_numbers.json")) if "start_numbers.json" in names else {}
        schedule = json.loads(zip_file.read("schedule.json")) if "schedule.json" in names else {}

    external_id = event_payload.get("external_id")
    if not external_id:
        raise ValueError("event.external_id fehlt")
    result.external_id = external_id

    # 1) Event upsert
    event = Event.query.filter_by(external_id=external_id).first()
    if not event:
        event = Event(
            external_id=external_id,
            name=event_payload.get("name") or f"Importiert {external_id[:8]}",
            is_test=is_test,
            is_published=False,
        )
        db.session.add(event)
        result.created = True
    else:
        if event_payload.get("name"):
            event.name = event_payload["name"]
    if event_payload.get("location"):
        event.location = event_payload["location"]
    if event_payload.get("starts_at"):
        event.starts_at = _parse_datetime(event_payload["starts_at"])
    if event_payload.get("ends_at"):
        event.ends_at = _parse_datetime(event_payload["ends_at"])
    db.session.flush()
    result.event_id = event.id

    # 2) Persons upsert
    person_id_by_ext: dict[str, int] = {}
    for p in entities.get("persons", []):
        ext = p.get("external_id")
        if not ext:
            continue
        person = Person.query.filter_by(external_id=ext).first()
        if not person:
            person = Person(
                external_id=ext,
                first_name=(p.get("first_name") or "")[:100],
                last_name=(p.get("last_name") or "")[:100],
                email=(p.get("email") or None),
            )
            db.session.add(person)
        else:
            if p.get("first_name"):
                person.first_name = p["first_name"][:100]
            if p.get("last_name"):
                person.last_name = p["last_name"][:100]
            if p.get("email"):
                person.email = p["email"]
        db.session.flush()
        person_id_by_ext[ext] = person.id
    result.persons = len(person_id_by_ext)

    # 3) Dogs upsert (match via external_id ODER license_no als Fallback)
    dog_id_by_ext: dict[str, int] = {}
    for d in entities.get("dogs", []):
        ext = d.get("external_id")
        if not ext:
            continue
        dog = Dog.query.filter_by(external_id=ext).first()
        license_no = (d.get("license_no") or "").strip() or None
        if not dog and license_no:
            dog = Dog.query.filter_by(license_no=license_no).first()
            if dog and not dog.external_id:
                dog.external_id = ext
        if not dog:
            try:
                lk = LicenseKind(d.get("license_kind", "CH"))
            except ValueError:
                lk = LicenseKind.CH
            dog = Dog(
                external_id=ext,
                name=(d.get("name") or "Unbenannt")[:120],
                license_no=license_no or ext[:50],
                license_kind=lk,
            )
            db.session.add(dog)
        else:
            if d.get("name"):
                dog.name = d["name"][:120]
        db.session.flush()
        dog_id_by_ext[ext] = dog.id
    result.dogs = len(dog_id_by_ext)

    # 4) Replace: erst Children löschen (StartNumber, Result, EventFinalist),
    #    dann Registrations. MySQL erzwingt FK-Reihenfolge — SQLite tolerant,
    #    aber wir wollen beidseitig sauberes Verhalten.
    StartNumber.query.filter_by(event_id=event.id).delete(synchronize_session=False)
    Result.query.filter_by(event_id=event.id).delete(synchronize_session=False)
    EventFinalist.query.filter_by(event_id=event.id).delete(synchronize_session=False)
    db.session.flush()
    Registration.query.filter_by(event_id=event.id).delete(synchronize_session=False)
    db.session.flush()
    reg_id_by_ext: dict[str, int] = {}
    for r in regs_payload:
        ext = r.get("external_id")
        dog_id = dog_id_by_ext.get(r.get("dog_external_id"))
        handler_id = person_id_by_ext.get(r.get("handler_person_external_id"))
        if not dog_id:
            result.warnings.append(f"Registration {ext}: dog_external_id unbekannt — übersprungen")
            continue
        try:
            status = RegistrationStatus(r.get("status", "SUBMITTED"))
        except ValueError:
            status = RegistrationStatus.SUBMITTED
        try:
            tka_status = TkaEventCheckStatus(r.get("tka_event_check_status", "PENDING"))
        except ValueError:
            tka_status = TkaEventCheckStatus.PENDING
        reg = Registration(
            external_id=ext,
            event_id=event.id,
            dog_id=dog_id,
            handler_id=handler_id,
            category_code=r.get("category_code") or "Large",
            class_level=int(r.get("class_level") or 1),
            status=status,
            tka_event_check_status=tka_status,
            club_name=r.get("club_name"),
        )
        db.session.add(reg)
        db.session.flush()
        if ext:
            reg_id_by_ext[ext] = reg.id
    result.registrations = len(reg_id_by_ext)

    # 5) StartNumbers: schon vorher gelöscht (s. Schritt 4 — FK-Reihenfolge)
    for n in snums_payload.get("numbers", []):
        reg_id = reg_id_by_ext.get(n.get("registration_external_id"))
        start_no = n.get("start_no")
        if not reg_id or start_no is None:
            continue
        db.session.add(StartNumber(event_id=event.id, registration_id=reg_id, start_no=int(start_no)))
        result.start_numbers += 1
    if "locked" in snums_payload:
        event.start_numbers_locked = bool(snums_payload["locked"])

    # 6) ScheduleBlocks: replace (optional)
    ScheduleBlock.query.filter_by(event_id=event.id).delete(synchronize_session=False)
    for idx, b in enumerate(schedule.get("blocks", [])):
        db.session.add(ScheduleBlock(
            event_id=event.id,
            ring=(b.get("ring") or "1")[:50],
            start_at=_parse_datetime(b.get("start_at")),
            discipline=(b.get("discipline") or "")[:100],
            category_code=(b.get("category_code") or "")[:20],
            class_level=b.get("class_level"),
            notes=(b.get("notes") or "")[:1000],
            sort_index=idx,
        ))
        result.schedule_blocks += 1
    if "locked" in schedule:
        event.schedule_locked = bool(schedule["locked"])

    db.session.commit()
    return result
