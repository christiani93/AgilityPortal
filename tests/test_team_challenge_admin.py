"""
Tests für die Portal-Admin-Teamauswahl (Team-Challenge, P5).

Deckt die echte HTTP-Route `team_admin.*` ab: Team bilden (Validierung gegen
Grösse/Level/Doppelvergabe), Eignungsliste, Löschen. DB ist In-Memory-SQLite
(conftest `app`-Fixture), Zugriff via ADMIN_KEY.
"""
import pytest

from app.extensions import db
from app.models import (Dog, Event, LicenseKind, Person, Registration, Team)


ADMIN_KEY = "testkey"


@pytest.fixture()
def seeded(app):
    """Event + mehrere Large-Registrations (Kl. 1/2/3) für Team-Bildung."""
    with app.app_context():
        app.config["ADMIN_KEY"] = ADMIN_KEY
        event = Event(name="Edelweiss Team-Test", type="regular",
                      special_ruleset="edelweiss_challenge", status="open")
        db.session.add(event)
        db.session.commit()

        regs = {}
        specs = [
            ("L1", "1001", "Large", 2),
            ("L2", "1002", "Large", 1),
            ("L3", "1003", "Large", 2),
            ("E1", "1004", "Large", 3),
            ("E2", "1005", "Large", 3),
            ("M1", "1006", "Medium", 2),
        ]
        for key, lic, cat, cls in specs:
            person = Person(first_name=key, last_name="Tester")
            dog = Dog(name=f"Hund {key}", license_no=lic, license_kind=LicenseKind.CH)
            db.session.add_all([person, dog])
            db.session.commit()
            reg = Registration(event_id=event.id, dog_id=dog.id, handler_id=person.id,
                               category_code=cat, class_level=cls)
            db.session.add(reg)
            db.session.commit()
            regs[key] = reg.id

        return {"event_id": event.id, "regs": regs}


def _client(app):
    return app.test_client()


def _add(client, event_id, cat, level, agi, jump, name=""):
    return client.post(
        f"/admin/events/{event_id}/teams/add",
        query_string={"key": ADMIN_KEY},
        data={"category_code": cat, "level": level,
              "member_agility_registration_id": agi,
              "member_jumping_registration_id": jump, "name": name},
    )


def test_config_page_renders(app, seeded):
    client = _client(app)
    resp = client.get(f"/admin/events/{seeded['event_id']}/teams",
                      query_string={"key": ADMIN_KEY})
    assert resp.status_code == 200
    assert b"Team-Challenge" in resp.data


def test_requires_admin_key(app, seeded):
    client = _client(app)
    resp = client.get(f"/admin/events/{seeded['event_id']}/teams")
    assert resp.status_code == 403


def test_add_valid_soft_team(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    resp = _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["L2"], "Die Schnellen")
    assert resp.status_code == 302

    with app.app_context():
        teams = Team.query.filter_by(event_id=seeded["event_id"]).all()
        assert len(teams) == 1
        t = teams[0]
        assert t.category_code == "Large"
        assert t.level == "soft"
        assert t.member_agility_registration_id == regs["L1"]
        assert t.member_jumping_registration_id == regs["L2"]
        assert t.source == "portal"
        assert t.external_id  # Round-Trip-Schlüssel automatisch gesetzt


def test_reject_reused_registration(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["L2"])
    # L1 erneut -> muss abgelehnt werden
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["L3"])
    with app.app_context():
        assert Team.query.filter_by(event_id=seeded["event_id"]).count() == 1


def test_reject_category_mismatch(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    # M1 ist Medium, Team soll Large sein
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["M1"])
    with app.app_context():
        assert Team.query.filter_by(event_id=seeded["event_id"]).count() == 0


def test_reject_wrong_level_class(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    # E1 ist Klasse 3 -> passt nicht zu soft (Kl. 1+2)
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["E1"])
    with app.app_context():
        assert Team.query.filter_by(event_id=seeded["event_id"]).count() == 0


def test_expert_team_with_class3(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    resp = _add(client, seeded["event_id"], "Large", "expert", regs["E1"], regs["E2"])
    assert resp.status_code == 302
    with app.app_context():
        t = Team.query.filter_by(event_id=seeded["event_id"]).one()
        assert t.level == "expert"


def test_delete_team(app, seeded):
    client = _client(app)
    regs = seeded["regs"]
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["L2"])
    with app.app_context():
        team_id = Team.query.filter_by(event_id=seeded["event_id"]).one().id

    resp = client.post(
        f"/admin/events/{seeded['event_id']}/teams/{team_id}/delete",
        query_string={"key": ADMIN_KEY})
    assert resp.status_code == 302
    with app.app_context():
        assert Team.query.filter_by(event_id=seeded["event_id"]).count() == 0


def test_eligible_excludes_used_registration(app, seeded):
    from app.blueprints.admin.routes_team_challenge import _eligible_registrations
    regs = seeded["regs"]
    with app.app_context():
        before = {r.id for r in _eligible_registrations(seeded["event_id"], "Large", "soft")}
        assert regs["L1"] in before and regs["L2"] in before

    client = _client(app)
    _add(client, seeded["event_id"], "Large", "soft", regs["L1"], regs["L2"])

    with app.app_context():
        after = {r.id for r in _eligible_registrations(seeded["event_id"], "Large", "soft")}
        assert regs["L1"] not in after and regs["L2"] not in after
        assert regs["L3"] in after  # noch frei
