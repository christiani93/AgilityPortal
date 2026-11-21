"""club.event_live zeigte bisher KEINEN Link zur Finalisten-Seite (anders als
die oeffentliche Event-Uebersicht public_overview, die den Button schon hatte)
- der Veranstalter sah auf der Live-Seite also keinen Weg zu den Finalisten/
Titelverteidigern. Button ist jetzt an has_finalists gekoppelt, analog
public_overview()."""
from app.extensions import db
from app import models as M


def _seed_event(with_finalist: bool):
    club = M.Club(vereinsnummer="1234", name="Hundesportverein Musterhausen")
    db.session.add(club)
    db.session.flush()

    event = M.Event(name="BCCS-Test", organiser_club_id=club.id, status="open")
    db.session.add(event)
    db.session.flush()

    if with_finalist:
        finalist = M.EventFinalist(
            event_id=event.id,
            license="16214",
            dog_name="Tease",
            handler_name="Silvan Zumthurm",
            source="title_defender",
            category="Large",
            division="sm",
            position=1,
        )
        db.session.add(finalist)

    db.session.commit()
    return event.id


def test_live_page_shows_finalists_button_when_finalists_exist(app):
    with app.app_context():
        event_id = _seed_event(with_finalist=True)
        client = app.test_client()
        resp = client.get(f"/club/events/{event_id}/live")
        assert resp.status_code == 200
        assert f"/events/{event_id}/finalists".encode() in resp.data


def test_live_page_hides_finalists_button_without_finalists(app):
    with app.app_context():
        event_id = _seed_event(with_finalist=False)
        client = app.test_client()
        resp = client.get(f"/club/events/{event_id}/live")
        assert resp.status_code == 200
        assert f"/events/{event_id}/finalists".encode() not in resp.data
