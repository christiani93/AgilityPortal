"""Ein-Klick Publizieren/Verstecken eines Turniers.

Hintergrund: Aus einer Vorlage erstellte Events werden als Entwurf geboren
(is_published=False). Bis hierher liess sich das nur versteckt im Bearbeiten-
Formular (is_published = not is_test) umschalten -> HCS-Events landeten still
auf 404. Der Toggle-Button macht das Publizieren auffindbar.
"""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_club_and_admin():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="club_admin")
    db.session.add_all([club, admin])
    db.session.flush()
    admin.club_id = club.id
    db.session.commit()
    return club, admin


def test_publish_draft_event_makes_it_public(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        event = M.Event(name="Tunnellauf", organiser_club_id=club.id,
                        is_published=False, is_test=False)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin.id)
        resp = client.post(f"/club/events/{event_id}/publish")
        assert resp.status_code == 302
        db.session.refresh(event)
        assert event.is_published is True


def test_publish_clears_test_flag(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        event = M.Event(name="Test-Event", organiser_club_id=club.id,
                        is_published=False, is_test=True)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin.id)
        client.post(f"/club/events/{event_id}/publish")
        db.session.refresh(event)
        assert event.is_published is True
        assert event.is_test is False


def test_toggle_hides_published_event(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        event = M.Event(name="Öffentlich", organiser_club_id=club.id,
                        is_published=True, is_test=False)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin.id)
        client.post(f"/club/events/{event_id}/publish")
        db.session.refresh(event)
        assert event.is_published is False


def test_detail_page_shows_publish_button_for_draft(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        event = M.Event(name="Entwurf", organiser_club_id=club.id,
                        is_published=False, is_test=False)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin.id)
        body = client.get(f"/club/events/{event_id}").get_data(as_text=True)
        assert f"/club/events/{event_id}/publish" in body
        assert "Nicht publiziert" in body
