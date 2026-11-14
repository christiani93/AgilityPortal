"""TV-Register Admin-Tests"""
import pytest
from app.extensions import db
from app.models import Event, EventFinalist


def test_event_title_defenders_add_tv(client, app, admin_key):
    """Admin kann TV hinzufügen"""
    with app.app_context():
        event = Event(name="Test Event", type="bccs_sm")
        db.session.add(event)
        db.session.commit()
        event_id = event.id

    response = client.post(
        f"/admin/events/{event_id}/title-defenders?key={admin_key}",
        data={
            "action": "add",
            "license_no": "12345",
            "dog_name": "Tease",
            "handler_name": "Silvan",
            "category": "Large",
            "division": "sm",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Überprüfe, dass TV in DB ist
    with app.app_context():
        tv = EventFinalist.query.filter_by(
            event_id=event_id,
            license="12345",
            source="title_defender",
        ).first()
        assert tv is not None
        assert tv.dog_name == "Tease"
        assert tv.handler_name == "Silvan"
        assert tv.category == "Large"
        assert tv.division == "sm"


def test_event_title_defenders_duplicate_rejected(client, app, admin_key):
    """Duplikate werden abgelehnt"""
    with app.app_context():
        event = Event(name="Test Event", type="bccs_sm")
        db.session.add(event)
        db.session.flush()
        event_id = event.id

        # Erstes TV hinzufügen
        tv1 = EventFinalist(
            event_id=event_id,
            license="12345",
            dog_name="Tease",
            handler_name="Silvan",
            source="title_defender",
            category="Large",
            division="sm",
            position=1,
        )
        db.session.add(tv1)
        db.session.commit()

    # Duplikat hinzufügen sollte fehlschlagen
    response = client.post(
        f"/admin/events/{event_id}/title-defenders?key={admin_key}",
        data={
            "action": "add",
            "license_no": "12345",
            "dog_name": "Tease",
            "handler_name": "Silvan",
            "category": "Large",
            "division": "sm",
        },
    )
    assert response.status_code == 400


def test_event_title_defenders_delete(client, app, admin_key):
    """Admin kann TV löschen"""
    with app.app_context():
        event = Event(name="Test Event", type="bccs_sm")
        db.session.add(event)
        db.session.flush()
        event_id = event.id

        tv = EventFinalist(
            event_id=event_id,
            license="12345",
            dog_name="Tease",
            handler_name="Silvan",
            source="title_defender",
            position=1,
        )
        db.session.add(tv)
        db.session.commit()
        tv_id = tv.id

    # Löschen
    response = client.post(
        f"/admin/events/{event_id}/title-defenders?key={admin_key}",
        data={"action": "delete", "finalist_id": tv_id},
        follow_redirects=True,
    )
    assert response.status_code == 200

    # Überprüfe, dass TV gelöscht ist
    with app.app_context():
        tv = EventFinalist.query.get(tv_id)
        assert tv is None
