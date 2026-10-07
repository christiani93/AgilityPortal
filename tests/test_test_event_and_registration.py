"""
Tests für:
  - Testevent-Sichtbarkeit: Veranstalter sieht eigene Testevents (event_info),
    fremder Verein nicht, Superadmin immer.
  - Anmelde-Guard: Selbst-Anmeldung nur in angebotene Kategorie/Klasse.
  - Testkopie eines Turniers (event_duplicate_as_test).
  - Öffentliche Infokarte zeigt Wettbewerbe.
"""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_club_admin():
    club = M.Club(vereinsnummer="C1", name="Club C")
    other = M.Club(vereinsnummer="C2", name="Club D")
    admin = M.User(email="admin@test.ch", role="club_admin")
    other_admin = M.User(email="other@test.ch", role="club_admin")
    db.session.add_all([club, other, admin, other_admin])
    db.session.flush()
    admin.club_id = club.id
    other_admin.club_id = other.id
    db.session.commit()
    return club, other, admin, other_admin


# ── Testevent-Sichtbarkeit ────────────────────────────────────────────────

def test_organiser_sees_own_test_event(app):
    with app.app_context():
        club, other, admin, other_admin = _seed_club_admin()
        ev = M.Event(name="Testturnier", organiser_club_id=club.id,
                     status="open", is_test=True)
        db.session.add(ev)
        db.session.commit()
        eid = ev.id

        client = app.test_client()
        _login(client, admin.id)
        resp = client.get(f"/club/events/{eid}/info")
        assert resp.status_code == 200


def test_foreign_organiser_cannot_see_test_event(app):
    with app.app_context():
        club, other, admin, other_admin = _seed_club_admin()
        ev = M.Event(name="Testturnier", organiser_club_id=club.id,
                     status="open", is_test=True)
        db.session.add(ev)
        db.session.commit()
        eid = ev.id

        client = app.test_client()
        _login(client, other_admin.id)
        resp = client.get(f"/club/events/{eid}/info")
        assert resp.status_code == 404


def test_superadmin_sees_any_test_event(app):
    with app.app_context():
        club, other, admin, other_admin = _seed_club_admin()
        sa = M.User(email="sa@test.ch", role="superadmin")
        db.session.add(sa)
        ev = M.Event(name="Testturnier", organiser_club_id=club.id,
                     status="open", is_test=True)
        db.session.add(ev)
        db.session.commit()
        eid, sid = ev.id, sa.id

        client = app.test_client()
        _login(client, sid)
        resp = client.get(f"/club/events/{eid}/info")
        assert resp.status_code == 200


# ── Anmelde-Guard: keine Anmeldung in nicht angebotene Klasse ─────────────

def _seed_superadmin_with_dog(category="L", class_level=3):
    sa = M.User(email="sa@test.ch", role="superadmin")
    person = M.Person(first_name="Max", last_name="Muster")
    db.session.add_all([sa, person])
    db.session.flush()
    sa.person_id = person.id
    dog = M.Dog(name="Rex", license_no="999001", license_kind=M.LicenseKind.CH,
                category=category, class_level=class_level)
    db.session.add(dog)
    db.session.flush()
    db.session.add(M.DogOwner(dog_id=dog.id, person_id=person.id,
                              role=M.DogOwnerRole.OWNER))
    db.session.commit()
    return sa, person, dog


