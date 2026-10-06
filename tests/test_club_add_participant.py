"""
Tests für die Veranstalter-Teilnehmererfassung:
  - LIZ-Abfrage (registration_lookup)
  - Teilnehmer hinzufügen (registration_add) — Hund finden oder neu anlegen,
    Hundeführer anlegen, Registrierung bestätigt erstellen.
"""
from app.extensions import db
from app import models as M


def _seed():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()
    event = M.Event(name="Event", organiser_club_id=club.id,
                    allows_bitches_in_season=True)
    db.session.add(event)
    db.session.commit()
    return event.id, admin.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_add_new_participant_creates_dog_person_registration(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/registrations/add", data={
            "license_no": "123456",
            "dog_name": "Rex",
            "category": "L",
            "class_level": "3",
            "handler_first_name": "Max",
            "handler_last_name": "Muster",
            "club_name": "AC Muster",
            "is_in_season": "on",
        })
        assert resp.status_code == 302

        dog = db.session.execute(
            db.select(M.Dog).filter_by(license_no="123456")
        ).scalar_one()
        assert dog.name == "Rex"
        assert dog.license_kind == M.LicenseKind.CH
        assert dog.category == "L"

        reg = db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id, dog_id=dog.id)
        ).scalar_one()
        assert reg.status == M.RegistrationStatus.CONFIRMED
        assert reg.category_code == "Large"
        assert reg.class_level == 3
        assert reg.club_name == "AC Muster"
        assert reg.is_in_season is True
        assert reg.handler is not None
        assert reg.handler.last_name == "Muster"


def test_add_existing_dog_reuses_and_lookup_prefills(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        dog = M.Dog(name="Bella", license_no="777", license_kind=M.LicenseKind.CH,
                    category="M", class_level=2)
        db.session.add(dog)
        db.session.commit()
        dog_id = dog.id

        # Lookup findet den Hund und liefert Prefill-Daten
        resp = client.get(f"/club/events/{event_id}/registrations/lookup?license_no=777")
        data = resp.get_json()
        assert data["found"] is True
        assert data["dog_name"] == "Bella"
        assert data["category"] == "M"
        assert data["class_level"] == 2
        assert data["already_registered"] is False

        # Hinzufügen verwendet den bestehenden Hund (kein zweiter Hund)
        client.post(f"/club/events/{event_id}/registrations/add", data={
            "license_no": "777", "category": "M", "class_level": "2",
        })
        dogs = db.session.execute(
            db.select(M.Dog).filter_by(license_no="777")
        ).scalars().all()
        assert len(dogs) == 1
        reg = db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id, dog_id=dog_id)
        ).scalar_one()
        assert reg.status == M.RegistrationStatus.CONFIRMED

        # Lookup meldet jetzt "bereits angemeldet"
        resp = client.get(f"/club/events/{event_id}/registrations/lookup?license_no=777")
        assert resp.get_json()["already_registered"] is True


def test_add_duplicate_does_not_create_second_registration(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        payload = {"license_no": "555", "dog_name": "Fido",
                   "category": "S", "class_level": "1"}
        client.post(f"/club/events/{event_id}/registrations/add", data=payload)
        client.post(f"/club/events/{event_id}/registrations/add", data=payload)

        regs = db.session.execute(
            db.select(M.Registration).join(M.Dog)
            .filter(M.Dog.license_no == "555")
        ).scalars().all()
        assert len(regs) == 1


def test_lookup_unknown_license_returns_not_found(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)
        resp = client.get(f"/club/events/{event_id}/registrations/lookup?license_no=999999")
        assert resp.get_json()["found"] is False


def test_add_rejects_invalid_category(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)
        client.post(f"/club/events/{event_id}/registrations/add", data={
            "license_no": "222", "dog_name": "X", "category": "Z", "class_level": "1",
        })
        count = db.session.execute(
            db.select(db.func.count()).select_from(M.Registration)
        ).scalar()
        assert count == 0
