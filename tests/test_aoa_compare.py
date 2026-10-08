"""AOA-Vergleicher (Re-Import-Diff): neue / weggefallene / geänderte Anmeldungen.

Prüft das Dreibuckets-Diff gegen eine bereits importierte Anmeldeliste, die
selektive Anwendung per Lizenznummer und dass bestehende Startnummern bei
Nachzüglern unberührt bleiben (angehängte Nummer).
"""
import base64
import json
from datetime import datetime

from app.extensions import db
from app import models as M

HEADERS = ["Lizenz", "Hundename", "Kategorie", "Klasse",
           "Vorname", "Nachname", "Email", "Vereinnr"]


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _payload(rows):
    return base64.b64encode(json.dumps({
        "headers": HEADERS,
        "rows": [dict(zip(HEADERS, r)) for r in rows],
    }).encode("utf-8")).decode("ascii")


def _seed_event(start_numbers_done=False):
    club = M.Club(vereinsnummer="294", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, admin])
    db.session.flush()
    event = M.Event(name="Abgleich-Test", organiser_club_id=club.id)
    if start_numbers_done:
        event.start_numbers_generated_at = datetime.utcnow()
    db.session.add(event)
    db.session.commit()
    return event, admin


def _import(client, event_id, rows):
    resp = client.post("/admin/aoa-import/execute", data={
        "event_id": event_id, "csv_b64": _payload(rows),
    })
    assert resp.status_code in (302, 200)


def test_compare_detects_new_dropped_changed(app):
    with app.app_context():
        event, admin = _seed_event()
        event_id, admin_id = event.id, admin.id

        # Erstimport: 3 Hunde
        base_rows = [
            ["100", "Alpha", "Large", "3", "Anna", "A", "a@t.ch", "294"],
            ["200", "Bravo", "Medium", "2", "Bea", "B", "b@t.ch", "294"],
            ["300", "Charlie", "Small", "1", "Cem", "C", "c@t.ch", "294"],
        ]
        client = app.test_client()
        _login(client, admin_id)
        _import(client, event_id, base_rows)

        # Re-Import: 300 weg (Abmeldung), 200 Klasse 2->3 (geändert), 400 neu
        new_rows = [
            ["100", "Alpha", "Large", "3", "Anna", "A", "a@t.ch", "294"],
            ["200", "Bravo", "Medium", "3", "Bea", "B", "b@t.ch", "294"],
            ["400", "Delta", "Intermediate", "1", "Dan", "D", "d@t.ch", "294"],
        ]
        resp = client.post("/admin/aoa-import/compare/preview", data={
            "event_id": event_id, "csv_file": (_file(new_rows), "re.csv"),
        }, content_type="multipart/form-data")
        assert resp.status_code == 200
        html = resp.get_data(as_text=True)
        # Buckets im Rendering erkennbar
        assert "400" in html and "Delta" in html          # neu
        assert "300" in html and "Charlie" in html         # weggefallen
        assert "Bravo" in html and "Klasse" in html        # geändert (200: Kl. 2->3)

        # Anwenden: alles ausser der Klassenänderung (change nicht angehakt)
        resp = client.post("/admin/aoa-import/compare/execute", data={
            "event_id": event_id,
            "csv_b64": _payload(new_rows),
            "create_license": ["400"],
            "cancel_license": ["300"],
        })
        assert resp.status_code in (302, 200)

        regs = {_lic(r): r for r in db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id)
        ).scalars().all()}
        assert regs["400"].status == M.RegistrationStatus.CONFIRMED  # neu angelegt
        assert regs["300"].status == M.RegistrationStatus.CANCELLED  # abgemeldet
        assert regs["200"].class_level == 2   # Änderung NICHT angewandt (kein Häkchen)


def test_compare_new_entry_appends_start_number(app):
    with app.app_context():
        event, admin = _seed_event(start_numbers_done=True)
        event_id, admin_id = event.id, admin.id
        client = app.test_client()
        _login(client, admin_id)

        # Zwei Large-3-Hunde mit bereits vergebenen Startnummern
        _import(client, event_id, [
            ["100", "Alpha", "Large", "3", "Anna", "A", "a@t.ch", "294"],
            ["101", "Beta", "Large", "3", "Bea", "B", "b@t.ch", "294"],
        ])
        for lic, nr in (("100", 1301), ("101", 1302)):
            reg = _reg_for(event_id, lic)
            reg.start_number = nr
        db.session.commit()

        # Nachzügler in Large-3
        new_rows = [
            ["100", "Alpha", "Large", "3", "Anna", "A", "a@t.ch", "294"],
            ["101", "Beta", "Large", "3", "Bea", "B", "b@t.ch", "294"],
            ["102", "Gamma", "Large", "3", "Gea", "G", "g@t.ch", "294"],
        ]
        resp = client.post("/admin/aoa-import/compare/execute", data={
            "event_id": event_id,
            "csv_b64": _payload(new_rows),
            "create_license": ["102"],
        })
        assert resp.status_code in (302, 200)

        # Bestehende Nummern unverändert, Nachzügler angehängt (max+1)
        assert _reg_for(event_id, "100").start_number == 1301
        assert _reg_for(event_id, "101").start_number == 1302
        assert _reg_for(event_id, "102").start_number == 1303


def _file(rows):
    import io
    lines = [";".join(HEADERS)]
    for r in rows:
        lines.append(";".join(r))
    return io.BytesIO("\n".join(lines).encode("utf-8"))


def _lic(reg):
    return db.session.get(M.Dog, reg.dog_id).license_no


def _reg_for(event_id, lic):
    dog = db.session.execute(
        db.select(M.Dog).filter_by(license_no=lic)).scalars().first()
    return db.session.execute(
        db.select(M.Registration).filter_by(event_id=event_id, dog_id=dog.id)
    ).scalars().first()
