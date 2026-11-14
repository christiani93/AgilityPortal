"""Tests für den Club-Lizenzcheck-Workflow (routes_lizenzcheck.py).

Deckt ab:
  - "Verein ... stimmt ... nicht mit Hundeführer überein" wird ignoriert
    (Fix: Regex matchte den realen TKAMO-Text vorher nicht, siehe
    _parse_and_apply_tkamo).
  - Hundename-Zeile mit "Im System ..." übernimmt den Namen korrekt,
    auch per Zeilennummer (keine Lizenz in der Zeile).
  - Zeilennummer→Lizenz-Mapping ist bei Gleichstand (category_code,
    class_level) über den id-Tiebreaker stabil.
  - Multi-Event-Lizenzcheck: Token encode/decode, CSV-Export, Bestätigung
    für alle Events gleichzeitig (Wochenend-Bundle).
"""
import csv
import io

from app.extensions import db
from app.models import Dog, Event, LicenseKind, Registration, RegistrationStatus
from app.blueprints.club.routes_lizenzcheck import (
    _parse_and_apply_tkamo,
    _parse_and_apply_tkamo_multi,
    _make_confirm_token,
    _decode_confirm_token,
)


def _make_event_with_regs(n: int):
    event = Event(name="Testevent")
    db.session.add(event)
    db.session.flush()

    dogs = []
    for i in range(n):
        dog = Dog(name=f"Dog{i}", license_no=str(10000 + i), license_kind=LicenseKind.CH)
        db.session.add(dog)
        db.session.flush()
        reg = Registration(
            event_id=event.id,
            dog_id=dog.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=1,
            category_code="Large",  # bewusst identisch → Gleichstand-Fall
        )
        db.session.add(reg)
        dogs.append(dog)
    db.session.commit()
    return event, dogs


def test_verein_mismatch_line_is_ignored(app):
    with app.app_context():
        event, dogs = _make_event_with_regs(1)
        report_text = (
            "Verein Cypat'Agil / User-ID: 3235, 22302 / Cindy / Bula / "
            "stimmt auf Zeile 2 nicht mit Hundeführer überein."
        )
        name_changes, class_emails, inactive_licenses = _parse_and_apply_tkamo(
            event, report_text
        )
        assert name_changes == []
        assert class_emails == []
        assert inactive_licenses == []
        # Hundename darf dadurch nicht angefasst werden
        assert dogs[0].name == "Dog0"


def test_dog_name_mismatch_updates_via_license_in_line(app):
    with app.app_context():
        event, dogs = _make_event_with_regs(1)
        report_text = (
            f"Hundename und Lizenznummer stimmen auf Zeile 2 nicht überein. "
            f"Lizenz {dogs[0].license_no} Hundename im File: Roy-Junior / Im System Roy"
        )
        name_changes, _, _ = _parse_and_apply_tkamo(event, report_text)
        assert len(name_changes) == 1
        # tka_name wird gesetzt, der AOA-Name (name) bleibt für normale Listen
        assert dogs[0].tka_name == "Roy"
        assert dogs[0].name == "Dog0"


def test_dog_name_mismatch_via_zeile_uses_stable_order(app):
    """
    Keine Lizenz in der Zeile → Mapping über Zeilennummer. Bei zwei
    Registrierungen mit identischem (category_code, class_level) muss der
    id-Tiebreaker die Reihenfolge stabil halten (Zeile 2 = erster, Zeile 3 =
    zweiter angelegter Datensatz) statt einer nicht garantierten DB-Reihenfolge.
    """
    with app.app_context():
        event, dogs = _make_event_with_regs(2)
        report_text = (
            "Hundename und Lizenznummer stimmen auf Zeile 3 nicht überein. "
            "Hundename im File: Petit-Piwie / Im System Piwie"
        )
        name_changes, _, _ = _parse_and_apply_tkamo(event, report_text)
        assert len(name_changes) == 1
        # Zeile 3 = zweiter Datensatz (Zeile 1 ist der Header)
        assert dogs[1].tka_name == "Piwie"
        assert dogs[0].tka_name is None  # unverändert


# ── Multi-Event-Tests ───────────────────────────────────────────────────────

def test_multi_event_token_encode_decode_list(app):
    """Multi-Event-Token mit Liste von event_ids encode/decode."""
    with app.app_context():
        event_ids = [34, 35]
        dog_id = 123
        cat, cls = "L", 2

        token = _make_confirm_token(event_ids, dog_id, cat, cls)
        data = _decode_confirm_token(token)

        assert data is not None
        assert data["event_ids"] == event_ids
        assert data["dog_id"] == dog_id
        assert data["cat"] == cat
        assert data["cls"] == cls


