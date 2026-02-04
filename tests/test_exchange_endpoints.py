import io
import json
import zipfile

from app.extensions import db
from app.models import Dog, Event, LicenseKind, Person, Registration, RegistrationStatus, Result


def _build_results_zip(event_external_id: str):
    manifest = {"schema": "agility.exchange.resultexport.v1"}
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
                "results": [
                    {
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
                ],
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