def test_registration_rejected_for_unoffered_class(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        sa, person, dog = _seed_superadmin_with_dog(category="L", class_level=3)
        ev = M.Event(name="Turnier", status="open")
        db.session.add(ev)
        db.session.flush()
        # Turnier bietet nur Large Klasse 1 an
        db.session.add(M.EventRun(event_id=ev.id, run_type="agility",
                                  category="L", class_level=1))
        db.session.commit()
        eid, did = ev.id, dog.id

        client = app.test_client()
        _login(client, sa.id)
        resp = client.post(f"/club/events/{eid}/view", data={
            "dog_id": str(did), "class_level": "3",
        })
        assert resp.status_code == 302
        count = M.Registration.query.filter_by(event_id=eid).count()
        assert count == 0


def test_registration_allowed_for_offered_class(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        sa, person, dog = _seed_superadmin_with_dog(category="L", class_level=1)
        ev = M.Event(name="Turnier", status="open")
        db.session.add(ev)
        db.session.flush()
        db.session.add(M.EventRun(event_id=ev.id, run_type="agility",
                                  category="L", class_level=1))
        db.session.commit()
        eid, did = ev.id, dog.id

        client = app.test_client()
        _login(client, sa.id)
        resp = client.post(f"/club/events/{eid}/view", data={
            "dog_id": str(did), "class_level": "1",
        })
        assert resp.status_code == 302
        reg = M.Registration.query.filter_by(event_id=eid).one()
        assert reg.category_code == "Large"
        assert reg.class_level == 1


# ── Testkopie ──────────────────────────────────────────────────────────────

def test_duplicate_as_test_copies_runs_and_regs(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, other, admin, other_admin = _seed_club_admin()
        ev = M.Event(name="Freitag", organiser_club_id=club.id, status="open",
                     ais_turniernummer=11338, external_id="EXT-9",
                     is_published=True, ring_count=2)
        db.session.add(ev)
        db.session.flush()
        run = M.EventRun(event_id=ev.id, run_type="agility", category="L", class_level=1)
        db.session.add(run)
        dog = M.Dog(name="Rex", license_no="999002", license_kind=M.LicenseKind.CH,
                    category="L", class_level=1)
        db.session.add(dog)
        db.session.flush()
        db.session.add(M.Registration(event_id=ev.id, dog_id=dog.id,
                                      category_code="Large", class_level=1,
                                      status=M.RegistrationStatus.CONFIRMED,
                                      external_id="REG-X"))
        db.session.add(M.ScheduleBlock(event_id=ev.id, ring="Ring 1",
                                       block_type="run", discipline="agility",
                                       category_code="Large", class_level=1,
                                       event_run_id=run.id, sort_index=10))
        db.session.commit()
        eid = ev.id

        client = app.test_client()
        _login(client, admin.id)
        resp = client.post(f"/club/events/{eid}/duplicate-as-test")
        assert resp.status_code == 302

        copy = M.Event.query.filter(M.Event.id != eid,
                                    M.Event.organiser_club_id == club.id).one()
        assert copy.is_test is True
        assert copy.is_published is False
        assert copy.ais_turniernummer is None
        assert copy.external_id is None
        assert copy.name.endswith("(TEST)")
        assert M.EventRun.query.filter_by(event_id=copy.id).count() == 1
        assert M.Registration.query.filter_by(event_id=copy.id).count() == 1
        copy_reg = M.Registration.query.filter_by(event_id=copy.id).one()
        assert copy_reg.external_id is None
        # Zeitplan-Block zeigt auf den Lauf der KOPIE, nicht des Originals
        copy_block = M.ScheduleBlock.query.filter_by(event_id=copy.id).one()
        copy_run = M.EventRun.query.filter_by(event_id=copy.id).one()
        assert copy_block.event_run_id == copy_run.id


def test_duplicate_as_test_forbidden_for_foreign_club(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, other, admin, other_admin = _seed_club_admin()
        ev = M.Event(name="Freitag", organiser_club_id=club.id, status="open")
        db.session.add(ev)
        db.session.commit()
        eid = ev.id

        client = app.test_client()
        _login(client, other_admin.id)
        resp = client.post(f"/club/events/{eid}/duplicate-as-test")
        assert resp.status_code == 403


# ── Öffentliche Infokarte: Wettbewerbe ────────────────────────────────────

def test_public_overview_shows_competitions(app):
    with app.app_context():
        club, other, admin, other_admin = _seed_club_admin()
        ev = M.Event(name="Offenes Turnier", organiser_club_id=club.id,
                     status="open", is_published=True)
        db.session.add(ev)
        db.session.flush()
        db.session.add_all([
            M.EventRun(event_id=ev.id, run_type="agility", category="L", class_level=1),
            M.EventRun(event_id=ev.id, run_type="jumping", category="S", class_level=2),
        ])
        db.session.commit()
        eid = ev.id

        client = app.test_client()
        resp = client.get(f"/events/{eid}")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Wettbewerbe" in body
        assert "Agility" in body
        assert "Jumping" in body
