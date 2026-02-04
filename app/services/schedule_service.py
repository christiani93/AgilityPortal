from datetime import datetime, time

from sqlalchemy import func

from app.extensions import db
from app.models import Event, Registration, RegistrationStatus, ScheduleBlock


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
    db.session.commit()
    return block


def update_block(block_id, data):
    block = ScheduleBlock.query.get(block_id)
    if not block:
        raise ValueError("Block not found")
    event = Event.query.get(block.event_id)
    if event and event.schedule_locked:
        raise ValueError("Schedule is locked")

    for field in ["ring", "start_at", "discipline", "category_code", "class_level", "notes"]:
        if field in data:
            setattr(block, field, data[field])
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
        db.session.add(
            ScheduleBlock(
                event_id=event_id,
                ring="Ring 1",
                start_at=default_start,
                discipline=discipline,
                category_code=category_code,
                class_level=class_level,
                notes="",
                sort_index=sort_index,
            )
        )
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