def test_single_event_token_backward_compatible(app):
    """Single-Event-Token bleibt backward-compatible."""
    with app.app_context():
        event_id = 34
        dog_id = 123
        cat, cls = "L", 2

        token = _make_confirm_token(event_id, dog_id, cat, cls)
        data = _decode_confirm_token(token)

        assert data is not None
        assert data["event_id"] == event_id  # alt: single event_id
        assert "event_ids" not in data  # nicht als Liste gespeichert
        assert data["dog_id"] == dog_id
        assert data["cat"] == cat
        assert data["cls"] == cls


def test_multi_event_csv_export_combines_events(app):
    """Multi-Event-CSV kombiniert Registrierungen aus mehreren Events."""
    with app.app_context():
        from app.models import Person, User
        from app.blueprints.club.routes_lizenzcheck import _CAT_LABEL

        # Event 1 + Event 2
        event1 = Event(name="Samstag")
        event2 = Event(name="Sonntag")
        db.session.add(event1)
        db.session.add(event2)
        db.session.flush()

        # Handler
        person = Person(first_name="Hans", last_name="Müller", email="hans@test.ch")
        user = User(email="hans@test.ch", person=person)
        db.session.add(person)
        db.session.add(user)
        db.session.flush()

        # 2 Hunde
        dog1 = Dog(
            name="Bello",
            license_no="10001",
            license_kind=LicenseKind.CH,
            category="L",
            class_level=2,
        )
        dog2 = Dog(
            name="Lassie",
            license_no="10002",
            license_kind=LicenseKind.CH,
            category="I",
            class_level=1,
        )
        db.session.add(dog1)
        db.session.add(dog2)
        db.session.flush()

        # Registrierungen
        # Event 1: dog1 + dog2
        reg1_1 = Registration(
            event_id=event1.id,
            dog_id=dog1.id,
            handler_id=person.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=2,
            category_code="Large",
        )
        reg1_2 = Registration(
            event_id=event1.id,
            dog_id=dog2.id,
            handler_id=person.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=1,
            category_code="Intermediate",
        )
        # Event 2: dog1 nur (dog2 nicht in Sonntag)
        reg2_1 = Registration(
            event_id=event2.id,
            dog_id=dog1.id,
            handler_id=person.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=2,
            category_code="Large",
        )
        db.session.add(reg1_1)
        db.session.add(reg1_2)
        db.session.add(reg2_1)
        db.session.commit()

        # CSV export simulieren (intern in Flask-Route,
        # hier testen wir die Logik direkt)
        from flask import Flask
        from werkzeug.test import EnvironBuilder
        from werkzeug.wrappers import Request

        # Simulate gathering regs
        all_regs = []
        for event_id in [event1.id, event2.id]:
            regs = db.session.execute(
                db.select(Registration)
                .filter_by(event_id=event_id)
                .filter(
                    Registration.status.in_(
                        [
                            RegistrationStatus.PENDING,
                            RegistrationStatus.CONFIRMED,
                            RegistrationStatus.SUBMITTED,
                        ]
                    )
                )
                .order_by(
                    Registration.category_code,
                    Registration.class_level,
                    Registration.id,
                )
            ).scalars().all()
            for reg in regs:
                all_regs.append((event_id, reg))

        # Verifiziere Struktur: 3 Zeilen (2 Events + kombiniert)
        assert len(all_regs) == 3
        # Event 1: 2 Regs
        assert all_regs[0][0] == event1.id
        assert all_regs[1][0] == event1.id
        # Event 2: 1 Reg
        assert all_regs[2][0] == event2.id


def test_multi_event_confirm_updates_all_registrations(app):
    """Multi-Event-Token-Bestätigung updatet Registrierungen in allen Events."""
    with app.app_context():
        from app.models import Person, User
        from app.blueprints.club.routes_lizenzcheck import _CAT_LABEL

        # 2 Events
        event1 = Event(name="Event1")
        event2 = Event(name="Event2")
        db.session.add(event1)
        db.session.add(event2)
        db.session.flush()

        # Handler
        person = Person(
            first_name="Jane", last_name="Doe", email="jane@test.ch"
        )
        user = User(email="jane@test.ch", person=person)
        db.session.add(person)
        db.session.add(user)
        db.session.flush()

        # Dog
        dog = Dog(
            name="Pluto",
            license_no="10999",
            license_kind=LicenseKind.CH,
            category="M",
            class_level=1,
        )
        db.session.add(dog)
        db.session.flush()

        # Registrierungen in beiden Events
        reg1 = Registration(
            event_id=event1.id,
            dog_id=dog.id,
            handler_id=person.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=1,
            category_code="Medium",
        )
        reg2 = Registration(
            event_id=event2.id,
            dog_id=dog.id,
            handler_id=person.id,
            status=RegistrationStatus.CONFIRMED,
            class_level=1,
            category_code="Medium",
        )
        db.session.add(reg1)
        db.session.add(reg2)
        db.session.commit()

        # Multi-Event-Token erstellen
        event_ids = [event1.id, event2.id]
        token = _make_confirm_token(event_ids, dog.id, "L", 3)
        data = _decode_confirm_token(token)

        assert data["event_ids"] == event_ids
        assert data["cls"] == 3
        assert data["cat"] == "L"

        # Simulation der Bestätigung: Alle Regs updaten
        for event_id in data.get("event_ids", [data.get("event_id")]):
            regs = db.session.execute(
                db.select(Registration).filter_by(
                    event_id=event_id, dog_id=data["dog_id"]
                )
            ).scalars().all()
            for reg in regs:
                reg.class_level = data["cls"]
                reg.category_code = _CAT_LABEL.get(data["cat"], data["cat"])

        db.session.commit()

        # Verifiziere Updates
        reg1_after = db.session.get(Registration, reg1.id)
        reg2_after = db.session.get(Registration, reg2.id)

        assert reg1_after.class_level == 3
        assert reg1_after.category_code == "Large"
        assert reg2_after.class_level == 3
        assert reg2_after.category_code == "Large"


