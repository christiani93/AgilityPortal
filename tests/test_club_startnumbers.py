"""
Regressionstest für die Schema-basierte Startnummernvergabe im Club-UI
(event_assign_startnumbers) — der produktiv genutzte Weg, im Unterschied zum
verwaisten Admin-Blueprint (routes_start_numbers.py / StartNumber-Tabelle),
das nie ein Template hatte und entfernt wurde (Crashes #94/#95/#96).

Deckt den vollen Kreis ab: gespeichertes startnumber_schema -> Vergabe auf
Registration.start_number -> Export-ZIP (start_numbers.json), wie es die
AgilitySoftware beim Import erwartet.
"""
import json
import zipfile
import io

from app.extensions import db
from app import models as M


def _seed_event_with_schema(start_last=True):
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()

    event = M.Event(
        name="Startnummer-Test",
        organiser_club_id=club.id,
        startnumber_schema=json.dumps({"Large-1": 5000}),
        allows_bitches_in_season=True,
        bitches_in_season_start_last=start_last,
    )
    db.session.add(event)
    db.session.flush()

    def _reg(i, handler_id_tag, is_in_season=False, status=M.RegistrationStatus.CONFIRMED):
        dog = M.Dog(name=f"Dog_{i}", license_no=f"{20000 + i}", license_kind=M.LicenseKind.CH)
        person = M.Person(first_name=f"HF{handler_id_tag}", last_name="Name")
        db.session.add_all([dog, person])
        db.session.flush()
        reg = M.Registration(
            event_id=event.id, dog_id=dog.id, handler_id=person.id,
            status=status, class_level=1, category_code="Large",
            is_in_season=is_in_season,
        )
        db.session.add(reg)
        return reg

    # Drei bestätigte Meldungen mit unterschiedlichen Handlern, eine läufig.
    reg_a = _reg(1, "A")
    reg_season = _reg(2, "B", is_in_season=True)
    reg_c = _reg(3, "C")
    # Eine nicht-bestätigte Meldung darf keine Startnummer bekommen.
    reg_pending = _reg(4, "D", status=M.RegistrationStatus.SUBMITTED)

    db.session.commit()
    return event.id, admin.id, reg_a.id, reg_season.id, reg_c.id, reg_pending.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_assign_startnumbers_uses_saved_schema_and_skips_unconfirmed(app):
    with app.app_context():
        event_id, admin_id, reg_a_id, reg_season_id, reg_c_id, reg_pending_id = _seed_event_with_schema()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/assign-startnumbers")
        assert resp.status_code == 302

        reg_a = db.session.get(M.Registration, reg_a_id)
        reg_season = db.session.get(M.Registration, reg_season_id)
        reg_c = db.session.get(M.Registration, reg_c_id)
        reg_pending = db.session.get(M.Registration, reg_pending_id)

        # Basis aus dem gespeicherten Schema (nicht dem Default!), läufig ans Ende.
        assert reg_a.start_number == 5000
        assert reg_c.start_number == 5001
        assert reg_season.start_number == 5002

        # Unbestätigte Meldung bleibt unangetastet.
        assert reg_pending.start_number is None


def test_assign_startnumbers_ignores_in_season_when_flag_off(app):
    # Ohne bitches_in_season_start_last zählt is_in_season NICHT für die
    # Reihenfolge — die läufige Hündin wird nicht ans Ende gezwungen.
    with app.app_context():
        event_id, admin_id, reg_a_id, reg_season_id, reg_c_id, reg_pending_id = \
            _seed_event_with_schema(start_last=False)
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/assign-startnumbers")
        assert resp.status_code == 302

        reg_a = db.session.get(M.Registration, reg_a_id)
        reg_season = db.session.get(M.Registration, reg_season_id)
        reg_c = db.session.get(M.Registration, reg_c_id)

        # Stabile Reihenfolge nach handler_id (A, B=läufig, C) — nicht ans Ende.
        assert reg_a.start_number == 5000
        assert reg_season.start_number == 5001
        assert reg_c.start_number == 5002


def test_organiser_toggle_in_season_keeps_startnumber(app):
    # Veranstalter markiert eine Hündin als läufig, NACHDEM Startnummern
    # vergeben wurden — die Startnummer bleibt erhalten.
    with app.app_context():
        event_id, admin_id, reg_a_id, reg_season_id, reg_c_id, reg_pending_id = \
            _seed_event_with_schema()
        client = app.test_client()
        _login(client, admin_id)
        client.post(f"/club/events/{event_id}/assign-startnumbers")

        reg_a = db.session.get(M.Registration, reg_a_id)
        assert reg_a.start_number == 5000
        assert reg_a.is_in_season is False

        resp = client.post(f"/club/registrations/{reg_a_id}/toggle-in-season-admin")
        assert resp.status_code == 302
        reg_a = db.session.get(M.Registration, reg_a_id)
        assert reg_a.is_in_season is True
        assert reg_a.start_number == 5000   # Nummer unverändert

        # Nochmal togglen hebt die Markierung wieder auf.
        client.post(f"/club/registrations/{reg_a_id}/toggle-in-season-admin")
        reg_a = db.session.get(M.Registration, reg_a_id)
        assert reg_a.is_in_season is False
        assert reg_a.start_number == 5000


