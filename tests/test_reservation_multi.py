"""
Tests für Mehr-Turnier-Reservationen (Variante a: mehrere Events teilen sich
eine AdminPortal-Reservation).

Deckt die Service-Schicht `reservation_sync.update_reservation` ab:
- `events`-Array enthält ALLE Events der Reservation (Haupt-Turnier zuerst)
- Einzel-Reservation sendet weiterhin genau ein Event
- `requests.patch` wird gemockt (kein echter AdminPortal-Call)
"""
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Event
from app.services import reservation_sync


class _FakeResp:
    def raise_for_status(self):
        pass

    def json(self):
        return {"id": 42}


@pytest.fixture()
def cfg(app):
    with app.app_context():
        app.config["WEBSITE_API_URL"] = "https://admin.example.test"
        app.config["WEBSITE_API_TOKEN"] = "tok"
        yield app


def _capture_patch(monkeypatch):
    captured = {}

    def fake_patch(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return _FakeResp()

    monkeypatch.setattr(reservation_sync.requests, "patch", fake_patch)
    return captured


def test_update_sends_all_group_events(cfg, monkeypatch):
    with cfg.app_context():
        e1 = Event(name="Tag 1", starts_at=datetime(2027, 5, 1),
                   ais_turniernummer=12345, max_participants=100, reservation_id=42)
        e2 = Event(name="Tag 2", starts_at=datetime(2027, 5, 2),
                   ais_turniernummer=12346, max_participants=80, reservation_id=42)
        db.session.add_all([e1, e2])
        db.session.commit()

        captured = _capture_patch(monkeypatch)
        ok, err = reservation_sync.update_reservation(e2)
        assert ok, err

        payload = captured["json"]
        assert captured["url"].endswith("/api/reservations/42")
        # Haupt-Turnier = frühestes Datum (Tag 1) füllt die Einzel-Spalten
        assert payload["ais_turniernummer"] == 12345
        assert payload["event_name"] == "Tag 1"
        # Summierte Teilnehmerschätzung
        assert payload["estimated_participants"] == 180
        # events-Array enthält beide, Tag 1 zuerst
        ais = [e["portal_event_id"] for e in payload["events"]]
        assert ais == [e1.id, e2.id]
        # beide Events bekommen einen Sync-Stempel
        assert e1.reservation_synced_at is not None
        assert e2.reservation_synced_at is not None


def test_update_single_event_still_sends_one(cfg, monkeypatch):
    with cfg.app_context():
        e = Event(name="Solo", starts_at=datetime(2027, 6, 1),
                  ais_turniernummer=999, max_participants=50, reservation_id=7)
        db.session.add(e)
        db.session.commit()

        captured = _capture_patch(monkeypatch)
        ok, err = reservation_sync.update_reservation(e)
        assert ok, err

        payload = captured["json"]
        assert len(payload["events"]) == 1
        assert payload["events"][0]["portal_event_id"] == e.id
        assert payload["estimated_participants"] == 50
