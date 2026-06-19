import io
import json
import zipfile

from app.extensions import db
from app.models import (Dog, Event, EventFinalist, LicenseKind, Person,
                        Registration, RegistrationStatus, Result)


def _build_results_zip(event_external_id: str, include_total_faults: bool = True,
                       finalists: list | None = None):
    manifest = {"schema": "agility.exchange.resultexport.v1"}
    row = {
        "registration_external_id": "reg-1",
        "start_no": 5,
        "rank": 1,
        "time_s": 35.5,
        "faults": 0,
        "refusals": 0,
        "eliminated": False,
        "status": "OK",
        "dog_name": "Rex",
        "handler_name": "Max Muster",
    }
    if include_total_faults:
        row["total_faults"] = 5.0
    results_payload = {
        "event_external_id": event_external_id,
        "exported_at": "2024-01-01T12:00:00",
        "final": True,
        "classes": [
            {
                "ring": "A",
                "discipline": "Agility",
                "category_code": "Large",
                "class_level": 1,
                "run_no": 1,
                "results": [row],
            }
        ],
        "documents": [
            {"kind": "RANKING_PDF", "name": "ranking.pdf", "path": "pdfs/ranking.pdf"}
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("manifest.json", json.dumps(manifest))
        zip_file.writestr("results.json", json.dumps(results_payload))
        zip_file.writestr("pdfs/ranking.pdf", b"dummy-pdf")
        if finalists is not None:
            zip_file.writestr("finalists.json", json.dumps({
                "event_external_id": event_external_id,
                "veranstaltungsart": "SKBS-SM",
                "finalists":         finalists,
                "open_spots":        0,
            }))
    return buffer.getvalue()


def test_event_export_zip_contains_files(app):
    with app.app_context():
        event = Event(name="Test Event")
        person = Person(first_name="Max", last_name="Muster")
        dog = Dog(name="Rex", license_no="12345", license_kind=LicenseKind.CH)
        registration = Registration(
            event=event,
            dog=dog,
            handler=person,
            status=RegistrationStatus.SUBMITTED,
            class_level=1,
            category_code="Large",
        )
        db.session.add_all([event, person, dog, registration])
        db.session.commit()

        client = app.test_client()
        response = client.get(f"/admin/exchange/events/{event.id}/export?key=dev-admin-key")
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.data)) as zip_file:
            names = set(zip_file.namelist())
            event_payload = json.loads(zip_file.read("event.json"))
            registrations_payload = json.loads(zip_file.read("registrations.json"))
        assert {
            "manifest.json",
            "event.json",
            "entities.json",
            "registrations.json",
            "start_numbers.json",
            "schedule.json",
        }.issubset(names)
        assert event_payload["billing_mode"] == "ORGANIZER"
        assert registrations_payload[0]["eligibility"]["payment_status"] == "NOT_MANAGED"


def test_liveupdate_idempotent(app):
    payload = {
        "schema": "agility.exchange.liveupdate.v1",
        "event_external_id": "evt-123",
        "source": {"device": "dev-1", "system": "AgilitySoftware", "version": "1.0"},
        "sequence_no": 42,
        "context": {},
    }
    client = app.test_client()
    response = client.post(
        "/api/liveupdate",
        json=payload,
        headers={"X-Api-Key": "dev-live-key"},
    )
    assert response.status_code == 200
    response = client.post(
        "/api/liveupdate",
        json=payload,
        headers={"X-Api-Key": "dev-live-key"},
    )
    data = response.get_json()
    assert response.status_code == 200
    assert data["stored"] is False


def test_resultexport_import_creates_results_rows(app):
    with app.app_context():
        event = Event(name="Result Event", external_id="evt-555")
        db.session.add(event)
        db.session.commit()

        zip_bytes = _build_results_zip(event.external_id)
        client = app.test_client()
        response = client.post(
            "/api/resultexport",
            data=zip_bytes,
            headers={"X-Api-Key": "dev-results-key"},
        )
        assert response.status_code == 200
        assert Result.query.count() == 1
        row = Result.query.first()
        assert row.total_faults == 5.0


def test_resultexport_import_backwards_compatible_without_total_faults(app):
    """Alte Software-Exports (vor Schema 3.1) ohne total_faults bleiben gültig."""
    with app.app_context():
        event = Event(name="Legacy Event", external_id="evt-legacy")
        db.session.add(event)
        db.session.commit()

        zip_bytes = _build_results_zip(event.external_id, include_total_faults=False)
        client = app.test_client()
        response = client.post(
            "/api/resultexport",
            data=zip_bytes,
            headers={"X-Api-Key": "dev-results-key"},
        )
        assert response.status_code == 200
        assert Result.query.count() == 1
        assert Result.query.first().total_faults is None


