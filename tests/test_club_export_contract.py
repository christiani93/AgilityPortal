"""
Kontrakt-Test für den PRODUKTIV genutzten Event-Export Portal→AgilitySoftware:
die im Veranstalter-UI verlinkte Route ``club.event_export_zip``
(/club/events/<id>/export.zip).

Hintergrund: Es gibt im Portal ZWEI eventexport.v1-Erzeuger mit bewusst
unterschiedlichen Schemata für zwei verschiedene Konsumenten —
``exchange_service.build_event_export_zip`` (external_id-basiert, Portal↔Portal-
Round-Trip, bereits von test_exchange_endpoints.py abgedeckt) und diese
club-Route (license_no-basiert, der echte Weg in die AgilitySoftware).

Felder, die die AgilitySoftware liest, aber nur im exchange_service-Pfad ergänzt
wurden, sind schon einmal still durchgerutscht (breed 0/104, Vereinsnummer 0/84
beim echten Jump-Into-Fall-Import). Dieser Test nagelt den Portal→Software-
Kontrakt auf der echten Route fest, damit genau das nicht wieder passiert.
"""
import io
import json
import zipfile

from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_event():
    club = M.Club(vereinsnummer="1234", name="Hundesportverein Musterhausen")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()

    event = M.Event(name="Kontrakt-Test", organiser_club_id=club.id)
    db.session.add(event)
    db.session.flush()

    dog = M.Dog(
        name="Rex",
        license_no="20001",
        license_kind=M.LicenseKind.CH,
        breed="Border Collie",
    )
    person = M.Person(first_name="Max", last_name="Muster")
    db.session.add_all([dog, person])
    db.session.flush()

    reg = M.Registration(
        event_id=event.id,
        dog_id=dog.id,
        handler_id=person.id,
        status=M.RegistrationStatus.CONFIRMED,
        class_level=1,
        category_code="Large",
        club_name="1234",  # Roh-Vereinsnummer (wie AOA-Import sie ablegt)
    )
    db.session.add(reg)
    db.session.commit()
    return event.id, admin.id


def test_club_export_includes_breed_and_club_name(app):
    """Der echte Export MUSS breed (entities.dogs) + club_name (registrations)
    enthalten — sonst fehlen Rasse und Vereinsnummer beim Software-Import."""
    with app.app_context():
        event_id, admin_id = _seed_event()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.get(f"/club/events/{event_id}/export.zip")
        assert resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            entities = json.loads(zf.read("entities.json"))
            registrations = json.loads(zf.read("registrations.json"))["registrations"]

        # breed: die Software liest sie ausschliesslich aus entities.dogs[].breed
        assert entities["dogs"], "entities.dogs darf nicht leer sein"
        for dog in entities["dogs"]:
            assert "breed" in dog, "entities.dogs[] ohne 'breed' — Kontrakt verletzt"
        assert any(d["breed"] == "Border Collie" for d in entities["dogs"])

        # club_name: die Software liest sie je Registration (→ Vereinsnummer)
        assert registrations, "registrations darf nicht leer sein"
        for reg in registrations:
            assert "club_name" in reg, "registrations[] ohne 'club_name' — Kontrakt verletzt"
        assert all(r["club_name"] == "1234" for r in registrations)
