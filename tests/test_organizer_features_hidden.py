"""Website-Sync, Zahlungsinfos und Sammelmail sind für den ersten (schnelleren)
Rollout der Veranstalter-Umgebung per Default ausgeblendet (Feature-Flags
ORGANIZER_WEBSITE_SYNC_ENABLED / ORGANIZER_PAYMENT_INFO_ENABLED /
ORGANIZER_BULK_EMAIL_ENABLED in app/__init__.py, Default aus)."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()
    event = M.Event(name="Event", organiser_club_id=club.id)
    db.session.add(event)
    db.session.commit()
    return event.id, admin.id


def test_event_detail_hides_gated_cards_by_default(app):
    with app.app_context():
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.get(f"/club/events/{event_id}")
        html = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Zahlungsinfos für Bestätigungsmail" not in html
        assert "Website-Sync (z-b.tech)" not in html
        assert "E-Mail an Teilnehmer" not in html


def test_gated_routes_404_by_default(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        assert client.post(f"/club/events/{event_id}/payment-info",
                            data={"payment_info": "IBAN ..."}).status_code == 404
        assert client.post(f"/club/events/{event_id}/website-sync").status_code == 404
        assert client.post(f"/club/events/{event_id}/description-save",
                            data={"event_description_de": "x"}).status_code == 404
        assert client.post(f"/club/events/{event_id}/email/send",
                            data={"subject": "x", "body": "y"}).status_code == 404


def test_flags_can_be_enabled_via_config(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        app.config["ORGANIZER_PAYMENT_INFO_ENABLED"] = True
        event_id, admin_id = _seed()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.get(f"/club/events/{event_id}")
        assert "Zahlungsinfos für Bestätigungsmail" in resp.get_data(as_text=True)

        resp = client.post(f"/club/events/{event_id}/payment-info",
                            data={"payment_info": "IBAN CH00"}, follow_redirects=True)
        assert resp.status_code == 200
        assert db.session.get(M.Event, event_id).payment_info == "IBAN CH00"
