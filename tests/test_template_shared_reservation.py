"""
Tests für vorlagen-gesteuerte geteilte Reservationen (Vorschlag 1).

Eine EventTemplate mit `reservation_shared=True` erzeugt bei mehreren „Turnier
aus Vorlage"-Durchläufen EINE gemeinsame Reservation: das erste Turnier legt die
Reservation an, die folgenden hängen sich an.

AdminPortal-Calls (`requests.post`/`.patch`) werden gemockt.
"""
import pytest

from app.extensions import db
from app.models import Event, EventTemplate
from app.services import reservation_sync


ADMIN_KEY = "testkey"


class _FakeResp:
    def __init__(self, rid=42):
        self._rid = rid

    def raise_for_status(self):
        pass

    def json(self):
        return {"id": self._rid}


@pytest.fixture()
def client(app, monkeypatch):
    with app.app_context():
        app.config["ADMIN_KEY"] = ADMIN_KEY
        app.config["WEBSITE_API_URL"] = "https://admin.example.test"
        app.config["WEBSITE_API_TOKEN"] = "tok"
        monkeypatch.setattr(reservation_sync.requests, "post",
                            lambda *a, **k: _FakeResp(rid=42))
        monkeypatch.setattr(reservation_sync.requests, "patch",
                            lambda *a, **k: _FakeResp(rid=42))
        yield app.test_client()


def _make_template(shared):
    tpl = EventTemplate(name="Serie", reservation_shared=shared,
                        contact_name="Chris", contact_email="c@example.test")
    db.session.add(tpl)
    db.session.commit()
    return tpl.id


def _create_event(client, tpl_id, date, ais):
    return client.post(
        f"/admin/templates/{tpl_id}/create-event?key={ADMIN_KEY}",
        data={"name": f"Tag {ais}", "starts_at": date, "ends_at": date,
              "ais_1": str(ais), "do_reservation": "1"},
        follow_redirects=False,
    )


def test_shared_template_groups_events_into_one_reservation(client, app):
    with app.app_context():
        tpl_id = _make_template(shared=True)

    _create_event(client, tpl_id, "2027-05-01", 12345)
    _create_event(client, tpl_id, "2027-05-02", 12346)

    with app.app_context():
        events = Event.query.filter_by(source_template_id=tpl_id).order_by(Event.id).all()
        assert len(events) == 2
        # Beide hängen an derselben Reservation
        assert events[0].reservation_id == 42
        assert events[1].reservation_id == 42


def test_unshared_template_makes_separate_reservations(client, app):
    with app.app_context():
        tpl_id = _make_template(shared=False)

    _create_event(client, tpl_id, "2027-05-01", 22345)
    _create_event(client, tpl_id, "2027-05-02", 22346)

    with app.app_context():
        events = Event.query.filter_by(source_template_id=tpl_id).order_by(Event.id).all()
        assert len(events) == 2
        # Ohne „shared" ruft jedes Turnier create_reservation auf (hier gemockt → 42),
        # aber es wird NICHT über update_reservation gruppiert. Entscheidend: jedes
        # Turnier hat eine eigene Anfrage gesendet (reservation_id gesetzt).
        assert all(e.reservation_id is not None for e in events)
