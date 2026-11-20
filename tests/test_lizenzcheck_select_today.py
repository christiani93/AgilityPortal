"""Das heutige Turnier darf in der Lizenzcheck-Auswahl (/club/lizenzcheck) nicht
verschwinden, nur weil seine Startzeit (starts_at) schon vorbei ist — Referenz
ist das Datum (ends_at/starts_at), nicht der exakte Zeitstempel."""
from datetime import datetime, timedelta

from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_todays_event_with_past_start_time_still_listed(app):
    with app.app_context():
        club = M.Club(vereinsnummer="V1", name="Club")
        club_admin = M.User(email="clubadmin@test.ch", role="club_admin", club=club)
        db.session.add_all([club, club_admin])
        db.session.flush()

        today = datetime.utcnow()
        # Turnier ist heute, aber die Startzeit liegt schon einige Stunden zurück.
        event_today = M.Event(name="Heutiges Turnier", organiser_club_id=club.id,
                               status="open",
                               starts_at=today - timedelta(hours=6),
                               ends_at=today + timedelta(hours=2))
        db.session.add(event_today)
        db.session.commit()

        client = app.test_client()
        _login(client, club_admin.id)

        resp = client.get("/club/lizenzcheck")
        assert resp.status_code == 200
        assert "Heutiges Turnier" in resp.get_data(as_text=True)