def test_resultexport_import_finalists_block(app):
    """Schema v1.6: finalists.json wird in EventFinalist persistiert."""
    with app.app_context():
        event = Event(name="SKBS-SM Event", external_id="evt-skbs")
        db.session.add(event)
        db.session.commit()

        finalists = [
            {"license": "100", "dog_name": "Aki", "handler_name": "Anna",
             "source": "agility", "from_class": 3, "quali_rank": 1},
            {"license": "200", "dog_name": "Bo", "handler_name": "Beat",
             "source": "title_defender", "from_class": None, "quali_rank": None},
            {"license": "300", "dog_name": "Cleo", "handler_name": "Chris",
             "source": "nachruecker", "from_class": 2, "quali_rank": 4},
        ]
        zip_bytes = _build_results_zip(event.external_id, finalists=finalists)
        client = app.test_client()
        response = client.post(
            "/api/resultexport",
            data=zip_bytes,
            headers={"X-Api-Key": "dev-results-key"},
        )
        assert response.status_code == 200

        persisted = EventFinalist.query.filter_by(event_id=event.id).order_by(EventFinalist.position).all()
        assert len(persisted) == 3
        assert persisted[0].license == "100"
        assert persisted[0].source == "agility"
        assert persisted[1].source == "title_defender"
        assert persisted[1].from_class is None
        assert persisted[2].source == "nachruecker"
        assert persisted[2].from_class == 2
        # Position 1-basiert in Aufnahme-Reihenfolge
        assert [f.position for f in persisted] == [1, 2, 3]


def _build_event_export_zip(external_id="evt-imp-1", with_schedule=True,
                             with_startnumbers=True):
    """Synthetisches eventexport.v1.zip für Import-Tests."""
    manifest = {"schema": "agility.exchange.eventexport.v1"}
    event_payload = {
        "external_id": external_id,
        "name":        "Imported Event",
        "location":    "Münsingen",
        "starts_at":   "2026-12-05T08:00:00",
        "billing_mode":"ORGANIZER",
    }
    entities = {
        "persons": [
            {"external_id": "p-1", "first_name": "Anna", "last_name": "Tester"},
            {"external_id": "p-2", "first_name": "Beat", "last_name": "Beispiel"},
        ],
        "dogs": [
            {"external_id": "d-1", "name": "Rex", "license_no": "1001", "license_kind": "CH"},
            {"external_id": "d-2", "name": "Bo",  "license_no": "1002", "license_kind": "CH"},
        ],
    }
    registrations = [
        {"external_id": "r-1", "event_external_id": external_id,
         "dog_external_id": "d-1", "handler_person_external_id": "p-1",
         "category_code": "Large", "class_level": 3, "status": "SUBMITTED",
         "tka_event_check_status": "PENDING"},
        {"external_id": "r-2", "event_external_id": external_id,
         "dog_external_id": "d-2", "handler_person_external_id": "p-2",
         "category_code": "Large", "class_level": 2, "status": "SUBMITTED",
         "tka_event_check_status": "PENDING"},
    ]
    start_numbers = {
        "event_external_id": external_id,
        "locked": True,
        "numbers": [
            {"registration_external_id": "r-1", "start_no": 1},
            {"registration_external_id": "r-2", "start_no": 2},
        ],
    } if with_startnumbers else {}
    schedule = {
        "event_external_id": external_id,
        "timezone": "Europe/Zurich",
        "locked": False,
        "blocks": [
            {"ring": "1", "start_at": "2026-12-05T08:00:00",
             "discipline": "Agility", "category_code": "Large",
             "class_level": 3, "notes": "Block 1"},
        ],
    } if with_schedule else {}

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json",      json.dumps(manifest))
        zf.writestr("event.json",         json.dumps(event_payload))
        zf.writestr("entities.json",      json.dumps(entities))
        zf.writestr("registrations.json", json.dumps(registrations))
        if with_startnumbers:
            zf.writestr("start_numbers.json", json.dumps(start_numbers))
        if with_schedule:
            zf.writestr("schedule.json", json.dumps(schedule))
    return buf.getvalue()


