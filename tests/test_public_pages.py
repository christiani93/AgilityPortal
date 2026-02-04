from app.extensions import db
from app.models import Event, ScheduleBlock


def test_schedule_page_returns_200_when_public(app):
    with app.app_context():
        event = Event(name="Public Event", is_published=True, schedule_public=True)
        db.session.add(event)
        db.session.commit()
        db.session.add(
            ScheduleBlock(
                event_id=event.id,
                ring="Ring 1",
                discipline="Agility",
                category_code="Large",
                class_level=1,
                sort_index=1,
            )
        )
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/schedule")
        assert response.status_code == 200


def test_startlist_page_returns_200(app):
    with app.app_context():
        event = Event(name="Public Startlist", is_published=True, startlist_public=True)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/startlist")
        assert response.status_code == 200
        assert b"Startliste" in response.data
