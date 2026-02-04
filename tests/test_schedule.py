from datetime import datetime
import io
import json
import zipfile

from app.extensions import db
from app.models import Event, Registration, RegistrationStatus, ScheduleBlock
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
        reg1 = Registration(
            event=event,
            status=RegistrationStatus.SUBMITTED,
            class_level=1,
            category_code="Large",
        )
        reg2 = Registration(
            event=event,
            status=RegistrationStatus.SUBMITTED,
            class_level=2,
            category_code="Large",
        )
        reg3 = Registration(
            event=event,
            status=RegistrationStatus.SUBMITTED,
            class_level=1,
            category_code="Small",
        )
        db.session.add_all([event, reg1, reg2, reg3])
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
