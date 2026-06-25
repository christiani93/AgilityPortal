"""Test der öffentlichen Finalisten-Anzeige (BCCS gruppiert, SKBS flach)."""
from app.extensions import db
from app.models import Event, EventFinalist


def _fin(ev, **kw):
    base = dict(event_id=ev.id, dog_name="D", handler_name="H", source="agility", position=1)
    base.update(kw)
    return EventFinalist(**base)


def test_public_finalists_bccs_grouped(app):
    client = app.test_client()
    ev = Event(name="BCCS-SM", is_published=True)
    db.session.add(ev)
    db.session.flush()
    db.session.add_all([
        _fin(ev, license="L0", dog_name="Movie", handler_name="HF", from_class=3,
             category="Large", division="sm", position=1),
        _fin(ev, license="N1", dog_name="Nano", handler_name="HFN", source="jumping",
             from_class=1, category="Intermediate", division="nachwuchs", position=2),
    ])
    db.session.commit()

    resp = client.get(f"/events/{ev.id}/finalists")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "Movie" in body and "Nano" in body
    assert "Large" in body and "Nachwuchs" in body   # Division-Label gerendert


def test_public_finalists_skbs_flat(app):
    client = app.test_client()
    ev = Event(name="SKBS-SM", is_published=True)
    db.session.add(ev)
    db.session.flush()
    db.session.add(_fin(ev, license="A", dog_name="Aaron", handler_name="HA", from_class=3))
    db.session.commit()

    resp = client.get(f"/events/{ev.id}/finalists")
    assert resp.status_code == 200
    assert "Aaron" in resp.get_data(as_text=True)


def test_public_finalists_404_ohne_finalisten(app):
    client = app.test_client()
    ev = Event(name="Leer", is_published=True)
    db.session.add(ev)
    db.session.commit()
    assert client.get(f"/events/{ev.id}/finalists").status_code == 404


def test_public_finalists_404_unpublished(app):
    client = app.test_client()
    ev = Event(name="Entwurf", is_published=False)
    db.session.add(ev)
    db.session.flush()
    db.session.add(_fin(ev, license="X", category="Large", division="sm"))
    db.session.commit()
    assert client.get(f"/events/{ev.id}/finalists").status_code == 404
