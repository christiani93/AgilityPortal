"""
Regression-Tests: doppelte AIS-Turniernummer darf nie mehr als unbehandelter
IntegrityError (500) enden, sondern muss als Formularfehler abgefangen werden.

Auslöser: Crash beim Bearbeiten von Event 18 (Halloween Cup Freitag) mit der
bereits auf Event 19 vergebenen AIS-Nummer 11471 (DB-Unique-Constraint auf
events.ais_turniernummer).
"""
from app.extensions import db
from app import models as M
from app.services.template_service import create_event_from_template


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


def test_event_edit_rejects_duplicate_ais_without_crashing(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        taken = M.Event(name="Samstag", organiser_club_id=club.id, ais_turniernummer=11471)
        other = M.Event(name="Freitag", organiser_club_id=club.id)
        db.session.add_all([taken, other])
        db.session.commit()
        other_id = other.id

        client = app.test_client()
        _login(client, admin.id)
        resp = client.post(f"/club/events/{other_id}/edit", data={
            "name": "Freitag",
            "starts_at": "2026-10-30",
            "ais_turniernummer": "11471",
        })

        # Kein 500, kein Redirect -> Formular mit Fehler erneut angezeigt.
        assert resp.status_code == 200
        assert "bereits" in resp.get_data(as_text=True)
        db.session.refresh(other)
        assert other.ais_turniernummer is None


def test_event_edit_allows_keeping_own_ais_number(app):
    """Das eigene Event darf beim Speichern nicht mit sich selbst kollidieren."""
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        event = M.Event(name="Turnier", organiser_club_id=club.id, ais_turniernummer=12345)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin.id)
        resp = client.post(f"/club/events/{event_id}/edit", data={
            "name": "Turnier",
            "starts_at": "2026-10-30",
            "ais_turniernummer": "12345",
        })
        assert resp.status_code == 302


def test_event_new_rejects_duplicate_ais_without_crashing(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_and_admin()
        db.session.add(M.Event(name="Bestehend", organiser_club_id=club.id, ais_turniernummer=11471))
        db.session.commit()

        client = app.test_client()
        _login(client, admin.id)
        resp = client.post("/club/events/new", data={
            "name": "Neues Turnier",
            "starts_at": "2026-10-31",
            "ais_turniernummer": "11471",
        })

        assert resp.status_code == 200
        assert "bereits" in resp.get_data(as_text=True)
        assert db.session.execute(
            db.select(M.Event).filter_by(name="Neues Turnier")
        ).scalars().first() is None


def test_create_event_from_template_rejects_duplicate_ais(app):
    with app.app_context():
        club, _ = _seed_club_and_admin()
        db.session.add(M.Event(name="Bestehend", organiser_club_id=club.id, ais_turniernummer=11471))
        tpl = M.EventTemplate(name="Vorlage", organiser_club_id=club.id, day_count=1)
        db.session.add(tpl)
        db.session.commit()

        event, messages = create_event_from_template(tpl, {
            "name": "Neu aus Vorlage",
            "starts_at": "2026-10-31",
            "ais_1": "11471",
        })

        assert event is None
        assert any("bereits" in text for text, _cat in messages)
