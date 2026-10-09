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


def _seed_registration(event_id, category="M", class_level=2):
    dog = M.Dog(name="Bello", license_no="4242", license_kind=M.LicenseKind.CH,
                category=category, class_level=class_level)
    db.session.add(dog)
    db.session.flush()
    reg = M.Registration(event_id=event_id, dog_id=dog.id,
                         category_code="Medium", class_level=class_level,
                         status=M.RegistrationStatus.CONFIRMED)
    db.session.add(reg)
    db.session.commit()
    return reg.id, dog.id


def test_organiser_set_class_updates_only_registration(app):
    with app.app_context():
        event_id, admin_id = _seed()
        reg_id, dog_id = _seed_registration(event_id)
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/registrations/{reg_id}/class", data={
            "category": "L", "class_level": "3",
        })
        assert resp.status_code == 302

        reg = db.session.get(M.Registration, reg_id)
        assert reg.category_code == "Large"
        assert reg.class_level == 3
        # Stammdaten des Hundes bleiben unberührt, solange update_dog fehlt
        dog = db.session.get(M.Dog, dog_id)
        assert dog.category == "M"
        assert dog.class_level == 2


def test_organiser_set_class_can_update_dog_master(app):
    with app.app_context():
        event_id, admin_id = _seed()
        reg_id, dog_id = _seed_registration(event_id)
        client = app.test_client()
        _login(client, admin_id)

        client.post(f"/club/registrations/{reg_id}/class", data={
            "category": "S", "class_level": "1", "update_dog": "on",
        })
        reg = db.session.get(M.Registration, reg_id)
        dog = db.session.get(M.Dog, dog_id)
        assert reg.category_code == "Small" and reg.class_level == 1
        assert dog.category == "S" and dog.class_level == 1


def test_organiser_set_class_rejects_invalid(app):
    with app.app_context():
        event_id, admin_id = _seed()
        reg_id, _ = _seed_registration(event_id)
        client = app.test_client()
        _login(client, admin_id)

        client.post(f"/club/registrations/{reg_id}/class", data={
            "category": "Z", "class_level": "9",
        })
        reg = db.session.get(M.Registration, reg_id)
        assert reg.category_code == "Medium" and reg.class_level == 2


def _seed_registration_with_handler(event_id):
    person = M.Person(first_name="Hans", last_name="Meier")
    dog = M.Dog(name="Rocky", license_no="5151", license_kind=M.LicenseKind.CH,
                category="L", class_level=3)
    db.session.add_all([person, dog])
    db.session.flush()
    reg = M.Registration(event_id=event_id, dog_id=dog.id, handler_id=person.id,
                         category_code="Large", class_level=3,
                         status=M.RegistrationStatus.CONFIRMED)
    db.session.add(reg)
    db.session.commit()
    return reg.id, dog.id, person.id


def test_rename_updates_dog_and_handler(app):
    with app.app_context():
        event_id, admin_id = _seed()
        reg_id, dog_id, person_id = _seed_registration_with_handler(event_id)
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/registrations/{reg_id}/rename", data={
            "dog_name": "Rocky II",
            "handler_first_name": "Johann",
            "handler_last_name": "Meyer",
        })
        assert resp.status_code == 302
        assert db.session.get(M.Dog, dog_id).name == "Rocky II"
        person = db.session.get(M.Person, person_id)
        assert person.first_name == "Johann"
        assert person.last_name == "Meyer"
        # Startnummer/Anmeldung unberührt
        reg = db.session.get(M.Registration, reg_id)
        assert reg.status == M.RegistrationStatus.CONFIRMED


def test_rename_without_handler_only_dog(app):
    with app.app_context():
        event_id, admin_id = _seed()
        reg_id, dog_id = _seed_registration(event_id)  # ohne handler
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/registrations/{reg_id}/rename", data={
            "dog_name": "Bello II",
            "handler_first_name": "Egal",
            "handler_last_name": "Egal",
        })
        assert resp.status_code == 302
        assert db.session.get(M.Dog, dog_id).name == "Bello II"


def test_rename_denied_for_foreign_club(app):
    with app.app_context():
        event_id, _ = _seed()
        reg_id, dog_id, _p = _seed_registration_with_handler(event_id)
        other_club = M.Club(vereinsnummer="V2", name="Other")
        db.session.add(other_club)
        db.session.flush()
        other = M.User(email="other2@test.ch", role="club_admin", club_id=other_club.id)
        db.session.add(other)
        db.session.commit()
        client = app.test_client()
        _login(client, other.id)

        resp = client.post(f"/club/registrations/{reg_id}/rename", data={
            "dog_name": "Hacked",
        })
        assert resp.status_code == 403
        assert db.session.get(M.Dog, dog_id).name == "Rocky"


def test_organiser_set_class_denied_for_foreign_club(app):
    with app.app_context():
        event_id, _ = _seed()
        reg_id, _dog = _seed_registration(event_id)
        # Veranstalter eines anderen Vereins darf nicht ändern
        other_club = M.Club(vereinsnummer="V2", name="Other")
        db.session.add(other_club)
        db.session.flush()
        other = M.User(email="other@test.ch", role="club_admin", club_id=other_club.id)
        db.session.add(other)
        db.session.commit()
        client = app.test_client()
        _login(client, other.id)

        resp = client.post(f"/club/registrations/{reg_id}/class", data={
            "category": "L", "class_level": "3",
        })
        assert resp.status_code == 403
        reg = db.session.get(M.Registration, reg_id)
        assert reg.category_code == "Medium"
