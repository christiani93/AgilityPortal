from app.extensions import db
from app.models import (Dog, Event, LicenseKind, Person, Registration,
                        RegistrationStatus, ScheduleBlock)


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
        # Ohne Startnummern: Reihenfolge-Variante des Ablaufplans.
        body = response.get_data(as_text=True)
        assert "Ablaufplan" in body
        assert "Reihenfolge" in body


def test_schedule_page_shows_segment_timeline_with_start_numbers(app):
    # Sobald Startnummern vergeben sind, zeigt die öffentliche Ansicht die
    # gleiche Segment-Timeline (Umbau/Briefing/Starter) wie für eingeloggte Nutzer.
    from datetime import datetime

    with app.app_context():
        event = Event(name="Mit Zeiten", is_published=True, schedule_public=True,
                      ring_count=1, start_numbers_generated_at=datetime(2026, 10, 6, 8, 0))
        db.session.add(event)
        db.session.commit()
        db.session.add(
            ScheduleBlock(
                event_id=event.id,
                ring="Ring 1",
                discipline="agility",
                category_code="Large",
                class_level=1,
                sort_index=1,
            )
        )
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/schedule")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Mit Zeiten" in body
        assert "Segment" in body
        assert "Umbau" in body


def test_startlist_page_returns_200(app):
    with app.app_context():
        event = Event(name="Public Startlist", is_published=True, startlist_public=True)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/startlist")
        assert response.status_code == 200
        # Ohne Startnummern rendert die Seite als Meldeliste.
        assert b"Meldeliste" in response.data


def test_startlist_page_visible_even_when_not_flagged_public(app):
    # Meldeliste/Startliste ist für publizierte Events immer sichtbar –
    # gleich wie für eingeloggte Nutzer (kein startlist_public-Gate mehr).
    with app.app_context():
        event = Event(name="Ohne Flag", is_published=True, startlist_public=False)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/startlist")
        assert response.status_code == 200
        assert b"Meldeliste" in response.data


def test_startlist_print_page_returns_200_with_rows(app):
    # Druckseite rendert die gleichen Zeilen wie die normale Startliste,
    # als eigenständige A4-Seite mit Logo-Kopf (ohne base.html-Navigation).
    with app.app_context():
        event = Event(name="Druck Event", is_published=True, startlist_public=True)
        db.session.add(event)
        db.session.flush()

        dog = Dog(name="Rex", license_no="12345", license_kind=LicenseKind.CH)
        handler = Person(first_name="Anna", last_name="Muster")
        db.session.add_all([dog, handler])
        db.session.flush()
        db.session.add(Registration(
            event_id=event.id, dog_id=dog.id, handler_id=handler.id,
            class_level=1, category_code="Large",
            status=RegistrationStatus.CONFIRMED,
        ))
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/startlist/print")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Rex" in body
        assert "Anna Muster" in body
        assert "window.print()" in body
        # Eigenständige Druckseite, nicht in base.html eingebettet.
        assert "<!DOCTYPE html>" in body

        # Normale Startliste verlinkt auf die Druckseite.
        list_resp = client.get(f"/events/{event.id}/startlist")
        assert f"/events/{event.id}/startlist/print" in list_resp.get_data(as_text=True)


def test_startlist_print_page_404_when_unpublished(app):
    with app.app_context():
        event = Event(name="Entwurf", is_published=False)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        assert client.get(f"/events/{event.id}/startlist/print").status_code == 404


def test_events_index_lists_only_published_nontest(app):
    with app.app_context():
        pub = Event(name="Sichtbar", is_published=True)
        draft = Event(name="Entwurf", is_published=False)
        test_ev = Event(name="Testturnier", is_published=True, is_test=True)
        db.session.add_all([pub, draft, test_ev])
        db.session.commit()

        client = app.test_client()
        response = client.get("/events")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Sichtbar" in body
        assert "Entwurf" not in body
        assert "Testturnier" not in body


def test_overview_page_returns_200_when_published(app):
    with app.app_context():
        event = Event(name="Public Overview", is_published=True, location="Halle",
                      startlist_public=True, schedule_public=True)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Public Overview" in body
        assert "Halle" in body
        assert f"/events/{event.id}/startlist" in body
        assert f"/events/{event.id}/schedule" in body


def test_overview_page_404_when_unpublished(app):
    with app.app_context():
        event = Event(name="Entwurf", is_published=False)
        db.session.add(event)
        db.session.commit()

        client = app.test_client()
        assert client.get(f"/events/{event.id}").status_code == 404


def test_startlist_shows_meldeliste_before_start_numbers(app):
    with app.app_context():
        event = Event(name="Vorlauf", is_published=True, startlist_public=True)
        db.session.add(event)
        db.session.flush()

        dog = Dog(name="Rex", license_no="12345", license_kind=LicenseKind.CH)
        handler = Person(first_name="Anna", last_name="Muster")
        db.session.add_all([dog, handler])
        db.session.flush()
        db.session.add(Registration(
            event_id=event.id, dog_id=dog.id, handler_id=handler.id,
            class_level=1, category_code="Large",
            status=RegistrationStatus.CONFIRMED,
        ))
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/events/{event.id}/startlist")
        assert response.status_code == 200
        body = response.get_data(as_text=True)
        assert "Meldeliste" in body
        assert "Rex" in body
        assert "Anna Muster" in body
