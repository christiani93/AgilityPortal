"""Regression: Nachzügler-Startnummer darf keine Duplikate erzeugen.

Bug (HCS 2026-10-31): bei ``per_category`` (X0XX-Schema, klassenübergreifend)
nahm _next_start_number ``max()`` nur über die eine Klasse → max+1 kollidierte
mit einer anderen Klasse derselben Kategorie (2× Startnr 17 in Small).
"""
import json
from datetime import datetime

from app.extensions import db
from app.models import (
    Dog,
    Event,
    LicenseKind,
    Person,
    Registration,
    RegistrationStatus,
)
from app.blueprints.admin.routes_aoa_import import _next_start_number


def _reg(event, cat, cls, nr, n):
    dog = Dog(name=f"D{n}", license_no=f"{90000 + n}", license_kind=LicenseKind.CH,
              category=cat[0], class_level=cls)
    person = Person(first_name="H", last_name=f"X{n}")
    db.session.add_all([dog, person])
    reg = Registration(event=event, dog=dog, handler=person,
                        status=RegistrationStatus.SUBMITTED,
                        class_level=cls, category_code=cat, start_number=nr)
    db.session.add(reg)
    return reg


def test_next_start_number_per_category_no_duplicate(app):
    with app.app_context():
        event = Event(name="HCS Tunnel",
                      start_numbers_rule_set="per_category",
                      start_numbers_generated_at=datetime(2026, 10, 30, 8, 0),
                      startnumber_schema=json.dumps({"Small-1": 4001}))
        db.session.add(event)
        db.session.commit()

        # Small klassenübergreifend belegt: Kl.1 4001-4002, Kl.2 4003-4010, Kl.3 4011-4016
        n = 0
        for cls, (lo, hi) in {1: (4001, 4002), 2: (4003, 4010), 3: (4011, 4016)}.items():
            for nr in range(lo, hi + 1):
                n += 1
                _reg(event, "Small", cls, nr, n)
        db.session.commit()

        # Nachzügler in Kl.1: früher max(Kl.1)+1 = 4003 → Duplikat mit Kl.2.
        # Jetzt hinter dem GANZEN Kategorie-Band.
        nr = _next_start_number(event, "Small", 1)
        assert nr == 4017
        used = {r.start_number for r in Registration.query.filter_by(event_id=event.id)}
        assert nr not in used


def test_next_start_number_per_class_default(app):
    with app.app_context():
        event = Event(name="Normal",
                      start_numbers_generated_at=datetime(2026, 10, 30, 8, 0),
                      startnumber_schema=json.dumps({"Large-1": 1101}))
        db.session.add(event)
        db.session.commit()
        _reg(event, "Large", 1, 1101, 1)
        _reg(event, "Large", 1, 1102, 2)
        db.session.commit()
        # Default (pro Kat+Klasse): hinter dem Klassen-Band.
        assert _next_start_number(event, "Large", 1) == 1103


def test_next_start_number_none_before_generation(app):
    with app.app_context():
        event = Event(name="Noch nicht vergeben")
        db.session.add(event)
        db.session.commit()
        assert _next_start_number(event, "Large", 1) is None
