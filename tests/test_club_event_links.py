"""Smoke-Test für die Seite "Teilbare Links" (club.event_links).

Stellt sicher, dass die öffentliche Link-Übersicht rendert und nur öffentliche
Links enthält (keine Veranstalter-internen Links, kein VAR).
"""
from app.extensions import db
from app import models as M


def _seed_published_event():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()
    event = M.Event(
        name="Link-Test-Turnier",
        organiser_club_id=club.id,
        is_published=True,
        status="open",
    )
    db.session.add(event)
    db.session.commit()
    return event.id, admin.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_event_links_page_renders_public_links_only(app):
    with app.app_context():
        event_id, admin_id = _seed_published_event()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.get(f"/club/events/{event_id}/links")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        # Öffentliche Links sind enthalten (absolute URLs).
        assert f"/events/{event_id}" in html            # Übersicht
        assert f"/events/{event_id}/live" in html        # Live (status=open)

        # Keine Veranstalter-internen Links / kein VAR.
        assert "var_control" not in html
        assert "/edit" not in html
        assert "export" not in html.lower()


def test_event_links_access_control(app):
    with app.app_context():
        event_id, _ = _seed_published_event()
        # Fremder Club-User ohne Superadmin darf NICHT zugreifen.
        other_club = M.Club(vereinsnummer="V2", name="Other")
        db.session.add(other_club)
        db.session.flush()
        other = M.User(email="other@test.ch", role="club_admin", club_id=other_club.id)
        db.session.add(other)
        db.session.commit()

        client = app.test_client()
        _login(client, other.id)
        resp = client.get(f"/club/events/{event_id}/links")
        assert resp.status_code == 403
