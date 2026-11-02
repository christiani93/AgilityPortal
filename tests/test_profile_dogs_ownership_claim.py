"""Besitzer-Übernahme fuer bereits bestehende, ownerlose Hunde (z.B. aus
AOA-Import) ueber /club/profile/dogs per bekannter Lizenznummer."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _make_user(email, first, last):
    person = M.Person(first_name=first, last_name=last)
    db.session.add(person)
    db.session.flush()
    user = M.User(email=email, role="handler", person_id=person.id)
    db.session.add(user)
    db.session.commit()
    return user.id


def test_claims_ownership_of_orphaned_dog(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        dog = M.Dog(name="Smash", license_no="55512", license_kind=M.LicenseKind.CH,
                    category="M", class_level=1)
        db.session.add(dog)
        db.session.commit()
        dog_id = dog.id

        user_id = _make_user("owner@test.ch", "Erika", "Muster")
        client = app.test_client()
        _login(client, user_id)

        r = client.post("/club/profile/dogs", data={
            "name": "Smash", "license_kind": "CH", "license_no": "55512",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "Besitzer".encode("utf-8") in r.data

        link = db.session.execute(
            db.select(M.DogOwner).filter_by(dog_id=dog_id)
        ).scalar_one()
        assert link.role == M.DogOwnerRole.OWNER


def test_second_claimant_becomes_handler_not_owner(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        owner_person = M.Person(first_name="Erika", last_name="Muster")
        db.session.add(owner_person)
        db.session.flush()
        dog = M.Dog(name="Smash", license_no="55512", license_kind=M.LicenseKind.CH,
                    category="M", class_level=1)
        db.session.add(dog)
        db.session.flush()
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=owner_person.id,
                                   role=M.DogOwnerRole.OWNER))
        db.session.commit()
        dog_id = dog.id

        other_user_id = _make_user("handler@test.ch", "Hans", "Beispiel")
        client = app.test_client()
        _login(client, other_user_id)

        r = client.post("/club/profile/dogs", data={
            "name": "Smash", "license_kind": "CH", "license_no": "55512",
        }, follow_redirects=True)
        assert r.status_code == 200
        assert "Hundeführer".encode("utf-8") in r.data

        links = db.session.execute(
            db.select(M.DogOwner).filter_by(dog_id=dog_id)
        ).scalars().all()
        roles = [l.role for l in links]
        assert M.DogOwnerRole.OWNER in roles
        assert M.DogOwnerRole.HANDLER in roles
        assert len(links) == 2


def test_owner_can_update_name_and_breed(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        owner_person = M.Person(first_name="Erika", last_name="Muster")
        db.session.add(owner_person)
        db.session.flush()
        dog = M.Dog(name="Smash", license_no="55512", license_kind=M.LicenseKind.CH,
                    category="M", class_level=1)
        db.session.add(dog)
        db.session.flush()
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=owner_person.id,
                                   role=M.DogOwnerRole.OWNER))
        db.session.commit()
        owner_user = M.User(email="owner2@test.ch", role="handler", person_id=owner_person.id)
        db.session.add(owner_user)
        db.session.commit()
        dog_id, owner_user_id = dog.id, owner_user.id

        client = app.test_client()
        _login(client, owner_user_id)
        r = client.post(f"/club/profile/dogs/{dog_id}/details", data={
            f"dog_{dog_id}-name": "Smash II", f"dog_{dog_id}-breed": "Border Collie",
        }, follow_redirects=True)
        assert r.status_code == 200

        dog = db.session.get(M.Dog, dog_id)
        assert dog.name == "Smash II"
        assert dog.breed == "Border Collie"


def test_handler_cannot_update_name_and_breed(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        owner_person = M.Person(first_name="Erika", last_name="Muster")
        handler_person = M.Person(first_name="Hans", last_name="Beispiel")
        db.session.add_all([owner_person, handler_person])
        db.session.flush()
        dog = M.Dog(name="Smash", license_no="55512", license_kind=M.LicenseKind.CH,
                    category="M", class_level=1)
        db.session.add(dog)
        db.session.flush()
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=owner_person.id,
                                   role=M.DogOwnerRole.OWNER))
        db.session.add(M.DogOwner(dog_id=dog.id, person_id=handler_person.id,
                                   role=M.DogOwnerRole.HANDLER))
        db.session.commit()
        handler_user = M.User(email="handler2@test.ch", role="handler", person_id=handler_person.id)
        db.session.add(handler_user)
        db.session.commit()
        dog_id, handler_user_id = dog.id, handler_user.id

        client = app.test_client()
        _login(client, handler_user_id)
        r = client.post(f"/club/profile/dogs/{dog_id}/details", data={
            f"dog_{dog_id}-name": "Gehackt", f"dog_{dog_id}-breed": "Egal",
        })
        assert r.status_code == 403

        dog = db.session.get(M.Dog, dog_id)
        assert dog.name == "Smash"
