"""Veranstalter kann das BCCS-SM-Flag einer Anmeldung manuell setzen/aufheben
(Ergänzung zum AOA-Import, der das Flag nicht immer zuverlässig übernimmt,
z.B. wenn die Excel keine SMQ-Spalte hat)."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_bccs_event():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()

    event = M.Event(name="BCCS-SM Test", organiser_club_id=club.id, type="bccs_sm")
    db.session.add(event)
    db.session.flush()

    dog = M.Dog(name="Rex", license_no="30001", license_kind=M.LicenseKind.CH)
    person = M.Person(first_name="HF", last_name="Toggle")
    db.session.add_all([dog, person])
    db.session.flush()
    reg = M.Registration(
        event_id=event.id, dog_id=dog.id, handler_id=person.id,
        status=M.RegistrationStatus.CONFIRMED, class_level=3, category_code="Large",
        bccs_sm=False,
    )
    db.session.add(reg)
    db.session.commit()
    return event.id, admin.id, reg.id


def test_organiser_toggles_bccs_sm_flag(app):
    with app.app_context():
        event_id, admin_id, reg_id = _seed_bccs_event()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/registrations/{reg_id}/toggle-bccs-sm")
        assert resp.status_code == 302
        reg = db.session.get(M.Registration, reg_id)
        assert reg.bccs_sm is True

        client.post(f"/club/registrations/{reg_id}/toggle-bccs-sm")
        reg = db.session.get(M.Registration, reg_id)
        assert reg.bccs_sm is False


def test_other_club_cannot_toggle_bccs_sm(app):
    with app.app_context():
        event_id, admin_id, reg_id = _seed_bccs_event()
        other_club = M.Club(vereinsnummer="V2", name="Fremdverein")
        other_user = M.User(email="other@test.ch", role="club_admin", club_id=None)
        db.session.add_all([other_club, other_user])
        db.session.flush()
        other_user.club_id = other_club.id
        db.session.commit()

        client = app.test_client()
        _login(client, other_user.id)

        resp = client.post(f"/club/registrations/{reg_id}/toggle-bccs-sm")
        assert resp.status_code == 403
        reg = db.session.get(M.Registration, reg_id)
        assert reg.bccs_sm is False
