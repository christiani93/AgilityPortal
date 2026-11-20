"""Ad-hoc Smoke-Test: Kommende/Vergangene-Split in /club/ (Superadmin + Club-Admin)."""
from datetime import datetime, timedelta

from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed():
    club = M.Club(vereinsnummer="V1", name="Club")
    superadmin = M.User(email="super@test.ch", role="superadmin")
    club_admin = M.User(email="clubadmin@test.ch", role="club_admin", club=club)
    db.session.add_all([club, superadmin, club_admin])
    db.session.flush()

    today = datetime.utcnow()
    past = M.Event(name="Vergangenes Turnier", organiser_club_id=club.id,
                   starts_at=today - timedelta(days=10), ends_at=today - timedelta(days=9))
    soon = M.Event(name="Nächstes Turnier", organiser_club_id=club.id,
                   starts_at=today + timedelta(days=1), ends_at=today + timedelta(days=1))
    later = M.Event(name="Späteres Turnier", organiser_club_id=club.id,
                    starts_at=today + timedelta(days=5), ends_at=today + timedelta(days=5))
    undated = M.Event(name="Undatiertes Turnier", organiser_club_id=club.id)
    db.session.add_all([past, soon, later, undated])
    db.session.commit()
    return superadmin.id, club_admin.id


def test_superadmin_dashboard_shows_upcoming_first_then_past(app):
    with app.app_context():
        superadmin_id, _ = _seed()
        client = app.test_client()
        _login(client, superadmin_id)

        resp = client.get("/club/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        pos_soon = html.index("Nächstes Turnier")
        pos_later = html.index("Späteres Turnier")
        pos_undated = html.index("Undatiertes Turnier")
        pos_past = html.index("Vergangenes Turnier")
        assert pos_soon < pos_later < pos_undated < pos_past


def test_participant_dashboard_shows_past_events_section(app):
    with app.app_context():
        _seed()
        handler = M.User(email="handler@test.ch", role="handler")
        db.session.add(handler)
        db.session.commit()
        client = app.test_client()
        _login(client, handler.id)

        resp = client.get("/club/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        assert "Vergangene Turniere" in html
        assert "Vergangenes Turnier" in html


def test_participant_dashboard_open_events_excludes_past_still_open(app):
    """Ein Event mit Status 'open', dessen Datum aber vorbei ist (nicht manuell
    geschlossen), darf nicht mehr unter 'Offene Turniere' erscheinen — nur noch
    unter 'Vergangene Turniere'."""
    with app.app_context():
        club, _, _ = M.Club(vereinsnummer="V9", name="ClubX"), None, None
        db.session.add(club)
        db.session.flush()
        today = datetime.utcnow()
        past_but_open = M.Event(name="Altes Offenes Turnier", organiser_club_id=club.id,
                                status="open",
                                starts_at=today - timedelta(days=5), ends_at=today - timedelta(days=4))
        db.session.add(past_but_open)
        handler = M.User(email="handler2@test.ch", role="handler")
        db.session.add(handler)
        db.session.commit()
        client = app.test_client()
        _login(client, handler.id)

        resp = client.get("/club/")
        html = resp.get_data(as_text=True)
        pos_open_header = html.index("Offene Turniere")
        pos_past_header = html.index("Vergangene Turniere")
        assert "Altes Offenes Turnier" not in html[pos_open_header:pos_past_header]
        assert "Altes Offenes Turnier" in html[pos_past_header:]


def test_club_admin_dashboard_shows_upcoming_first_then_past(app):
    with app.app_context():
        _, club_admin_id = _seed()
        client = app.test_client()
        _login(client, club_admin_id)

        resp = client.get("/club/")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)

        pos_soon = html.index("Nächstes Turnier")
        pos_later = html.index("Späteres Turnier")
        pos_undated = html.index("Undatiertes Turnier")
        pos_past = html.index("Vergangenes Turnier")
        assert pos_soon < pos_later < pos_undated < pos_past
