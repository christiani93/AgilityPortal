from datetime import datetime, time

from sqlalchemy import func

from app.extensions import db
from app.models import Event, EventRun, Registration, RegistrationStatus, ScheduleBlock


_CODE_MAP = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}
_CODE_CATEGORY_MAP = {v: k for k, v in _CODE_MAP.items()}


def link_block_to_run(block):
    """Verknüpft einen Lauf-Block mit seinem fachlichen EventRun (find-or-create).

    Der Richter wird kanonisch am EventRun gehalten; der Block leitet ihn über
    event_run_id ab. Ersetzt den früheren Composite-Key-Match und hält Zeitplan
    und Läufe-Liste konsistent. EventRun.run_type ist lowercase-kanonisch.
    """
    # block_type-Default ("run") wird erst beim Flush gesetzt → None hier als
    # Lauf behandeln. Rank-Blöcke setzen block_type explizit und haben keine
    # discipline, fallen also über die discipline-Prüfung raus.
    if block.block_type not in (None, "run") or not block.discipline:
        return None
    run_type = (block.discipline or "").lower()
    category = _CODE_CATEGORY_MAP.get(block.category_code, block.category_code)
    run = EventRun.query.filter_by(
        event_id=block.event_id, run_type=run_type,
        category=category, class_level=block.class_level, is_final=False,
    ).first()
    if run is None:
        run = EventRun(
            event_id=block.event_id, run_type=run_type,
            category=category, class_level=block.class_level, is_final=False,
        )
        db.session.add(run)
        db.session.flush()   # id für event_run_id
    block.event_run = run
    return run


def list_blocks(event_id):
    return (
        ScheduleBlock.query.filter_by(event_id=event_id)
        .order_by(ScheduleBlock.sort_index, ScheduleBlock.start_at)
        .all()
    )


def add_block(event_id, data):
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    if event.schedule_locked:
        raise ValueError("Schedule is locked")

    max_sort = (
        db.session.query(func.max(ScheduleBlock.sort_index))
        .filter_by(event_id=event_id)
        .scalar()
    )
    next_sort = (max_sort or 0) + 1
    block = ScheduleBlock(
        event_id=event_id,
        ring=data.get("ring") or "Ring 1",
        start_at=data.get("start_at"),
        discipline=data.get("discipline") or "Agility",
        category_code=data.get("category_code"),
        class_level=data.get("class_level"),
        notes=data.get("notes"),
        sort_index=next_sort,
    )
    db.session.add(block)
    link_block_to_run(block)
    db.session.commit()
    return block


def update_block(block_id, data):
    block = ScheduleBlock.query.get(block_id)
    if not block:
        raise ValueError("Block not found")
    event = Event.query.get(block.event_id)
    if event and event.schedule_locked:
        raise ValueError("Schedule is locked")

    relink_fields = {"discipline", "category_code", "class_level"}
    changed_run_key = False
    for field in ["ring", "start_at", "discipline", "category_code", "class_level", "notes"]:
        if field in data:
            if field in relink_fields and data[field] != getattr(block, field):
                changed_run_key = True
            setattr(block, field, data[field])
    if changed_run_key:
        link_block_to_run(block)   # auf den jetzt passenden Lauf umhängen
    db.session.commit()
    return block


def delete_block(block_id):
    block = ScheduleBlock.query.get(block_id)
    if not block:
        raise ValueError("Block not found")
    event = Event.query.get(block.event_id)
    if event and event.schedule_locked:
        raise ValueError("Schedule is locked")
    db.session.delete(block)
    db.session.commit()


def move_block(block_id, direction):
    block = ScheduleBlock.query.get(block_id)
    if not block:
        raise ValueError("Block not found")
    event = Event.query.get(block.event_id)
    if event and event.schedule_locked:
        raise ValueError("Schedule is locked")

    if direction not in {"up", "down"}:
        raise ValueError("Invalid direction")

    comparator = ScheduleBlock.sort_index < block.sort_index if direction == "up" else ScheduleBlock.sort_index > block.sort_index
    order = ScheduleBlock.sort_index.desc() if direction == "up" else ScheduleBlock.sort_index.asc()
    neighbor = (
        ScheduleBlock.query.filter_by(event_id=block.event_id)
        .filter(comparator)
        .order_by(order)
        .first()
    )
    if not neighbor:
        return

    block.sort_index, neighbor.sort_index = neighbor.sort_index, block.sort_index
    db.session.commit()


def auto_generate_blocks_from_registrations(event_id):
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    if event.schedule_locked:
        raise ValueError("Schedule is locked")

    registrations = Registration.query.filter_by(
        event_id=event_id, status=RegistrationStatus.SUBMITTED
    ).all()

    combos = set()
    for registration in registrations:
        combos.add(("Agility", registration.category_code, registration.class_level))

    if event.starts_at:
        default_start = event.starts_at.replace(hour=8, minute=0, second=0, microsecond=0)
    else:
        base_date = datetime.utcnow().date()
        default_start = datetime.combine(base_date, time(hour=8))

    ScheduleBlock.query.filter_by(event_id=event_id).delete()

    sort_index = 1
    for discipline, category_code, class_level in sorted(combos):
        block = ScheduleBlock(
            event_id=event_id,
            ring="Ring 1",
            start_at=default_start,
            discipline=discipline,
            category_code=category_code,
            class_level=class_level,
            notes="",
            sort_index=sort_index,
        )
        db.session.add(block)
        link_block_to_run(block)
        sort_index += 1

    db.session.commit()


def lock_schedule(event_id):
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    event.schedule_locked = True
    db.session.commit()


def unlock_schedule(event_id):
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    event.schedule_locked = False
    db.session.commit()
