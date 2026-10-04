"""Tests für den Club-Lizenzcheck-Workflow (routes_lizenzcheck.py).

Deckt ab:
  - "Verein ... stimmt ... nicht mit Hundeführer überein" wird ignoriert
    (Fix: Regex matchte den realen TKAMO-Text vorher nicht, siehe
    _parse_and_apply_tkamo).
  - Hundename-Zeile mit "Im System ..." übernimmt den Namen korrekt,
    auch per Zeilennummer (keine Lizenz in der Zeile).
  - Zeilennummer→Lizenz-Mapping ist bei Gleichstand (category_code,
    class_level) über den id-Tiebreaker stabil.
"""
from app.extensions import db
from app.models import Dog, Event, LicenseKind, Registration, RegistrationStatus
from app.blueprints.club.routes_lizenzcheck import _parse_and_apply_tkamo


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
        assert dogs[0].name == "Roy"


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
        assert dogs[1].name == "Piwie"
        assert dogs[0].name == "Dog0"  # unverändert