def test_event_package_import_creates_event(app):
    with app.app_context():
        zip_bytes = _build_event_export_zip("evt-imp-1")
        resp = app.test_client().post(
            "/admin/exchange/event-package/import?key=dev-admin-key",
            data={"package": (io.BytesIO(zip_bytes), "evt.zip")},
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        # POST redirects to GET → 302
        assert resp.status_code == 302
        event = Event.query.filter_by(external_id="evt-imp-1").first()
        assert event is not None
        assert event.is_test is True
        assert event.is_published is False
        assert event.name == "Imported Event"
        # Anmeldungen + Stammdaten
        from app.models import Person, Dog, ScheduleBlock, StartNumber
        assert Person.query.filter_by(external_id="p-1").count() == 1
        assert Dog.query.filter_by(external_id="d-1").count() == 1
        from app.models import Registration as Reg
        assert Reg.query.filter_by(event_id=event.id).count() == 2
        assert StartNumber.query.filter_by(event_id=event.id).count() == 2
        assert ScheduleBlock.query.filter_by(event_id=event.id).count() == 1


def test_event_package_import_idempotent(app):
    """Zweiter Import des gleichen Events: ersetzt Anmeldungen, dupliziert nicht."""
    with app.app_context():
        zip_bytes = _build_event_export_zip("evt-imp-2")
        client = app.test_client()
        # 1. Import
        client.post(
            "/admin/exchange/event-package/import?key=dev-admin-key",
            data={"package": (io.BytesIO(zip_bytes), "evt.zip")},
            content_type="multipart/form-data",
        )
        event = Event.query.filter_by(external_id="evt-imp-2").first()
        assert event is not None
        first_id = event.id

        # 2. Import: gleiche Daten, sollte updaten nicht duplizieren
        client.post(
            "/admin/exchange/event-package/import?key=dev-admin-key",
            data={"package": (io.BytesIO(zip_bytes), "evt.zip")},
            content_type="multipart/form-data",
        )
        events = Event.query.filter_by(external_id="evt-imp-2").all()
        assert len(events) == 1
        assert events[0].id == first_id
        from app.models import Registration as Reg
        assert Reg.query.filter_by(event_id=event.id).count() == 2


def test_event_package_import_rejects_wrong_schema(app):
    with app.app_context():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"schema": "wrong.schema.v1"}))
            zf.writestr("event.json", json.dumps({"external_id": "x"}))
        resp = app.test_client().post(
            "/admin/exchange/event-package/import?key=dev-admin-key",
            data={"package": (io.BytesIO(buf.getvalue()), "bad.zip")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        # Flash-Message zeigt Fehler
        assert b"Import fehlgeschlagen" in resp.data or b"Ung" in resp.data


def test_ensure_test_event_creates_with_test_flag(app):
    with app.app_context():
        client = app.test_client()
        resp = client.get(
            "/admin/exchange/debug/ensure_test_event/test-evt-xxx?key=dev-admin-key&name=My+Test"
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["created"] is True
        assert data["external_id"] == "test-evt-xxx"
        assert data["is_test"] is True
        assert data["is_published"] is False
        assert data["name"] == "My Test"

        # Idempotent: zweiter Aufruf erstellt nicht erneut
        resp2 = client.get(
            "/admin/exchange/debug/ensure_test_event/test-evt-xxx?key=dev-admin-key"
        )
        data2 = resp2.get_json()
        assert data2["created"] is False
        assert data2["event_id"] == data["event_id"]


def test_ensure_test_event_requires_admin_key(app):
    with app.app_context():
        resp = app.test_client().get(
            "/admin/exchange/debug/ensure_test_event/anything"
        )
        assert resp.status_code == 403


def test_resultexport_import_finalists_idempotent(app):
    """Zweiter Import mit anderem ZIP-Inhalt ersetzt die Liste, dupliziert nicht."""
    with app.app_context():
        event = Event(name="SKBS-SM Event", external_id="evt-skbs-idem")
        db.session.add(event)
        db.session.commit()

        # 1. Import mit 2 Finalisten
        zip1 = _build_results_zip(event.external_id, finalists=[
            {"license": "100", "dog_name": "A", "handler_name": "AA",
             "source": "agility", "from_class": 3, "quali_rank": 1},
            {"license": "200", "dog_name": "B", "handler_name": "BB",
             "source": "jumping", "from_class": 3, "quali_rank": 1},
        ])
        client = app.test_client()
        r1 = client.post("/api/resultexport", data=zip1,
                         headers={"X-Api-Key": "dev-results-key"})
        assert r1.status_code == 200
        assert EventFinalist.query.filter_by(event_id=event.id).count() == 2

        # 2. Import mit 1 Finalist (anderer Inhalt → andere sha256)
        zip2 = _build_results_zip(event.external_id, finalists=[
            {"license": "999", "dog_name": "Solo", "handler_name": "Solo HF",
             "source": "agility", "from_class": 3, "quali_rank": 1},
        ])
        # Anderer Hash damit der Import nicht als Duplikat erkannt wird
        # (Daten unterschiedlich, also automatisch anderer sha256)
        r2 = client.post("/api/resultexport", data=zip2,
                         headers={"X-Api-Key": "dev-results-key"})
        assert r2.status_code == 200
        persisted = EventFinalist.query.filter_by(event_id=event.id).all()
        assert len(persisted) == 1
        assert persisted[0].license == "999"
