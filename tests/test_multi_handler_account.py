"""Mehr-Läufer-Konto: ein Account verwaltet mehrere Läufer (Personen), wählt bei
der Anmeldung den Läufer, und der Verein wird pro Läufer übernommen."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_account():
    person = M.Person(first_name="Haupt", last_name="Konto")
    db.session.add(person)
    db.session.flush()
    user = M.User(email="konto@test.ch", role="handler", person_id=person.id)
    person.account_user_id = user.id
    db.session.add(user)
    db.session.commit()
    return user.id


def test_add_handler_appears_in_account(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club = M.Club(vereinsnummer="4242", name="Testclub")
        db.session.add(club)
        db.session.flush()
        user_id = _seed_account()
        client = app.test_client()
        _login(client, user_id)

        r = client.post("/club/profile/handlers", data={
            "first_name": "Kind", "last_name": "Konto", "club_id": str(club.id),
        }, follow_redirects=True)
        assert r.status_code == 200

        user = db.session.get(M.User, user_id)
        names = {f"{p.first_name} {p.last_name}" for p in user.handlers}
        assert "Haupt Konto" in names and "Kind Konto" in names
        kid = next(p for p in user.handlers if p.first_name == "Kind")
        assert kid.account_user_id == user_id
        assert kid.club_id == club.id


def test_registration_uses_selected_handler_and_club(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club = M.Club(vereinsnummer="5050", name="Zweitclub")
        db.session.add(club)
        db.session.flush()
        user_id = _seed_account()
        user = db.session.get(M.User, user_id)

        # Zweiter Läufer mit Verein
        kid = M.Person(first_name="Kind", last_name="Konto",
                       account_user_id=user_id, club_id=club.id)
        dog = M.Dog(name="Rex", license_no="7777", license_kind=M.LicenseKind.CH,
                    category="L", class_level=1)
        event = M.Event(name="Turnier", status="open", is_test=True)
        db.session.add_all([kid, dog, event])
        db.session.flush()
        # Hund gehört dem Hauptkonto, soll aber vom Kind geführt werden
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=user.person_id,
                                  role=M.DogOwnerRole.OWNER))
        db.session.commit()
        kid_id, dog_id, event_id = kid.id, dog.id, event.id

        client = app.test_client()
        _login(client, user_id)

        # Hund ist über das Konto sichtbar (aggregiert über alle Läufer)
        assert dog_id in [d.id for d in db.session.get(M.User, user_id).dogs]

        r = client.post(f"/club/events/{event_id}/view", data={
            "dog_id": str(dog_id), "handler_id": str(kid_id), "class_level": "1",
        }, follow_redirects=True)
        assert r.status_code == 200

        reg = db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id, dog_id=dog_id)
        ).scalar_one()
        assert reg.handler_id == kid_id
        assert reg.club_name == "5050"


def test_cannot_register_foreign_handler(app):
    """handler_id, der nicht zum Konto gehört → Fallback auf eigene Person."""
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id = _seed_account()
        user = db.session.get(M.User, user_id)
        other_person = M.Person(first_name="Fremd", last_name="Person")
        dog = M.Dog(name="Fido", license_no="8888", license_kind=M.LicenseKind.CH,
                    category="L", class_level=1)
        event = M.Event(name="T2", status="open", is_test=True)
        db.session.add_all([other_person, dog, event])
        db.session.flush()
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=user.person_id,
                                  role=M.DogOwnerRole.OWNER))
        db.session.commit()
        other_id, dog_id, event_id = other_person.id, dog.id, event.id

        client = app.test_client()
        _login(client, user_id)
        client.post(f"/club/events/{event_id}/view", data={
            "dog_id": str(dog_id), "handler_id": str(other_id), "class_level": "1",
        }, follow_redirects=True)
        reg = db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id, dog_id=dog_id)
        ).scalar_one()
        assert reg.handler_id == db.session.get(M.User, user_id).person_id
