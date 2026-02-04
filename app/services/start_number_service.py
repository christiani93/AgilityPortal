import json
import random
from datetime import datetime

from app.extensions import db
from app.models import Event, Registration, RegistrationStatus, StartNumber


def generate_start_numbers(event_id: int, mode: str, club_prio=None, seed=None) -> None:
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    if event.start_numbers_locked:
        raise ValueError("Start numbers are locked")

    registrations = Registration.query.filter_by(
        event_id=event_id, status=RegistrationStatus.SUBMITTED
    ).all()

    if seed is not None:
        random.seed(seed)

    if mode == "RANDOM":
        random.shuffle(registrations)
    elif mode == "CLUB_PRIO":
        if not club_prio:
            raise ValueError("club_prio required")
        club_mode = club_prio.get("mode")
        club_name = club_prio.get("club_name")
        if club_mode == "random_club_first":
            clubs = [reg.club_name for reg in registrations if reg.club_name]
            club_name = random.choice(clubs) if clubs else None
        if not club_name:
            random.shuffle(registrations)
        else:
            preferred = [reg for reg in registrations if reg.club_name == club_name]
            others = [reg for reg in registrations if reg.club_name != club_name]
            random.shuffle(preferred)
            random.shuffle(others)
            registrations = preferred + others
    else:
        raise ValueError("Unsupported mode")

    StartNumber.query.filter_by(event_id=event_id).delete()

    for index, registration in enumerate(registrations, start=1):
        db.session.add(
            StartNumber(
                event_id=event_id,
                registration_id=registration.id,
                start_no=index,
            )
        )

    event.start_numbers_generated_at = datetime.utcnow()
    event.start_numbers_rule_set = json.dumps(
        {"mode": mode, "club_prio": club_prio, "seed": seed}, ensure_ascii=False
    )
    db.session.commit()


def lock_start_numbers(event_id: int) -> None:
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    event.start_numbers_locked = True
    db.session.commit()


def unlock_start_numbers(event_id: int) -> None:
    event = Event.query.get(event_id)
    if not event:
        raise ValueError("Event not found")
    event.start_numbers_locked = False
    db.session.commit()


def set_start_number_manual(event_id: int, registration_id: int, new_start_no: int) -> None:
    if StartNumber.query.filter_by(event_id=event_id, start_no=new_start_no).first():
        raise ValueError("Start number already in use")

    entry = StartNumber.query.filter_by(event_id=event_id, registration_id=registration_id).first()
    if not entry:
        entry = StartNumber(event_id=event_id, registration_id=registration_id, start_no=new_start_no)
        db.session.add(entry)
    else:
        entry.start_no = new_start_no
    db.session.commit()