def _seed_event_multidog(n, handler_dog_count, base=5000):
    """Ein Block mit `n` Startern; ein Handler besitzt `handler_dog_count`
    Hunde, der Rest je einen. Gibt (event_id, admin_id, multi_reg_ids) zurück.
    """
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()

    event = M.Event(
        name="Gap-Test",
        organiser_club_id=club.id,
        startnumber_schema=json.dumps({"Large-1": base}),
        allows_bitches_in_season=True,
        bitches_in_season_start_last=False,
    )
    db.session.add(event)
    db.session.flush()

    # Multi-Hund-Handler (eine Person, mehrere Hunde)
    multi = M.Person(first_name="Multi", last_name="Handler")
    db.session.add(multi)
    db.session.flush()

    multi_reg_ids = []
    for i in range(handler_dog_count):
        dog = M.Dog(name=f"MultiDog_{i}", license_no=f"{30000 + i}",
                    license_kind=M.LicenseKind.CH)
        db.session.add(dog)
        db.session.flush()
        reg = M.Registration(
            event_id=event.id, dog_id=dog.id, handler_id=multi.id,
            status=M.RegistrationStatus.CONFIRMED,
            class_level=1, category_code="Large",
        )
        db.session.add(reg)
        db.session.flush()
        multi_reg_ids.append(reg.id)

    # Rest: Einzelhund-Handler, bis der Block `n` Starter hat
    for i in range(n - handler_dog_count):
        dog = M.Dog(name=f"SoloDog_{i}", license_no=f"{40000 + i}",
                    license_kind=M.LicenseKind.CH)
        person = M.Person(first_name=f"Solo{i}", last_name="Handler")
        db.session.add_all([dog, person])
        db.session.flush()
        reg = M.Registration(
            event_id=event.id, dog_id=dog.id, handler_id=person.id,
            status=M.RegistrationStatus.CONFIRMED,
            class_level=1, category_code="Large",
        )
        db.session.add(reg)

    db.session.commit()
    return event.id, admin.id, multi_reg_ids


def test_tight_spread_pushes_multidog_handler_to_extremes(app):
    # Spreizung Block/N < 20 (hier 20/2 = 10): die beiden Hunde desselben
    # Handlers werden maximal gespreizt → Abstand = Block-Länge - 1 (erster/
    # letzter Slot), nicht nur Block/N.
    with app.app_context():
        n = 20
        event_id, admin_id, multi_ids = _seed_event_multidog(n, handler_dog_count=2)
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/assign-startnumbers")
        assert resp.status_code == 302

        nums = sorted(db.session.get(M.Registration, rid).start_number
                      for rid in multi_ids)
        assert nums[1] - nums[0] == n - 1      # Block/(N-1) bei N=2 → Extreme


def test_roomy_block_distributes_multidog_handler_evenly(app):
    # Spreizung Block/N >= 20 (hier 40/2 = 20): gleichmässige Verteilung → Abstand
    # Block/N, NICHT maximal gespreizt (kein Zwang auf ersten/letzten Slot).
    with app.app_context():
        n = 40
        event_id, admin_id, multi_ids = _seed_event_multidog(n, handler_dog_count=2)
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/assign-startnumbers")
        assert resp.status_code == 302

        nums = sorted(db.session.get(M.Registration, rid).start_number
                      for rid in multi_ids)
        assert nums[1] - nums[0] == n // 2     # Block/N bei N=2 → 20
        assert nums[1] - nums[0] < n - 1       # gerade NICHT auf die Extreme


def test_export_zip_reflects_assigned_startnumbers(app):
    with app.app_context():
        event_id, admin_id, reg_a_id, reg_season_id, reg_c_id, reg_pending_id = _seed_event_with_schema()
        client = app.test_client()
        _login(client, admin_id)

        client.post(f"/club/events/{event_id}/assign-startnumbers")

        resp = client.get(f"/club/events/{event_id}/export.zip")
        assert resp.status_code == 200

        with zipfile.ZipFile(io.BytesIO(resp.data)) as zf:
            payload = json.loads(zf.read("start_numbers.json"))

        # Format, das die AgilitySoftware beim Import akzeptiert (Schlüssel "start_numbers").
        assert payload["locked"] is True
        by_license = {e["license_no"]: e["start_no"] for e in payload["start_numbers"]}
        assert by_license["20001"] == 5000
        assert by_license["20003"] == 5001
        assert by_license["20002"] == 5002
        # Unbestätigte Meldung taucht gar nicht erst auf.
        assert "20004" not in by_license
