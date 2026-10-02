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
from app.blueprints.club.schedule_utils import (
    compute_detailed_segments,
    compute_timeline,
)


class _StubBlock:
    """Leichtgewichtiger ScheduleBlock-Ersatz für die reinen Timeline-Funktionen."""

    def __init__(self, id, discipline, class_level, count, sort_index,
                 skip_changeover=False, skip_briefing=False):
        self.id = id
        self.discipline = discipline
        self.class_level = class_level
        self.category_code = "Large"
        self.block_type = "run"
        self.sort_index = sort_index
        self.title = None
        self.judge = None
        self._participant_count = count
        self._display_title = f"{discipline} Large Kl. {class_level}"
        self.skip_changeover = skip_changeover
        self.skip_briefing = skip_briefing


def _two_group_blocks():
    # Gruppe 1 (agility) normal, Gruppe 2 (open) ohne Umbau/Briefing
    return {
        "Ring 1": [
            _StubBlock(1, "agility", 1, 10, 0),
            _StubBlock(2, "open", 1, 10, 10,
                       skip_changeover=True, skip_briefing=True),
        ]
    }


def test_timeline_skip_removes_changeover_and_briefing():
    tl = compute_timeline(_two_group_blocks(), {"Ring 1": "08:00"}, "2026-05-10")
    first, second = tl["Ring 1"]
    # Erste Gruppe rechnet Umbau + Briefing ein
    assert first["changeover_min"] > 0
    assert first["briefing_min"] > 0
    # Zweite Gruppe (Open) weder Umbau noch Briefing
    assert second["changeover_min"] == 0
    assert second["briefing_min"] == 0
    # Lückenlos: Open startet, wenn Agility endet (kein Umbau-/Briefing-Loch)
    assert second["start_time"] == first["end_time"]


def test_detailed_segments_skip_omits_umbau_briefing():
    segs = compute_detailed_segments(_two_group_blocks(), {"Ring 1": "08:00"}, "2026-05-10")
    seg_types = {(s["segment"], s["block"].discipline) for s in segs["Ring 1"]}
    assert ("changeover", "agility") in seg_types
    assert ("briefing", "agility") in seg_types
    assert ("changeover", "open") not in seg_types
    assert ("briefing", "open") not in seg_types
    assert ("run", "open") in seg_types


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
