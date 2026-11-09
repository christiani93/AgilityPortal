"""Läufig-Meldung nur für Hündinnen (F) oder unbekanntes Geschlecht — nie für
Rüden (M). Das Aufheben einer bestehenden Meldung bleibt immer erlaubt."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed(sex, is_in_season=False):
    person = M.Person(first_name="Ann", last_name="Handler")
    db.session.add(person)
    db.session.flush()
    user = M.User(email=f"ann_{sex or 'none'}@test.ch", role="handler", person_id=person.id)
    dog = M.Dog(name="Dog", license_no=f"9{abs(hash(sex or 'x')) % 100000}",
                license_kind=M.LicenseKind.CH, sex=sex, category="L", class_level=1)
    event = M.Event(name="Turnier", status="open", allows_bitches_in_season=True)
    db.session.add_all([user, dog, event])
    db.session.flush()
    reg = M.Registration(event_id=event.id, dog_id=dog.id, handler_id=person.id,
                         category_code="Large", class_level=1,
                         status=M.RegistrationStatus.PENDING, is_in_season=is_in_season)
    db.session.add(reg)
    db.session.commit()
    return user.id, reg.id


def test_male_dog_cannot_be_marked_in_season(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id, reg_id = _seed("M")
        client = app.test_client()
        _login(client, user_id)
        client.post(f"/club/registrations/{reg_id}/toggle-in-season")
        assert db.session.get(M.Registration, reg_id).is_in_season is False


def test_female_dog_can_be_marked_in_season(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id, reg_id = _seed("F")
        client = app.test_client()
        _login(client, user_id)
        client.post(f"/club/registrations/{reg_id}/toggle-in-season")
        assert db.session.get(M.Registration, reg_id).is_in_season is True


def test_unknown_sex_can_be_marked_in_season(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id, reg_id = _seed(None)
        client = app.test_client()
        _login(client, user_id)
        client.post(f"/club/registrations/{reg_id}/toggle-in-season")
        assert db.session.get(M.Registration, reg_id).is_in_season is True


def test_male_in_season_can_still_be_unmarked(app):
    """Datenaltlast: ein bereits als läufig markierter Rüde muss aufhebbar sein."""
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user_id, reg_id = _seed("M", is_in_season=True)
        client = app.test_client()
        _login(client, user_id)
        client.post(f"/club/registrations/{reg_id}/toggle-in-season")
        assert db.session.get(M.Registration, reg_id).is_in_season is False
