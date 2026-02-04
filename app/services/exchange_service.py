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
    LiveUpdate,
    Registration,
    Result,
    ResultImport,
    StartNumber,
    ScheduleBlock,
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

        if final and event:
            event.is_completed = True

        db.session.commit()
        return result_import


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
