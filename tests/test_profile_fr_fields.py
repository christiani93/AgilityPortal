"""Render-Smoke + Persistenz der franz. Zusatzfelder (CNEAC-Formular) in den
Teilnehmer-Profilseiten: /profile (Läufer: N° licence/Club/Régionale) und
/profile/dogs (Hund: FAPAC/Sexe)."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_user():
    person = M.Person(first_name="Arthur", last_name="Naud")
    db.session.add(person)
    db.session.flush()
    user = M.User(email="arthur@test.fr", role="club_user", person_id=person.id)
    db.session.add(user)
    db.session.commit()
    return user.id


def test_profile_pages_render_french_fields(app):
    with app.app_context():
        user_id = _seed_user()
        client = app.test_client()
        _login(client, user_id)

        r = client.get("/club/profile")
        assert r.status_code == 200
        assert b"licence" in r.data  # N° licence (franz. Laeuferlizenz)

        r = client.get("/club/profile/dogs")
        assert r.status_code == 200
        assert b"FAPAC" in r.data


def test_profile_persists_french_runner_fields(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id = _seed_user()
        client = app.test_client()
        _login(client, user_id)

        r = client.post("/club/profile", data={
            "first_name": "Arthur", "last_name": "Naud", "phone": "",
            "fr_license_no": "L-98765", "fr_club": "CC Lyon", "fr_regionale": "Rhône-Alpes",
        }, follow_redirects=True)
        assert r.status_code == 200

        person = db.session.get(M.User, user_id).person
        assert person.fr_license_no == "L-98765"
        assert person.fr_club == "CC Lyon"
        assert person.fr_regionale == "Rhône-Alpes"


def test_profile_dogs_persists_french_dog_fields(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id = _seed_user()
        client = app.test_client()
        _login(client, user_id)

        r = client.post("/club/profile/dogs", data={
            "name": "Haze", "breed": "Border Collie",
            "license_kind": "FOREIGN", "license_no": "FRA-104983",
            "fapac_no": "D-12345", "sex": "M",
        }, follow_redirects=True)
        assert r.status_code == 200

        dog = db.session.execute(
            db.select(M.Dog).filter_by(license_no="FRA-104983")
        ).scalar_one()
        assert dog.fapac_no == "D-12345"
        assert dog.sex == "M"
