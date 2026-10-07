"""Regressionstest: AOA-Import darf verschiedene Personen mit gemeinsamer
Familien-E-Mail (z.B. Ehepaar) NICHT auf denselben Handler mappen.

Prod-Befund Event 9/16 (2026-10-07): Océane und Pascal Mauroux teilen sich die
Kontakt-E-Mail kudelski.irene@bluewin.ch in der SportyDog-/AOA-Startliste. Der
Import matchte bisher zuerst per E-Mail (ohne Namensabgleich) -> Pascals 5
Meldungen landeten auf Océanes Person-Datensatz (7 Regs auf 1 Handler statt
2 getrennte Personen). Das verfälschte u.a. die Startnummern-Lückenberechnung
(event_assign_startnumbers sah einen Handler mit 7 statt 2 bzw. 5 Hunden).
"""
import base64
import json

from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _build_payload(rows):
    headers = ["Lizenz", "Hundename", "Kategorie", "Klasse",
               "Vorname", "Nachname", "Email", "Vereinnr"]
    payload = {
        "headers": headers,
        "rows": [dict(zip(headers, r)) for r in rows],
    }
    return base64.b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def test_shared_family_email_does_not_merge_different_handlers(app):
    with app.app_context():
        club = M.Club(vereinsnummer="V1", name="Club")
        admin = M.User(email="admin@test.ch", role="superadmin")
        db.session.add_all([club, admin])
        db.session.flush()
        event = M.Event(name="Import-Test", organiser_club_id=club.id)
        db.session.add(event)
        db.session.commit()
        event_id, admin_id = event.id, admin.id

        shared_email = "kudelski.irene@bluewin.ch"
        rows = [
            # Océane: ein Hund, Small Kl.3
            ["15710", "Nyx's Crazy Style", "Small", "3",
             "Océane", "Mauroux", shared_email, "294"],
            # Pascal: zwei Hunde, Large Kl.2/Kl.3 — teilt sich die E-Mail
            ["17100", "Fast Folly", "Large", "2",
             "Pascal", "Mauroux", shared_email, "294"],
            ["13877", "Djinn' Tomic Folly", "Large", "3",
             "Pascal", "Mauroux", shared_email, "294"],
        ]
        csv_b64 = _build_payload(rows)

        client = app.test_client()
        _login(client, admin_id)
        resp = client.post("/admin/aoa-import/execute", data={
            "event_id": event_id,
            "csv_b64": csv_b64,
        })
        assert resp.status_code in (302, 200)

        regs = db.session.execute(
            db.select(M.Registration).filter_by(event_id=event_id)
        ).scalars().all()
        assert len(regs) == 3

        by_license = {}
        for r in regs:
            dog = db.session.get(M.Dog, r.dog_id)
            by_license[dog.license_no] = r

        oceane_handler = by_license["15710"].handler_id
        pascal_handler_1 = by_license["17100"].handler_id
        pascal_handler_2 = by_license["13877"].handler_id

        # Pascals beide Hunde auf demselben (einen) Handler.
        assert pascal_handler_1 == pascal_handler_2
        # Aber NICHT derselbe Handler wie Océane — das war der Bug.
        assert oceane_handler != pascal_handler_1

        oceane = db.session.get(M.Person, oceane_handler)
        pascal = db.session.get(M.Person, pascal_handler_1)
        assert oceane.first_name == "Océane"
        assert pascal.first_name == "Pascal"
        assert oceane.email == shared_email
        assert pascal.email == shared_email
