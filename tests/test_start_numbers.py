import io
import json
import zipfile

from app.extensions import db
from app.models import Dog, Event, LicenseKind, Person, Registration, RegistrationStatus, StartNumber
from app.services.exchange_service import build_event_export_zip
from app.services.start_number_service import (
    generate_start_numbers,
    set_start_number_manual,
)


def _setup_event_with_regs():
    event = Event(name="Start Number Event")
    clubs = ["Alpha", "Beta", "Alpha"]
    registrations = []
    for i, club in enumerate(clubs, start=1):
        dog = Dog(name=f"Dog_{i}", license_no=f"{10000 + i}", license_kind=LicenseKind.CH)
        person = Person(first_name=f"HF{i}", last_name=f"Name{i}")
        registrations.append(Registration(
            event=event,
            dog=dog,
            handler=person,
            status=RegistrationStatus.SUBMITTED,
            class_level=1,
            category_code="Large",
            club_name=club,
        ))
    db.session.add(event)
    for reg in registrations:
        db.session.add(reg.dog)
        db.session.add(reg.handler)
        db.session.add(reg)
    db.session.commit()
    return event, registrations


def test_generate_random_unique_numbers(app):
    with app.app_context():
        event, registrations = _setup_event_with_regs()
        generate_start_numbers(event_id=event.id, mode="RANDOM", club_prio=None, seed=42)
        numbers = StartNumber.query.filter_by(event_id=event.id).all()
        assert len(numbers) == len(registrations)
        assert len({entry.start_no for entry in numbers}) == len(registrations)


def test_generate_club_first_places_club_first(app):
    with app.app_context():
        event, registrations = _setup_event_with_regs()
        generate_start_numbers(
            event_id=event.id,
            mode="CLUB_PRIO",
            club_prio={"mode": "club_first", "club_name": "Alpha"},
            seed=1,
        )
        numbers = (
            StartNumber.query.filter_by(event_id=event.id)
            .order_by(StartNumber.start_no)
            .all()
        )
        reg_map = {reg.id: reg for reg in registrations}
        first_two = [reg_map[entry.registration_id].club_name for entry in numbers[:2]]
        assert first_two == ["Alpha", "Alpha"]


def test_manual_set_rejects_duplicate_start_no(app):
    with app.app_context():
        event, registrations = _setup_event_with_regs()
        generate_start_numbers(event_id=event.id, mode="RANDOM", club_prio=None, seed=3)
        first = registrations[0]
        second = registrations[1]
        first_entry = StartNumber.query.filter_by(event_id=event.id, registration_id=first.id).first()
        try:
            set_start_number_manual(event_id=event.id, registration_id=second.id, new_start_no=first_entry.start_no)
        except ValueError as exc:
            assert "already in use" in str(exc)
        else:
            assert False, "Expected ValueError for duplicate start_no"


def test_export_includes_start_numbers_json(app):
    with app.app_context():
        event, _ = _setup_event_with_regs()
        generate_start_numbers(event_id=event.id, mode="RANDOM", club_prio=None, seed=5)
        zip_bytes, _, _ = build_event_export_zip(event.id)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            payload = json.loads(zip_file.read("start_numbers.json"))
        assert payload["event_external_id"]
        assert payload["numbers"]
