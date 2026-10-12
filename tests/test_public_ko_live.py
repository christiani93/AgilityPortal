"""Öffentliche KO-Live-Anzeige: spiegelt den von der Software gepushten Bracket-Stand."""
import json

from app.extensions import db
from app.models import Event, LiveUpdate


def _ko_update(ev, seq, finals, device="ring-main"):
    return LiveUpdate(
        event_id=ev.id,
        event_external_id=ev.external_id,
        source_system="agility-software",
        source_device=device,
        sequence_no=seq,
        payload_json=json.dumps({
            "schema": "agility.exchange.liveupdate.v1",
            "event_external_id": ev.external_id,
            "update_type": "ko_bracket",
            "event_name": ev.name,
            "finals": finals,
        }),
    )


_BRACKET = [{
    "id": "f1", "group_label": "Large", "category_code": "L", "status": "running",
    "matchups": [{
        "id": "m1", "round_no": 1, "matchup_no": 1, "matchup_type": "winner",
        "label": "Runde 1",
        "a": {"id": "pa", "dog_name": "Rex", "handler_name": "Anna", "start_number": 3},
        "b": {"id": "pb", "dog_name": "Fido", "handler_name": "Ben", "start_number": 7},
        "a_total": 41.2, "b_total": 44.9, "winner_id": "pa",
        "forfeit_id": None, "is_tie": False, "rings": None,
    }],
}]


def test_ko_live_json_returns_latest_bracket(app):
    client = app.test_client()
    ev = Event(name="HCS", is_published=True, external_id="hcs-1")
    db.session.add(ev)
    db.session.flush()
    db.session.add(_ko_update(ev, 1000, _BRACKET))
    db.session.commit()

    resp = client.get(f"/api/events/{ev.id}/ko-live.json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["event_name"] == "HCS"
    assert len(data["finals"]) == 1
    assert data["finals"][0]["matchups"][0]["a"]["dog_name"] == "Rex"
    assert data["updated_at"]


def test_ko_live_json_picks_newest_update(app):
    client = app.test_client()
    ev = Event(name="HCS", is_published=True, external_id="hcs-2")
    db.session.add(ev)
    db.session.flush()
    # Älterer Stand (ein Duell) + neuerer Stand (Sieger entschieden)
    db.session.add(_ko_update(ev, 1000, _BRACKET))
    newer = json.loads(json.dumps(_BRACKET))
    newer[0]["status"] = "done"
    db.session.add(_ko_update(ev, 2000, newer))
    db.session.commit()

    data = client.get(f"/api/events/{ev.id}/ko-live.json").get_json()
    assert data["finals"][0]["status"] == "done"


def test_ko_live_json_ignores_non_ko_updates(app):
    client = app.test_client()
    ev = Event(name="HCS", is_published=True, external_id="hcs-3")
    db.session.add(ev)
    db.session.flush()
    other = LiveUpdate(
        event_id=ev.id, event_external_id=ev.external_id,
        source_system="agility-software", source_device="ring-main",
        sequence_no=500,
        payload_json=json.dumps({"update_type": "result", "ring": "Ring 1"}),
    )
    db.session.add(other)
    db.session.commit()

    data = client.get(f"/api/events/{ev.id}/ko-live.json").get_json()
    assert data["finals"] == []
    assert data["updated_at"] is None


def test_ko_live_page_renders(app):
    client = app.test_client()
    ev = Event(name="HCS", is_published=True, external_id="hcs-4")
    db.session.add(ev)
    db.session.flush()
    db.session.add(_ko_update(ev, 1000, _BRACKET))
    db.session.commit()

    resp = client.get(f"/events/{ev.id}/ko-live")
    assert resp.status_code == 200
    assert "ko-live.json" in resp.get_data(as_text=True)


def test_ko_live_page_404_unpublished(app):
    client = app.test_client()
    ev = Event(name="Entwurf", is_published=False, external_id="hcs-5")
    db.session.add(ev)
    db.session.commit()
    assert client.get(f"/events/{ev.id}/ko-live").status_code == 404


def test_overview_shows_ko_button_only_with_bracket(app):
    client = app.test_client()
    ev = Event(name="HCS", is_published=True, external_id="hcs-6")
    db.session.add(ev)
    db.session.commit()
    # Ohne Push: kein Button
    assert "ko-live" not in client.get(f"/events/{ev.id}").get_data(as_text=True)
    # Nach Push: Button sichtbar
    db.session.add(_ko_update(ev, 1000, _BRACKET))
    db.session.commit()
    assert "ko-live" in client.get(f"/events/{ev.id}").get_data(as_text=True)
