"""Veranstalter kann das FMBB-Quali-Flag einer Anmeldung manuell setzen/aufheben
(FMBB-Teilnehmer kommen aus der SKBS-Lizenzliste, nicht aus der öffentlichen
Portal-Anmeldung). Analog zum BCCS-SM-Toggle."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_fmbb_event(event_type="fmbb_quali"):
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()

    event = M.Event(name="FMBB Test", organiser_club_id=club.id, type=event_type)
    db.session.add(event)
    db.session.flush()

    dog = M.Dog(name="Malik", license_no="40001", license_kind=M.LicenseKind.CH)
    person = M.Person(first_name="HF", last_name="Fmbb")
    db.session.add_all([dog, person])
    db.session.flush()
    reg = M.Registration(
        event_id=event.id, dog_id=dog.id, handler_id=person.id,
        status=M.RegistrationStatus.CONFIRMED, class_level=2, category_code="Large",
        is_fmbb=False,
    )
    db.session.add(reg)
    db.session.commit()
    return event.id, admin.id, reg.id


def test_organiser_toggles_fmbb_flag(app):
    with app.app_context():
        event_id, admin_id, reg_id = _seed_fmbb_event()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/registrations/{reg_id}/toggle-fmbb")
        assert resp.status_code == 302
        assert db.session.get(M.Registration, reg_id).is_fmbb is True

        client.post(f"/club/registrations/{reg_id}/toggle-fmbb")
        assert db.session.get(M.Registration, reg_id).is_fmbb is False


def test_other_club_cannot_toggle_fmbb(app):
    with app.app_context():
        event_id, admin_id, reg_id = _seed_fmbb_event()
        other_club = M.Club(vereinsnummer="V2", name="Fremdverein")
        other_user = M.User(email="other@test.ch", role="club_admin", club_id=None)
        db.session.add_all([other_club, other_user])
        db.session.flush()
        other_user.club_id = other_club.id
        db.session.commit()

        client = app.test_client()
        _login(client, other_user.id)

        resp = client.post(f"/club/registrations/{reg_id}/toggle-fmbb")
        assert resp.status_code == 403
        assert db.session.get(M.Registration, reg_id).is_fmbb is False


def test_allows_fmbb_property():
    # FMBB-Button erscheint bei reinen FMBB-Tagen UND bei SKBS-SM (Overlay), sonst nicht.
    assert M.Event(type="fmbb_quali").allows_fmbb is True
    assert M.Event(type="skbs_sm").allows_fmbb is True
    assert M.Event(type="bccs_sm").allows_fmbb is False
    assert M.Event(type="regular").allows_fmbb is False
