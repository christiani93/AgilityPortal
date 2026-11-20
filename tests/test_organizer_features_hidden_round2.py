"""Fortsetzung der Veranstalter-Ausblend-Serie (siehe test_organizer_features_hidden.py):
Reservationsanfrage-Buttons, TKAMO-Agenda-"Turnier anlegen" (nur Superadmin,
da die TKAMO-Agenda keine Club-Zuordnung je Eintrag liefert) und
Mitgliederverwaltung (nur fuer Club-Admins ausgeblendet, Superadmin ausgenommen)."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed():
    club = M.Club(vereinsnummer="V1", name="Club")
    superadmin = M.User(email="super@test.ch", role="superadmin")
    club_admin = M.User(email="clubadmin@test.ch", role="club_admin", club=club)
    db.session.add_all([club, superadmin, club_admin])
    db.session.flush()
    event = M.Event(name="Event", organiser_club_id=club.id)
    db.session.add(event)
    db.session.commit()
    return event.id, superadmin.id, club_admin.id


# ── Reservationsanfrage ──────────────────────────────────────────────────────

def test_reservation_buttons_hidden_by_default(app):
    with app.app_context():
        event_id, superadmin_id, _ = _seed()
        client = app.test_client()
        _login(client, superadmin_id)

        resp = client.get(f"/club/events/{event_id}")
        html = resp.get_data(as_text=True)
        assert "Reservationsanfrage senden" not in html
        assert "über das AdminPortal" in html


def test_reservation_routes_404_by_default(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        event_id, superadmin_id, _ = _seed()
        client = app.test_client()
        _login(client, superadmin_id)

        assert client.post(f"/club/events/{event_id}/reservation-request",
                            data={"contact_name": "x", "contact_email": "x@y.ch"}).status_code == 404
        assert client.post(f"/club/events/{event_id}/reservation-sync").status_code == 404


def test_reservation_buttons_visible_when_flag_on(app):
    with app.app_context():
        app.config["ORGANIZER_RESERVATION_ACTIONS_ENABLED"] = True
        event_id, superadmin_id, _ = _seed()
        client = app.test_client()
        _login(client, superadmin_id)

        resp = client.get(f"/club/events/{event_id}")
        assert "Reservationsanfrage senden" in resp.get_data(as_text=True)


# ── TKAMO-Agenda ─────────────────────────────────────────────────────────────
# Je ein eigener Test (statt zwei Logins in einer Funktion): zwei sequentielle
# client.get()-Aufrufe mit unterschiedlichem Login auf dieselbe Route innerhalb
# eines Prozesses zeigten sich in dieser Umgebung als unzuverlässig (current_user
# im zweiten Request vereinzelt noch der erste) — eigener app-Fixture pro Test
# umgeht das sauber, ohne das eigentliche Verhalten (siehe Produktionsbetrieb:
# echte, unabhängige HTTP-Requests) in Frage zu stellen.

def _patch_agenda_api(monkeypatch):
    class _FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"entries": [{"ais": 999, "datum": "01.01.27", "name_ort": "Turnier X",
                                 "meldefrist": "", "kategorien": "", "status": ""}]}
    import requests as requests_module
    monkeypatch.setattr(requests_module, "get", lambda *a, **k: _FakeResp())


def test_agenda_create_button_hidden_for_club_admin(app, monkeypatch):
    with app.app_context():
        app.config["WEBSITE_API_URL"] = "https://fake"
        app.config["WEBSITE_API_TOKEN"] = "tok"
        _, _, club_admin_id = _seed()
        _patch_agenda_api(monkeypatch)

        client = app.test_client()
        _login(client, club_admin_id)
        resp = client.get("/club/agenda")
        assert "Turnier anlegen" not in resp.get_data(as_text=True)


def test_agenda_create_button_visible_for_superadmin(app, monkeypatch):
    with app.app_context():
        app.config["WEBSITE_API_URL"] = "https://fake"
        app.config["WEBSITE_API_TOKEN"] = "tok"
        _, superadmin_id, _ = _seed()
        _patch_agenda_api(monkeypatch)

        client = app.test_client()
        _login(client, superadmin_id)
        resp = client.get("/club/agenda")
        assert "Turnier anlegen" in resp.get_data(as_text=True)


# ── Mitgliederverwaltung ─────────────────────────────────────────────────────

def test_members_nav_and_route_hidden_for_club_admin_by_default(app):
    with app.app_context():
        _, superadmin_id, club_admin_id = _seed()
        client = app.test_client()
        _login(client, club_admin_id)

        resp = client.get("/club/")
        assert 'href="/club/users"' not in resp.get_data(as_text=True)
        assert client.get("/club/users").status_code == 404


def test_members_route_always_available_for_superadmin(app):
    with app.app_context():
        _, superadmin_id, _ = _seed()
        client = app.test_client()
        _login(client, superadmin_id)

        resp = client.get("/club/")
        assert "Alle Benutzer" in resp.get_data(as_text=True)
        assert client.get("/club/users").status_code == 200


def test_members_route_available_for_club_admin_when_flag_on(app):
    with app.app_context():
        app.config["ORGANIZER_MEMBER_MANAGEMENT_ENABLED"] = True
        _, _, club_admin_id = _seed()
        client = app.test_client()
        _login(client, club_admin_id)

        resp = client.get("/club/")
        assert "Mitglieder" in resp.get_data(as_text=True)
        assert client.get("/club/users").status_code == 200
