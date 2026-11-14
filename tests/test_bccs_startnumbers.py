"""
BCCS-SM Startnummern-Vergabe: Schema-basiert, auto-sequenziell.
"""
import json
from app.extensions import db
from app import models as M


def test_bccs_startnumber_schema_configured(app):
    """CLI-Befehl configure-bccs-startnumbers setzt die Schemas auf Events 33/34/35."""
    with app.app_context():
        # Erstelle die Events (simuliert die seed-season-events)
        for event_id, name in [(33, "Abendmeeting"), (34, "BCCS-Sa"), (35, "BCCS-So")]:
            event = M.Event(
                id=event_id,
                external_id=f"test_bccs_{event_id}",
                name=name,
                type="bccs_sm" if event_id != 33 else "regular",
                starts_at=M.datetime(2026, 11, 20 + event_id - 33),
                ends_at=M.datetime(2026, 11, 20 + event_id - 33),
                status="closed",
                is_published=True,
            )
            db.session.add(event)
        db.session.commit()

        # Befehl aufrufen
        runner = app.test_cli_runner()
        result = runner.invoke(args=["configure-bccs-startnumbers", "--dry-run"])
        assert result.exit_code == 0, result.output
        assert "Events bereit" in result.output

        # Jetzt ohne --dry-run
        result = runner.invoke(args=["configure-bccs-startnumbers"])
        assert result.exit_code == 0, result.output
        assert "3 Events aktualisiert" in result.output

        # Verifiziere, dass alle Events das Schema haben
        expected_schema = {
            "Intermediate-1": 101, "Intermediate-2": 111, "Intermediate-3": 121,
            "Large-1": 201, "Large-2": 211, "Large-3": 221,
        }
        for event_id in [33, 34, 35]:
            event = db.session.get(M.Event, event_id)
            actual_schema = json.loads(event.startnumber_schema) if event.startnumber_schema else {}
            assert actual_schema == expected_schema


def test_bccs_assign_startnumbers_full_flow(app):
    """
    Voller Flow: BCCS-Event mit registrierten Teilnehmern → Startnummern-Vergabe.
    """
    with app.app_context():
        club = M.Club(vereinsnummer="BCCS", name="BCCS Club")
        admin = M.User(email="admin@test.ch", role="superadmin")
        db.session.add_all([club, admin])
        db.session.flush()

        # Event mit BCCS-Schema
        schema = {
            "Intermediate-1": 101,
            "Intermediate-2": 111,
            "Intermediate-3": 121,
            "Large-1": 201,
            "Large-2": 211,
            "Large-3": 221,
        }
        event = M.Event(
            name="BCCS Test",
            organiser_club_id=club.id,
            startnumber_schema=json.dumps(schema),
            type="bccs_sm",
            status="open",
        )
        db.session.add(event)
        db.session.flush()

        # Registrierungen: 2× Large-3, 1× Intermediate-2
        regs = []
        for i, (cat, kl) in enumerate([("Large", 3), ("Large", 3), ("Intermediate", 2)]):
            dog = M.Dog(name=f"Dog{i}", license_no=f"1000{i}", license_kind=M.LicenseKind.CH)
            person = M.Person(first_name=f"HF{i}", last_name="Test")
            db.session.add_all([dog, person])
            db.session.flush()
            reg = M.Registration(
                event_id=event.id, dog_id=dog.id, handler_id=person.id,
                status=M.RegistrationStatus.CONFIRMED, class_level=kl,
                category_code=cat,
            )
            db.session.add(reg)
            regs.append(reg)

        db.session.commit()

        # Startnummern-Vergabe
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["_user_id"] = str(admin.id)
            sess["_fresh"] = True

        resp = client.post(f"/club/events/{event.id}/assign-startnumbers")
        assert resp.status_code == 302

        # Verifiziere Startnummern
        db.session.refresh(regs[0])  # Large-3 #1
        db.session.refresh(regs[1])  # Large-3 #2
        db.session.refresh(regs[2])  # Intermediate-2

        # Large-3 sollte ab 221 nummeriert werden, Intermediate-2 ab 111
        # Die Reihenfolge ist zufällig (Reglement), aber die Ranges stimmen
        assert regs[0].start_number in range(221, 231)
        assert regs[1].start_number in range(221, 231)
        assert regs[2].start_number in range(111, 121)

        # Keine Duplikate
        assert regs[0].start_number != regs[1].start_number
