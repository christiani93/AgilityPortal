"""
Tests für die Spezialturnier-Freigabe (SpecialRulesetAllowedClub).

Deckt ab:
  - Event.special_ruleset_allows_club (unrestricted vs. restricted)
  - Club-Self-Service event_edit: nicht freigegebenes Ruleset wird abgelehnt,
    bereits gesetzter Wert blockiert aber nicht das restliche Formular
  - Club-Self-Service Turnier-Vorlagen (template_list / template_create_event):
    nur der Veranstalter-Verein der Vorlage darf sie nutzen
  - Admin-Route special_ruleset_edit setzt die Freigabe korrekt
"""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_two_clubs():
    club_a = M.Club(vereinsnummer="A1", name="Club A")
    club_b = M.Club(vereinsnummer="B1", name="Club B")
    admin_a = M.User(email="a@test.ch", role="club_admin")
    admin_b = M.User(email="b@test.ch", role="club_admin")
    db.session.add_all([club_a, club_b, admin_a, admin_b])
    db.session.flush()
    admin_a.club_id = club_a.id
    admin_b.club_id = club_b.id
    db.session.commit()
    return club_a, club_b, admin_a, admin_b


# ── Model-Helper ──────────────────────────────────────────────────────────

def test_allows_club_open_when_no_restriction(app):
    with app.app_context():
        club_a, club_b, _, _ = _seed_two_clubs()
        assert M.Event.special_ruleset_allows_club("edelweiss_challenge", club_a.id) is True
        assert M.Event.special_ruleset_allows_club("edelweiss_challenge", club_b.id) is True
        assert M.Event.special_ruleset_restricts("edelweiss_challenge") is False


def test_allows_club_restricted_to_allowlist(app):
    with app.app_context():
        club_a, club_b, _, _ = _seed_two_clubs()
        db.session.add(M.SpecialRulesetAllowedClub(ruleset="edelweiss_challenge", club_id=club_a.id))
        db.session.commit()
        assert M.Event.special_ruleset_restricts("edelweiss_challenge") is True
        assert M.Event.special_ruleset_allows_club("edelweiss_challenge", club_a.id) is True
        assert M.Event.special_ruleset_allows_club("edelweiss_challenge", club_b.id) is False
        # Unrestricted ruleset bleibt unberührt
        assert M.Event.special_ruleset_allows_club("halloween_cup", club_b.id) is True


# ── Club-Self-Service: event_edit ────────────────────────────────────────

def test_event_edit_rejects_disallowed_ruleset(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        db.session.add(M.SpecialRulesetAllowedClub(ruleset="edelweiss_challenge", club_id=club_a.id))
        event = M.Event(name="Club-B-Turnier", organiser_club_id=club_b.id)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin_b.id)
        resp = client.post(f"/club/events/{event_id}/edit", data={
            "name": "Club-B-Turnier",
            "starts_at": "2026-05-01",
            "special_ruleset": "edelweiss_challenge",
        })
        # Kein Redirect -> Formular mit Validierungsfehler erneut angezeigt
        assert resp.status_code == 200
        db.session.refresh(event)
        assert event.special_ruleset is None


def test_event_edit_allows_ruleset_for_allowed_club(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        db.session.add(M.SpecialRulesetAllowedClub(ruleset="edelweiss_challenge", club_id=club_a.id))
        event = M.Event(name="Club-A-Turnier", organiser_club_id=club_a.id)
        db.session.add(event)
        db.session.commit()
        event_id = event.id

        client = app.test_client()
        _login(client, admin_a.id)
        resp = client.post(f"/club/events/{event_id}/edit", data={
            "name": "Club-A-Turnier",
            "starts_at": "2026-05-01",
            "special_ruleset": "edelweiss_challenge",
        })
        assert resp.status_code == 302
        db.session.refresh(event)
        assert event.special_ruleset == "edelweiss_challenge"


def test_event_edit_keeps_existing_value_when_allowlist_revoked_later(app):
    """Freigabe wird nach dem Setzen entzogen -> Formular bleibt trotzdem speicherbar,
    solange das Ruleset selbst nicht geändert wird."""
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        # Club B war mal erlaubt, Event wurde entsprechend getaggt ...
        event = M.Event(name="Alt", organiser_club_id=club_b.id, special_ruleset="edelweiss_challenge")
        db.session.add(event)
        db.session.commit()
        event_id = event.id
        # ... jetzt wird die Freigabe auf Club A beschränkt (Club B fliegt raus)
        db.session.add(M.SpecialRulesetAllowedClub(ruleset="edelweiss_challenge", club_id=club_a.id))
        db.session.commit()

        client = app.test_client()
        _login(client, admin_b.id)
        resp = client.post(f"/club/events/{event_id}/edit", data={
            "name": "Neu benannt",
            "starts_at": "2026-05-01",
            "special_ruleset": "edelweiss_challenge",
        })
        assert resp.status_code == 302
        db.session.refresh(event)
        assert event.name == "Neu benannt"
        assert event.special_ruleset == "edelweiss_challenge"


# ── Club-Self-Service: Turnier-Vorlagen ──────────────────────────────────

def test_template_list_shows_only_own_club_templates(app):
    with app.app_context():
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        tpl_a = M.EventTemplate(name="Vorlage A", organiser_club_id=club_a.id)
        tpl_b = M.EventTemplate(name="Vorlage B", organiser_club_id=club_b.id)
        db.session.add_all([tpl_a, tpl_b])
        db.session.commit()

        client = app.test_client()
        _login(client, admin_a.id)
        resp = client.get("/club/templates")
        assert resp.status_code == 200
        body = resp.get_data(as_text=True)
        assert "Vorlage A" in body
        assert "Vorlage B" not in body


def test_template_create_event_forbidden_for_other_club(app):
    with app.app_context():
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        tpl_a = M.EventTemplate(name="Vorlage A", organiser_club_id=club_a.id)
        db.session.add(tpl_a)
        db.session.commit()
        tpl_id = tpl_a.id

        client = app.test_client()
        _login(client, admin_b.id)
        resp = client.get(f"/club/templates/{tpl_id}/create-event")
        assert resp.status_code == 403


def test_template_create_event_works_for_own_club(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club_a, club_b, admin_a, admin_b = _seed_two_clubs()
        tpl_a = M.EventTemplate(name="Vorlage A", organiser_club_id=club_a.id, day_count=1)
        db.session.add(tpl_a)
        db.session.commit()
        tpl_id = tpl_a.id

        client = app.test_client()
        _login(client, admin_a.id)
        resp = client.post(f"/club/templates/{tpl_id}/create-event", data={
            "starts_at": "2026-06-01",
        })
        assert resp.status_code == 302
        created = M.Event.query.filter_by(source_template_id=tpl_id).one()
        assert created.organiser_club_id == club_a.id


# ── Admin: Freigabe-Verwaltung ───────────────────────────────────────────

def test_admin_special_ruleset_edit_sets_allowlist(app):
    with app.app_context():
        app.config["ADMIN_KEY"] = "testkey"
        club_a, club_b, _, _ = _seed_two_clubs()

        client = app.test_client()
        resp = client.post(
            "/admin/special-ruleset-assignments/edelweiss_challenge/edit?key=testkey",
            data={"allowed_club_ids": [str(club_a.id)]},
        )
        assert resp.status_code == 302
        allowed = M.Event.special_ruleset_allowed_club_ids("edelweiss_challenge")
        assert allowed == {club_a.id}
