from datetime import datetime
import io
import json
import zipfile

from app.extensions import db
from app.models import Dog, Event, LicenseKind, Person, Registration, RegistrationStatus, ScheduleBlock
from app.services.exchange_service import build_event_export_zip
from app.services.schedule_service import (
    add_block,
    auto_generate_blocks_from_registrations,
    delete_block,
    list_blocks,
    update_block,
)


def test_add_update_delete_block(app):
    with app.app_context():
        event = Event(name="Schedule Event")
        db.session.add(event)
        db.session.commit()

        block = add_block(
            event.id,
            {
                "ring": "Ring 1",
                "start_at": datetime(2026, 5, 10, 8, 0),
                "discipline": "Agility",
                "category_code": "Large",
                "class_level": 1,
                "notes": "Test",
            },
        )
        assert block.id

        update_block(block.id, {"notes": "Updated"})
        updated = ScheduleBlock.query.get(block.id)
        assert updated.notes == "Updated"

        delete_block(block.id)
        assert ScheduleBlock.query.get(block.id) is None


def test_auto_generate_blocks_creates_unique_combinations(app):
    with app.app_context():
        event = Event(name="Schedule Event")

        counter = {"n": 0}

        def _make_reg(class_level, category):
            counter["n"] += 1
            n = counter["n"]
            dog = Dog(name=f"D_{n}", license_no=f"{20000 + n}",
                      license_kind=LicenseKind.CH)
            person = Person(first_name="HF", last_name=f"X_{n}")
            return Registration(event=event, dog=dog, handler=person,
                                status=RegistrationStatus.SUBMITTED,
                                class_level=class_level, category_code=category)

        reg1 = _make_reg(1, "Large")
        reg2 = _make_reg(2, "Large")
        reg3 = _make_reg(1, "Small")
        db.session.add(event)
        for reg in [reg1, reg2, reg3]:
            db.session.add(reg.dog)
            db.session.add(reg.handler)
            db.session.add(reg)
        db.session.commit()

        auto_generate_blocks_from_registrations(event.id)
        blocks = list_blocks(event.id)
        combos = {(b.category_code, b.class_level) for b in blocks}
        assert combos == {("Large", 1), ("Large", 2), ("Small", 1)}


def test_export_includes_schedule_json(app):
    with app.app_context():
        event = Event(name="Schedule Export")
        db.session.add(event)
        db.session.commit()

        add_block(
            event.id,
            {
                "ring": "Ring 1",
                "start_at": datetime(2026, 5, 10, 8, 0),
                "discipline": "Agility",
                "category_code": "Large",
                "class_level": 1,
                "notes": "",
            },
        )
        zip_bytes, _, _ = build_event_export_zip(event.id)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            payload = json.loads(zip_file.read("schedule.json"))
        assert payload["blocks"]