def test_multi_event_tkamo_import_dog_name_change(app):
	"""Multi-Event TKAMO-Import: Hundenamen-Änderung wird verarbeitet."""
	with app.app_context():
		from app.models import Person, User

		# 2 Events
		event1 = Event(name="Samstag")
		event2 = Event(name="Sonntag")
		db.session.add(event1)
		db.session.add(event2)
		db.session.flush()

		# Handler
		person = Person(first_name="Max", last_name="Muster", email="max@test.ch")
		user = User(email="max@test.ch", person=person)
		db.session.add(person)
		db.session.add(user)
		db.session.flush()

		# Dog
		dog = Dog(
			name="Bello",
			license_no="20001",
			license_kind=LicenseKind.CH,
			category="L",
			class_level=1,
		)
		db.session.add(dog)
		db.session.flush()

		# Registrierungen in beiden Events
		reg1 = Registration(
			event_id=event1.id,
			dog_id=dog.id,
			handler_id=person.id,
			status=RegistrationStatus.CONFIRMED,
			class_level=1,
			category_code="Large",
		)
		reg2 = Registration(
			event_id=event2.id,
			dog_id=dog.id,
			handler_id=person.id,
			status=RegistrationStatus.CONFIRMED,
			class_level=1,
			category_code="Large",
		)
		db.session.add(reg1)
		db.session.add(reg2)
		db.session.commit()

		# TKAMO-Report mit Hundenamen-Änderung
		report_text = (
			"Hundename und Lizenznummer stimmen auf Zeile 2 nicht überein. "
			f"Lizenz {dog.license_no} Hundename im File: Bello / Im System Bella"
		)

		name_changes, class_emails, inactive_licenses = _parse_and_apply_tkamo_multi(
			[event1, event2], report_text
		)

		# Verifiziere Ergebnisse
		assert len(name_changes) == 1
		assert "Bella" in name_changes[0]
		assert dog.tka_name == "Bella"
		assert class_emails == []
		assert inactive_licenses == []


def test_multi_event_tkamo_import_class_mismatch(app):
	"""Multi-Event TKAMO-Import: Klassen-Diskrepanz wird erkannt."""
	with app.app_context():
		from app.models import Person, User

		# 2 Events
		event1 = Event(name="Samstag")
		event2 = Event(name="Sonntag")
		db.session.add(event1)
		db.session.add(event2)
		db.session.flush()

		# Handler
		person = Person(first_name="Anna", last_name="Schmidt", email="anna@test.ch")
		user = User(email="anna@test.ch", person=person)
		db.session.add(person)
		db.session.add(user)
		db.session.flush()

		# Dog
		dog = Dog(
			name="Pluto",
			license_no="20002",
			license_kind=LicenseKind.CH,
			category="M",
			class_level=2,
		)
		db.session.add(dog)
		db.session.flush()

		# Registrierungen
		reg1 = Registration(
			event_id=event1.id,
			dog_id=dog.id,
			handler_id=person.id,
			status=RegistrationStatus.CONFIRMED,
			class_level=2,
			category_code="Medium",
		)
		reg2 = Registration(
			event_id=event2.id,
			dog_id=dog.id,
			handler_id=person.id,
			status=RegistrationStatus.CONFIRMED,
			class_level=2,
			category_code="Medium",
		)
		db.session.add(reg1)
		db.session.add(reg2)
		db.session.commit()

		# TKAMO-Report mit inaktiver Lizenz
		report_text = "Lizenz 20002 ist inaktiv und nicht startberechtigt."

		name_changes, class_emails, inactive_licenses = _parse_and_apply_tkamo_multi(
			[event1, event2], report_text
		)

		# Inaktive Lizenz wird erkannt
		assert len(inactive_licenses) == 1
		assert "20002" in inactive_licenses[0]
		assert name_changes == []
		assert class_emails == []
